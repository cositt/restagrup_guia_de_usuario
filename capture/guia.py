"""Capture helpers: drive Odoo with Playwright and record numbered screenshots.

Each task module defines TASK (texts) and run(g). Every g.step() saves one
image and the boxes of the marked elements, as percentages of the image, so
the site can draw the numbered circles on top.
"""
import io
import json
import os
import re
import subprocess
import tempfile

from PIL import Image

BASE = os.environ.get('GUIA_URL', 'https://restagrup.cositt.net')
DB = os.environ.get('GUIA_DB', 'db-restagrup')
CREDENTIALS = os.path.expanduser(os.environ.get('GUIA_CREDENTIALS', '~/.restagrup-guia.env'))
# Lo que crean las tareas en la base (producción): se anota aquí y capture/limpiar.py lo borra al terminar.
CREATED = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'created.json')
PREFIX = '[GUIA]'
VIEWPORT = {'width': 1680, 'height': 1000}
SCALE = 1.25
PAD = 44
MARK_PAD = 4


SCROLL_JS = """e => {
    let p = e.parentElement;
    while (p && !(p.scrollHeight > p.clientHeight && /auto|scroll/.test(getComputedStyle(p).overflowY))) p = p.parentElement;
    p = p || document.scrollingElement;
    const sticky = [...document.querySelectorAll('.o_form_statusbar, .o_control_panel, .modal-header')]
        .filter(x => x.offsetParent && !e.contains(x) && !x.contains(e) && x.getBoundingClientRect().top < 300)
        .reduce((m, x) => Math.max(m, x.getBoundingClientRect().bottom), 0);
    p.scrollTop += e.getBoundingClientRect().top - sticky - 24;
}"""


class Band:
    def __init__(self, top, bottom, sheet):
        self.top, self.bottom, self.sheet = top, bottom, sheet


class Guide:
    def __init__(self, page, task, out_dir):
        self.page = page
        self.task = task
        self.out_dir = out_dir
        self.steps = []
        img_dir = os.path.join(out_dir, 'img', task['id'])
        os.makedirs(img_dir, exist_ok=True)
        for old in os.listdir(img_dir):
            if old.endswith('.webp'):
                os.remove(os.path.join(img_dir, old))

    # -- navigation -------------------------------------------------------
    def wait(self, ms=600):
        page = self.page
        page.wait_for_load_state('load')
        try:
            page.wait_for_function(
                "() => !document.querySelector('.o_loading_indicator, .o-main-components-container .o_blockUI')",
                timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(ms)

    def home(self):
        self.page.goto(f'{BASE}/odoo')
        self.page.wait_for_selector('.o_app', timeout=60000)
        self.wait()

    def open_app(self, name='Restagrup'):
        self.home()
        self.page.locator('.o_app', has_text=name).first.click()
        self.page.wait_for_selector('.o_menu_sections', timeout=30000)
        self.wait()

    def menu(self, *path):
        """Locator of a top menu entry; for a submenu the dropdown is opened.

        Entries that do not fit in the bar live under the «+»: it is opened
        and the entry inside it is returned.
        """
        nav = self.page.locator('.o_menu_sections')
        top = nav.locator('.o_nav_entry, .dropdown-toggle', has_text=path[0]).first
        if not top.is_visible():
            item = self.page.locator('.o-dropdown--menu .dropdown-item:visible', has_text=path[-1]).first
            if not item.count():
                nav.locator('.o_menu_sections_more .dropdown-toggle, .o_menu_sections_more button').last.click()
                item.wait_for(timeout=10000)
            return item
        if len(path) == 1:
            return top
        top.click()
        self.page.wait_for_selector('.o-dropdown--menu .dropdown-item')
        return self.page.locator('.o-dropdown--menu .dropdown-item', has_text=path[1]).first

    def go(self, *path):
        self.menu(*path).click()
        self.wait(900)

    def url(self, path):
        self.page.goto(f'{BASE}{path}')
        self.wait(1200)

    # -- locators -----------------------------------------------------------
    def scope(self):
        modal = self.page.locator('.modal:visible .modal-content')
        return modal.last if modal.count() else self.page.locator('.o_action_manager')

    def field(self, name):
        sc = self.scope()
        visible = sc.locator(f'.o_field_widget[name="{name}"]:visible')
        return visible.first if visible.count() else sc.locator(f'.o_field_widget[name="{name}"]').first

    def label(self, name):
        cands = self.scope().locator(f'label[for^="{name}_"]')
        for i in range(cands.count()):
            one = cands.nth(i)
            if re.fullmatch(rf'{re.escape(name)}_\d+', one.get_attribute('for') or '') and one.is_visible():
                return one
        return None

    def button(self, text=None, name=None):
        sc = self.scope()
        if name:
            return sc.locator(f'button[name="{name}"]:visible').first
        return sc.locator('button:visible', has_text=re.compile(rf'^\s*{re.escape(text)}\s*$')).first

    def sep(self, text):
        return self.scope().locator('.o_horizontal_separator', has_text=text).first

    def band(self, top, bottom):
        """Crop of the whole form width, from the top locator to the bottom one."""
        return Band(top, bottom, self.scope().locator('.o_form_sheet, .modal-body').first)

    def radio(self, name, label):
        self.field(name).locator('label', has_text=label).first.click()
        self.wait(900)

    def tab(self, text):
        return self.scope().locator('.o_notebook .nav-link', has_text=text).first

    # -- input --------------------------------------------------------------
    def m2o(self, name, text, pick=None):
        inp = self.field(name).locator('input').first
        inp.click()
        inp.fill(text)
        self.page.wait_for_selector('.o-autocomplete--dropdown-item', timeout=10000)
        self.page.wait_for_timeout(500)
        items = self.page.locator('.o-autocomplete--dropdown-item')
        items.filter(has_text=pick or text).first.click()
        self.wait(1000)

    def fill(self, name, value, enter=False):
        widget = self.field(name)
        inp = widget.locator('input, textarea, [contenteditable=true]').first
        if not inp.count() and widget.locator('button.o_input').count():
            # Odoo 19 shows some dates as a button until they are clicked
            widget.locator('button.o_input').first.click()
            self.page.wait_for_timeout(400)
        inp.click()
        if inp.get_attribute('contenteditable') == 'true':
            self.page.keyboard.type(str(value))
            self.wait(500)
            return
        inp.fill(str(value))
        self.page.mouse.move(VIEWPORT['width'] - 2, VIEWPORT['height'] - 2)
        if enter:
            inp.press('Enter')
        else:
            inp.press('Tab')
        self.page.wait_for_timeout(300)
        if self.page.locator('.o_datetime_picker:visible, .o-autocomplete--dropdown-menu:visible').count():
            self.page.keyboard.press('Escape')
        self.wait(500)

    def open_select(self, name):
        self.field(name).locator('input.o_select_menu_toggler, select').first.click()
        self.page.wait_for_selector('.o_select_menu_item', timeout=10000)
        return self.page.locator('.o_select_menu_item:visible')

    def options(self, name):
        texts = self.open_select(name).all_inner_texts()
        self.page.keyboard.press('Escape')
        self.page.wait_for_timeout(300)
        return [t.strip() for t in texts]

    def select(self, name, label):
        items = self.open_select(name)
        items.filter(has_text=label).first.click()
        self.wait(1000)

    def check(self, name, on=True):
        box = self.field(name).locator('input[type=checkbox]').first
        if box.is_checked() != on:
            box.click(force=True)
        self.wait(300)

    def save(self):
        self.page.locator('.o_form_button_save:visible').first.click()
        self.wait(900)

    # -- data ---------------------------------------------------------------
    def rpc(self, model, method, args=None, kwargs=None):
        return self.page.evaluate(
            """async ([model, method, args, kwargs]) => {
                kwargs = Object.assign({}, kwargs);
                kwargs.context = Object.assign({lang: 'es_ES', tz: 'Europe/Madrid', allowed_company_ids: [1]}, kwargs.context || {});
                const r = await fetch('/web/dataset/call_kw', {method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({jsonrpc: '2.0', method: 'call',
                        params: {model, method, args, kwargs}})});
                const j = await r.json();
                if (j.error) throw new Error(JSON.stringify(j.error.data.message));
                return j.result;
            }""", [model, method, args or [], kwargs or {}])

    def find(self, model, domain, fields=('id',)):
        res = self.rpc(model, 'search_read', [domain], {'fields': list(fields), 'limit': 1})
        return res[0] if res else None

    def track(self, model, ids):
        """Anota registros creados por la guía para borrarlos al terminar (capture/limpiar.py)."""
        ids = [ids] if isinstance(ids, int) else list(ids)
        data = json.load(open(CREATED, encoding='utf-8')) if os.path.exists(CREATED) else []
        data += [{'model': model, 'id': i, 'task': self.task['id']} for i in ids]
        with open(CREATED, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)

    def create(self, model, vals, context=None):
        """Crea por RPC y lo anota para limpiar."""
        rid = self.rpc(model, 'create', [vals], {'context': context or {}})
        self.track(model, rid)
        return rid

    def open_row(self, row):
        row.locator('td.o_data_cell').first.click()
        self.wait(1500)

    def open_record(self, action, rid):
        self.url(f'/odoo/action-{action}/{rid}')
        self.page.wait_for_selector('.o_form_view', timeout=30000)
        self.wait(800)

    def draw(self, canvas, strokes):
        """Draw strokes (lists of (x, y) fractions of the canvas) with the mouse."""
        box = canvas.bounding_box()
        mouse = self.page.mouse
        for stroke in strokes:
            x, y = stroke[0]
            mouse.move(box['x'] + x * box['width'], box['y'] + y * box['height'])
            mouse.down()
            for x, y in stroke[1:]:
                mouse.move(box['x'] + x * box['width'], box['y'] + y * box['height'], steps=6)
            mouse.up()
        self.page.wait_for_timeout(300)

    def sign(self, name, step_text=None):
        self.field(name).click()
        dialog = self.page.locator('.modal-content', has_text='Adopte su firma').last
        dialog.wait_for()
        self.draw(dialog.locator('canvas.o_web_sign_signature'),
                  [[(.15, .6), (.25, .3), (.32, .7), (.42, .35), (.5, .65), (.6, .4), (.75, .55), (.85, .45)]])
        if step_text:
            self.step(step_text, marks=[dialog.locator('canvas'), dialog.locator('button', has_text='Adoptar y firmar')],
                      crop=dialog, labels=['Firma con el dedo o el ratón.', 'Pulsa **Adoptar y firmar**.'])
        dialog.locator('button', has_text='Adoptar y firmar').click()
        self.wait(800)

    # -- capture ------------------------------------------------------------
    def _box(self, target):
        if target is None:
            return None
        loc = target
        boxes = []
        for part in (loc if isinstance(loc, (list, tuple)) else [loc]):
            if part is None:
                continue
            for one in part.all():
                if not one.is_visible():
                    continue
                b = one.bounding_box()
                if b and (b['y'] < 0 or b['y'] + b['height'] > VIEWPORT['height']):
                    one.scroll_into_view_if_needed(timeout=5000)
                    b = one.bounding_box()
                if b:
                    boxes.append(b)
        if not boxes:
            return None
        x0 = min(b['x'] for b in boxes) - MARK_PAD
        y0 = min(b['y'] for b in boxes) - MARK_PAD
        x1 = max(b['x'] + b['width'] for b in boxes) + MARK_PAD
        y1 = max(b['y'] + b['height'] for b in boxes) + MARK_PAD
        return {'x': x0, 'y': y0, 'width': x1 - x0, 'height': y1 - y0}

    def step(self, text, marks=(), crop=None, tip=None, warn=None, stop=None,
             detail=None, labels=None):
        """Screenshot with numbered marks. marks: locators (or lists of them)."""
        page = self.page
        page.mouse.move(VIEWPORT['width'] - 2, VIEWPORT['height'] - 2)
        page.wait_for_timeout(250)
        if isinstance(crop, Band):
            crop.top.evaluate(SCROLL_JS)
            page.wait_for_timeout(400)
        elif crop not in (None, 'top'):
            first = crop[0] if isinstance(crop, (list, tuple)) else crop
            first.first.evaluate(SCROLL_JS)
            page.wait_for_timeout(300)
        mark_boxes = [self._box(m) for m in marks]
        clip = None
        if isinstance(crop, Band):
            t, bt, sh = crop.top.bounding_box(), crop.bottom.bounding_box(), crop.sheet.bounding_box()
            y0 = max(t['y'] - PAD / 2, 0)
            clip = {'x': max(sh['x'] - 8, 0), 'y': y0, 'width': min(sh['width'] + 16, VIEWPORT['width']),
                    'height': min(bt['y'] + bt['height'] + PAD / 2, VIEWPORT['height']) - y0}
        elif crop == 'top':
            clip = {'x': 0, 'y': 0, 'width': VIEWPORT['width'], 'height': 380}
        elif crop is not None:
            cb = self._box(crop)
            clip = {'x': max(cb['x'] - PAD, 0), 'y': max(cb['y'] - PAD, 0)}
            clip['width'] = min(cb['width'] + 2 * PAD, VIEWPORT['width'] - clip['x'])
            clip['height'] = min(cb['height'] + 2 * PAD, VIEWPORT['height'] - clip['y'])
        if clip is None:
            clip = {'x': 0, 'y': 0, **VIEWPORT}
        png = page.screenshot(clip=clip)
        self.steps.append(dict(text=text, tip=tip, warn=warn, stop=stop,
                               detail=detail, labels=labels or []))
        idx = len(self.steps)
        rel = f"img/{self.task['id']}/{idx:02d}.webp"
        img = Image.open(io.BytesIO(png)).convert('RGB')
        img.save(os.path.join(self.out_dir, rel), 'WEBP', quality=82, method=6)
        out = []
        for b in mark_boxes:
            if not b:
                out.append(None)
                continue
            out.append({k: round(v, 2) for k, v in dict(
                x=(b['x'] - clip['x']) / clip['width'] * 100,
                y=(b['y'] - clip['y']) / clip['height'] * 100,
                w=b['width'] / clip['width'] * 100,
                h=b['height'] / clip['height'] * 100).items()})
        self.steps[-1].update(img=rel, w=img.width, h=img.height, marks=out)

    def record_id(self):
        return int(re.search(r'/(\d+)(?:\?|$)', self.page.url).group(1))

    def pdf(self, model, method, text, pages=(1,), res_id=None, **kw):
        """Render the report that model.method returns and show its pages."""
        res_id = res_id or self.record_id()
        action = self.rpc(model, method, [[res_id]])
        ids = (action.get('context') or {}).get('active_ids') or [res_id]
        url = f"{BASE}/report/pdf/{action['report_name']}/{','.join(map(str, ids))}"
        resp = self.page.request.get(url, timeout=120000)
        assert resp.ok and resp.body()[:4] == b'%PDF', f'no PDF from {url}'
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, 'doc.pdf')
        with open(path, 'wb') as fh:
            fh.write(resp.body())
        for n, pg in enumerate(pages):
            subprocess.run(['pdftoppm', '-r', '110', '-f', str(pg), '-l', str(pg), '-png', path,
                            os.path.join(tmp, f'p{pg}')], check=True)
            png = [f for f in os.listdir(tmp) if f.startswith(f'p{pg}') and f.endswith('.png')][0]
            img = Image.open(os.path.join(tmp, png)).convert('RGB')
            self.steps.append(dict(text=text if n == 0 else f'Página {pg}.', labels=[], marks=[],
                                   tip=kw.get('tip') if n == 0 else None, warn=kw.get('warn') if n == 0 else None,
                                   stop=None, detail=kw.get('detail') if n == 0 else None, doc=True))
            rel = f"img/{self.task['id']}/{len(self.steps):02d}.webp"
            img.save(os.path.join(self.out_dir, rel), 'WEBP', quality=80, method=6)
            self.steps[-1].update(img=rel, w=img.width, h=img.height)
        self.wait(800)

    def result(self):
        data = dict(self.task)
        data['steps'] = self.steps
        return data


def _credentials():
    """GUIA_USER / GUIA_PASSWORD del entorno o del fichero local (KEY=valor, permisos 600, fuera del repo)."""
    values = {}
    if os.path.exists(CREDENTIALS):
        for line in open(CREDENTIALS, encoding='utf-8'):
            key, sep, value = line.strip().partition('=')
            if sep and not key.startswith('#'):
                values[key.strip()] = value.strip()
    return (os.environ.get('GUIA_USER') or values.get('GUIA_USER'),
            os.environ.get('GUIA_PASSWORD') or values.get('GUIA_PASSWORD'))


def login(page):
    """Entra con el usuario de la guía (nunca se escribe en el repo ni en la salida)."""
    user, password = _credentials()
    if not user or not password:
        raise SystemExit('Falta el usuario de la guía: GUIA_USER y GUIA_PASSWORD en %s (permisos 600).' % CREDENTIALS)
    page.goto(f'{BASE}/web/login?db={DB}')
    page.fill('.oe_login_form input[name=login]', user)
    page.fill('.oe_login_form input[name=password]', password)
    page.click('.oe_login_form button[type=submit]')
    page.wait_for_selector('.o_main_navbar', timeout=60000)


def all_companies(page):
    """Restagrup tiene una sola compañía."""
    page.context.add_cookies([{'name': 'cids', 'value': '1', 'url': BASE}])

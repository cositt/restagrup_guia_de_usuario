"""Run the capture of the guide: python3 capture/run.py [task_id ...]"""
import importlib
import json
import os
import sys
import traceback

from playwright.sync_api import sync_playwright

from guia import SCALE, VIEWPORT, Guide, all_companies, login
from tareas import ORDER

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, 'docs')
DATA = os.path.join(DOCS, 'data', 'tasks.json')


def load():
    if os.path.exists(DATA):
        with open(DATA, encoding='utf-8') as fh:
            return {t['id']: t for t in json.load(fh)}
    return {}


def main(only):
    done = load()
    failed = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport=VIEWPORT, device_scale_factor=SCALE,
                                  locale='es-ES', timezone_id='Europe/Madrid')
        # Hide the floating chat bubbles: they are not part of the module.
        ctx.add_init_script("""document.addEventListener('DOMContentLoaded', () => {
            const st = document.createElement('style');
            st.textContent = '.o-mail-ChatHub, .o-mail-ChatWindow, [class*=ChatBubble], .o-mail-ChatHub-bubbles {display: none !important}';
            document.head.appendChild(st);
        });""")
        page = ctx.new_page()
        page.set_default_timeout(20000)
        login(page)
        all_companies(page)
        for name in ORDER:
            mod = importlib.import_module(f'tareas.{name}')
            if only and mod.TASK['id'] not in only and name not in only:
                continue
            g = Guide(page, mod.TASK, DOCS)
            print('>>', mod.TASK['id'], flush=True)
            try:
                mod.run(g)
                done[mod.TASK['id']] = g.result()
            except Exception:
                traceback.print_exc()
                page.screenshot(path=os.path.join(ROOT, f'capture/error-{mod.TASK["id"]}.png'))
                failed.append(mod.TASK['id'])
                page.keyboard.press('Escape')
        browser.close()
    order = {importlib.import_module(f'tareas.{n}').TASK['id']: i for i, n in enumerate(ORDER)}
    tasks = sorted(done.values(), key=lambda t: order.get(t['id'], 999))
    with open(DATA, 'w', encoding='utf-8') as fh:
        json.dump(tasks, fh, ensure_ascii=False, indent=1)
    print('OK', len(tasks), 'FAILED', failed)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(set(sys.argv[1:])))

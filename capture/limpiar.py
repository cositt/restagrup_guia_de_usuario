"""Borra de la base todo lo que crearon las capturas: python3 capture/limpiar.py [--dry-run]

1. Lo anotado en capture/created.json (en orden inverso a como se creó).
2. Un barrido de seguridad: todo registro cuyo nombre empiece por [GUIA] en los modelos de la guía.
Los presupuestos y hojas de servicio se cancelan antes de borrarlos (Odoo no borra los confirmados).
Al final dice qué queda; si queda algo, no se da por limpio.
"""
import json
import os
import sys

from playwright.sync_api import sync_playwright

from guia import CREATED, PREFIX, VIEWPORT, Guide, all_companies, login

# Modelo -> campo con el nombre para el barrido. Orden: primero lo que depende de lo demás.
SWEEP = [
    ('restagrup.pending.mail', 'subject'),
    ('purchase.order', 'partner_id.name'),
    ('sale.order', 'partner_id.name'),
    ('restagrup.restaurant.search', 'lead_id.name'),
    ('restagrup.restaurant.menu', 'name'),
    ('crm.lead', 'name'),
    ('product.template', 'name'),
    ('res.partner', 'name'),
]
CANCEL = {'sale.order': '_action_cancel', 'purchase.order': 'button_cancel'}


def _ids(g, model, domain):
    return g.rpc(model, 'search', [domain], {'context': {'active_test': False}})


def _delete(g, model, ids, dry):
    ids = [i for i in ids if _ids(g, model, [('id', '=', i)])]
    if not ids:
        return 0
    if dry:
        print('  borraría', model, ids)
        return len(ids)
    if model in CANCEL:
        g.rpc(model, CANCEL[model], [ids])
    g.rpc(model, 'unlink', [ids])
    print('  borrado', model, ids)
    return len(ids)


def main(dry):
    tracked = json.load(open(CREATED, encoding='utf-8')) if os.path.exists(CREATED) else []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_context(viewport=VIEWPORT, locale='es-ES').new_page()
        login(page)
        all_companies(page)
        g = Guide.__new__(Guide)
        g.page = page
        failed = []
        print('Anotados:', len(tracked))
        for item in reversed(tracked):
            try:
                _delete(g, item['model'], [item['id']], dry)
            except Exception as exc:  # noqa: BLE001 -- se informa y se sigue con el resto
                failed.append((item['model'], item['id'], str(exc)[:200]))
        print('Barrido', PREFIX)
        for model, name in SWEEP:
            try:
                _delete(g, model, _ids(g, model, [(name, '=like', PREFIX + '%')]), dry)
            except Exception as exc:  # noqa: BLE001
                failed.append((model, name, str(exc)[:200]))
        left = {model: _ids(g, model, [(name, '=like', PREFIX + '%')]) for model, name in SWEEP}
        left = {m: ids for m, ids in left.items() if ids}
        browser.close()
    for row in failed:
        print('ERROR', *row)
    if dry:
        print('Simulación: no se ha borrado nada.')
        return 0
    if left or failed:
        print('NO LIMPIO. Queda:', left)
        return 1
    if os.path.exists(CREATED):
        os.remove(CREATED)
    print('LIMPIO: no queda nada con', PREFIX)
    return 0


if __name__ == '__main__':
    sys.exit(main('--dry-run' in sys.argv))

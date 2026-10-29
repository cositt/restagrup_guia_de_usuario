"""Monta la guía con capturas hechas desde un Chrome ya logueado (sin usuario ni contraseña en ningún sitio).

    python3 capture/chrome.py reset <tarea>                  # empieza la tarea de cero (borra sus pasos e imágenes)
    python3 capture/chrome.py step <tarea> <captura> '<json>'  # añade un paso
    python3 capture/chrome.py build                          # junta todo en docs/data/tasks.json

La tarea (título, resumen, cuándo, antes, resultado...) está en capture/chrome_tasks/<tarea>.json y el orden en
capture/chrome_tasks/ORDER. El json del paso: {"text", "marks": [{x,y,w,h} en % de la pantalla o null], "labels",
"tip", "warn", "stop", "detail", "crop": {x,y,w,h} en % (opcional, recorta la pantalla)}.
"""
import json
import os
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, 'docs')
TASKS = os.path.join(ROOT, 'capture', 'chrome_tasks')
STEPS = os.path.join(ROOT, 'capture', 'chrome_steps')
DATA = os.path.join(DOCS, 'data', 'tasks.json')
MAX_WIDTH = 1920


def _steps_path(task):
    return os.path.join(STEPS, '%s.json' % task)


def _load_steps(task):
    path = _steps_path(task)
    return json.load(open(path, encoding='utf-8')) if os.path.exists(path) else []


def _save_steps(task, steps):
    os.makedirs(STEPS, exist_ok=True)
    with open(_steps_path(task), 'w', encoding='utf-8') as fh:
        json.dump(steps, fh, ensure_ascii=False, indent=1)


def reset(task):
    img_dir = os.path.join(DOCS, 'img', task)
    if os.path.isdir(img_dir):
        for name in os.listdir(img_dir):
            os.remove(os.path.join(img_dir, name))
    _save_steps(task, [])


def _relative(mark, crop):
    """Marca en % de la pantalla -> % del recorte."""
    if not mark or not crop:
        return mark
    f = lambda v: round(v, 2)  # noqa: E731
    return {'x': f((mark['x'] - crop['x']) / crop['w'] * 100), 'y': f((mark['y'] - crop['y']) / crop['h'] * 100),
            'w': f(mark['w'] / crop['w'] * 100), 'h': f(mark['h'] / crop['h'] * 100)}


def step(task, shot, spec):
    spec = json.loads(spec)
    steps = _load_steps(task)
    img = Image.open(shot).convert('RGB')
    crop = spec.get('crop')
    if crop:
        W, H = img.size
        box = (round(crop['x'] / 100 * W), round(crop['y'] / 100 * H),
               round((crop['x'] + crop['w']) / 100 * W), round((crop['y'] + crop['h']) / 100 * H))
        img = img.crop(box)
    if img.width > MAX_WIDTH:
        img = img.resize((MAX_WIDTH, round(img.height * MAX_WIDTH / img.width)), Image.LANCZOS)
    rel = 'img/%s/%02d.webp' % (task, len(steps) + 1)
    os.makedirs(os.path.join(DOCS, 'img', task), exist_ok=True)
    img.save(os.path.join(DOCS, rel), 'WEBP', quality=82, method=6)
    steps.append(dict(
        text=spec['text'], tip=spec.get('tip'), warn=spec.get('warn'), stop=spec.get('stop'),
        detail=spec.get('detail'), labels=spec.get('labels') or [], img=rel, w=img.width, h=img.height,
        marks=[_relative(m, crop) for m in spec.get('marks') or []], doc=spec.get('doc', False)))
    _save_steps(task, steps)
    print('paso', len(steps), rel)


def build():
    order = [line.strip() for line in open(os.path.join(TASKS, 'ORDER'), encoding='utf-8') if line.strip()]
    tasks = []
    for name in order:
        meta = json.load(open(os.path.join(TASKS, '%s.json' % name), encoding='utf-8'))
        steps = _load_steps(name)
        if not steps:
            print('sin pasos:', name)
            continue
        tasks.append(dict(meta, id=name, steps=steps))
    with open(DATA, 'w', encoding='utf-8') as fh:
        json.dump(tasks, fh, ensure_ascii=False, indent=1)
    print('tareas', len(tasks))


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'reset':
        reset(sys.argv[2])
    elif cmd == 'step':
        step(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == 'build':
        build()

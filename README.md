# Guía de usuario — Restagrup

Guía paso a paso, con capturas, de Restagrup en Odoo 19 para el equipo de RestaGrup: peticiones de grupos, búsqueda
de restaurantes, presupuestos, expedientes, pagos, facturas y correos automáticos.

- **Web**: carpeta `docs/` (estática, publicada con GitHub Pages).
- **Capturas**: carpeta `capture/` (Playwright). Genera `docs/img/<tarea>/` y `docs/data/tasks.json`.

Las capturas se hacen **en producción** (`restagrup.cositt.net`) para comprobar de paso que todo funciona. Todo lo
que crean lleva el prefijo **`[GUIA]`**, se anota en `capture/created.json` y se borra al terminar con
`capture/limpiar.py`. Los correos de prueba van solo a buzones de prueba, nunca a agencias ni restaurantes reales.

## Regenerar las capturas

Necesitas Python 3 con Playwright (`pip install playwright pillow && playwright install chromium`) y `pdftoppm`.

El usuario de la guía va en un fichero local **fuera del repositorio**, con permisos `600`:

```bash
# ~/.restagrup-guia.env
GUIA_USER=...
GUIA_PASSWORD=...
```

```bash
python3 capture/run.py                    # todas las tareas, en orden
python3 capture/run.py menu avisos        # solo algunas (por id)
python3 capture/limpiar.py --dry-run      # qué se borraría
python3 capture/limpiar.py                # borra lo creado y comprueba que no queda nada con [GUIA]
```

Cada tarea es un fichero en `capture/tareas/` con su `TASK` (textos) y `run(g)` (pasos). Lo que crea se anota con
`g.create(...)` o `g.track(...)`. El orden está en `capture/tareas/__init__.py`.

## Textos fijos

Temas, flujos, sinónimos de búsqueda, glosario y errores frecuentes están en `docs/assets/meta.js`.

## Ver la web en local

```bash
cd docs && python3 -m http.server 8765
```

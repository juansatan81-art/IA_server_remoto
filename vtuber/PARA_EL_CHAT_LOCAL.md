# Encargo para el chat local «VTuber 2D con IA setup»

Lo ha preparado el chat en la nube (rama `claude/gallant-goodall-ep9rxq` de
`juansatan81-art/IA_server_remoto`). Juan Luis te pide tres cosas:

## 1. Actualizar la carpeta local

En `C:\Users\juans\Proyectos\IA_server_remoto`:

```
git pull
cd vtuber
.venv\Scripts\python -m pip install -r requirements.txt
ollama pull gemma4:26b
ollama pull qwen3:1.7b
```

(`iniciar.bat` ya instala lo que falte y actualiza edge-tts al arrancar.)

## 2. Copiar el motion graphic a YouTube automatización

El vídeo está en `vtuber/arte/motion/entregas/lara_la_carta_v1.mp4` (1080×1080,
60 fps, 15 s, sin música todavía). Es un **edit**: cópialo a la carpeta del proyecto
de **YouTube automatización**, en la parte de **producción** (donde vayan los edits /
clips terminados), con un nombre que siga la numeración de ese proyecto. Si no existe
una subcarpeta para edits, créala dentro de producción y díselo a Juan Luis.

## 3. Qué se ha hecho (resumen)

**Lara (la VTuber), `vtuber/`**
- Cerebro: `gemma4:26b` (MoE, ~68 tok/s en su RTX 5070 Ti, parte en RAM). Decide sola si
  busca en internet y si piensa a fondo (solo cálculos y problemas; dice "déjame
  pensarlo" para no quedarse en silencio). Ve imágenes y la pantalla compartida.
- Modo directo autónomo (`directo.py`): elige a quién responder del chat, habla sola
  cuando el chat calla, tiene ánimo, plan del directo y recuerdos (`memoria/`).
- Filtros (`filtros.py`): reglas + un modelo pequeño en el procesador (`qwen3:1.7b`) que
  revisa el chat y lo que va a decir antes de la voz. Botón de PÁNICO en el panel.
- Chat de YouTube (`youtube.py`): la clave va en `config.local.json` (no se sube a git).
- Glosario de memes y palabras de internet (`glosario.py`, `memoria/glosario.json`): los
  nuevos que busca quedan pendientes de aprobar en el panel.
- El modelo se descarga al cerrar la ventana negra o si no queda ninguna pantalla abierta.
- La voz reintenta y avisa en el panel si Microsoft devuelve audio vacío.

**Motion graphic «la carta»** (`vtuber/arte/motion/`, ver su README)
- Copia el ritmo de los TikTok de referencia (`arte/referencias/`), medido fotograma a
  fotograma: 4 poses con destellos, rebote a 120 BPM, espejo en la segunda mitad.
- Poses de brazos de Google Flow (`pose1..4.jpg`), encajadas con `herramientas/poses.py`
  según `poses.json`.
- El avatar ahora puede cambiar de brazos (`avatar.brazos('pose1')`), moverse al compás
  (`avatar.ritmo(...)`: pelo, flequillo, brazos, cuerpo y pecho se deforman) y tiene una
  cara nueva `timida`.
- Para volver a generar el vídeo (necesita Node + Playwright y ffmpeg):
  `python herramientas/motion_carta.py` → `arte/motion/salida/la_carta.mp4`.

**Pendiente** (pregúntaselo a Juan Luis si sale el tema): el título del vídeo (el
original pone «BRIANT»), la música (para ajustar el ritmo) y una simulación de directo
nueva para devolverle a Lara algo de chispa en la charla.

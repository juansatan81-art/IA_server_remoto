# VTuber con IA

Avatar 2D animado que controla una IA local. La IA decide qué decir y qué cara
poner, la voz sale de **edge-tts** y el avatar se muestra en el navegador o en
OBS con fondo transparente.

```
Tú / el chat ──► Cerebro (modelo local) ──► "[feliz] ¡Hola! [sorprendida] ¿En serio?"
                                               │
                         servidor.py ◄─────────┘  divide por emociones + genera la voz
                                               │
                    Avatar (navegador / OBS) ◄─┘  cambia la cara, mueve la boca con el audio
```

## Qué hace el avatar

- **Emociones:** neutral, feliz, enojada, triste, llorando, sorprendida,
  avergonzada, presumida y pensativa. Cambian ojos, cejas, boca, rubor,
  lágrimas, gota de sudor, vena de enfado y brillos, con transiciones suaves.
- **Boca sincronizada** con el volumen de la voz.
- **Vida propia:** parpadeo, mirada que se mueve, respiración y balanceo de la
  cabeza.
- **El cuerpo sigue a la cabeza con retraso:** el torso se dobla un poco, como
  si la cabeza tirara de él.
- **Pelo con física:** la parte larga se balancea con inercia y algo de viento,
  y el flequillo se mueve un poco más que la cara al girar (sensación de volumen).
- **Pecho con física:** rebota con su propio muelle al moverse el torso.
- **Ojos que miran:** la forma negra se desplaza dentro del contorno del ojo.
- La IA puede **cambiar de emoción a mitad de frase**.

## Instalación (en tu PC)

Necesitas **Python 3.10 o superior**.

```bash
cd vtuber
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
```

### El cerebro (modelo local)

Sirve cualquier programa con API compatible con OpenAI. Lo más fácil es
**Ollama** (https://ollama.com):

```bash
ollama pull qwen2.5:7b      # buen español; con poca GPU prueba qwen2.5:3b
```

Ollama escucha en `http://localhost:11434/v1`, que ya es el valor por defecto
en `config.json`. Si usas otro programa, cambia `cerebro.url` y `cerebro.modelo`:

| Programa | URL típica |
|---|---|
| Ollama | `http://localhost:11434/v1` |
| LM Studio | `http://localhost:1234/v1` |
| llama.cpp (`llama-server`) | `http://localhost:8080/v1` |
| Servidor remoto con GPU | `http://IP-DEL-SERVIDOR:PUERTO/v1` |

### La voz

Por defecto usa `es-ES-ElviraNeural`, una voz femenina de España. Para ver
todas las voces femeninas en español:

```bash
python voz.py
```

Otras buenas opciones: `es-ES-XimenaNeural`, `es-MX-DaliaNeural`,
`es-AR-ElenaNeural`. En `config.json` puedes ajustar `velocidad` (`"+10%"`) y
`tono` (`"+20Hz"` da una voz más aguda o juvenil).

## Uso

```bash
python servidor.py
```

- **Panel:** http://127.0.0.1:8765/panel. Desde aquí chateas con la IA, haces
  que diga frases exactas, cambias emociones y ladeas la cabeza. Tiene vista
  previa.
- **Avatar para OBS:** añade una *Fuente de navegador* con la URL
  `http://127.0.0.1:8765/avatar`, tamaño 1300 × 1140, y marca *Controlar audio
  mediante OBS*. El fondo es transparente.

Opciones en la URL del avatar:

| Parámetro | Efecto |
|---|---|
| `?subtitulos=1` | muestra lo que dice |
| `?fondo=%2300ff00` | fondo de color (por ejemplo verde para croma) |
| `?emocion=feliz` | empieza con esa emoción |

## Controlarlo desde otros programas

Cualquier programa (un bot de Twitch, otra IA, un script) puede manejarlo por
HTTP:

```bash
# la IA responde y habla
curl -X POST localhost:8765/api/chat -H "Content-Type: application/json" \
     -d '{"mensaje": "¿Qué juego jugamos hoy?", "usuario": "juan"}'

# hablar sin pasar por la IA
curl -X POST localhost:8765/api/decir -H "Content-Type: application/json" \
     -d '{"texto": "[presumida] Obviamente, soy la mejor."}'

# solo cambiar la cara (duracion en segundos, 0 = hasta que cambie)
curl -X POST localhost:8765/api/emocion -H "Content-Type: application/json" \
     -d '{"nombre": "enojada", "duracion": 5}'
```

También hay `/api/cabeza` (`x`, `y`, `inclinacion`), `/api/mirar`
(`x`, `y`, `duracion`), `/api/parar`, `/api/olvidar` y `/api/estado`. Cada uno
está explicado al principio de `servidor.py`.

## Personalizar

- **Nombre y personalidad:** `config.json` → `personaje`.
- **Instrucciones completas de la IA:** añade `cerebro.prompt_sistema` en
  `config.json` para sustituir la plantilla de `cerebro.py`.
- **Emociones:** `web/avatar.js` → `EXPRESIONES`. Cada emoción es una lista de
  valores: párpados, cejas, curva de la boca, rubor, lágrimas, etc.
- **Cambiar o añadir piezas:** están en `arte/piezas/`. Después ejecuta
  `python herramientas/preparar_piezas.py` (antes, una vez:
  `pip install -r herramientas/requisitos.txt`). Si cambias una pieza por otra
  con distinta posición, añade `--alinear` para recalcular su encaje.

## Cómo está hecho

El avatar se monta con las piezas dibujadas por separado (`arte/piezas/`).
`herramientas/preparar_piezas.py`:

1. **Quita el fondo magenta** recuperando la transparencia real del trazo, y
   descarta los restos medio borrados (solo se queda con las zonas nítidas).
2. **Alinea cada pieza** buscando la escala y la posición en que sus líneas
   coinciden con las del dibujo de referencia. Las piezas de cuerpo encajan con
   "La imagen maestra" y las de cabeza con el busto original; el encaje y su
   error en píxeles quedan en `arte/piezas/alineacion.json`.
3. **Separa los brazos** de la imagen maestra: son las zonas cerradas por líneas
   que no tocan el contorno del pelo.
4. **Limpia las líneas que sobran** donde se solapan piezas: el contorno del pelo
   largo bajo la cabeza, el borde de arriba del flequillo, la línea de la cara
   bajo el flequillo y el arranque del cuello bajo la barbilla.

En el navegador, la cabeza se mueve con una transformación. El pelo largo y el
torso se dibujan en **tiras horizontales de 2 px**, y cada tira se desplaza un
poco distinto: así se doblan de forma continua y sin cortes, como la suma de
muchos rectángulos que aproxima una curva. El pecho usa las mismas tiras con un
rebote que crece hacia abajo, para que arriba siga pegado al torso.

## Ideas para seguir

- Leer el chat de Twitch o YouTube y mandarlo a `/api/chat`.
- Reconocimiento de voz (por ejemplo Whisper) para hablar con ella por micrófono.
- Brazos como piezas separadas (brazo y antebrazo) para poder moverlos.
- Poses de cuerpo entero (brazos en jarra, aplaudir…) usando las otras
  ilustraciones como cambios de pose.

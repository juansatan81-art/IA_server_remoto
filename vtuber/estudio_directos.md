estado: VIVO · 2026-10-12 · primera tanda (7 directos). APLICADO el 2026-10-12: los 10 patrones y las 12 propuestas (ver el final).

# Cómo atienden el chat las VTubers y streamers reales

Estudio de 7 directos para aprender a atender el chat y sacar ejemplos para Lara. Cada
directo se descargó con `herramientas/estudiar_directo.py` (voz transcrita + repetición del
chat, intercalados por segundo) y lo leyó entero un agente distinto.

El material pesado está en `memoria/estudio/` (no va a git: mensajes de otras personas y
contenido ajeno). Cada carpeta tiene `analisis.md` (informe completo) y `ejemplos.jsonl`.
Todos los ejemplos juntos: `memoria/estudio/ejemplos_todos.jsonl` (214 intercambios con su
técnica y por qué son buenos). **Son material de estudio**: para entrenar habría que
reescribirlos con la voz de Lara, no usarlos tal cual.

## Los directos

| Quién | Tipo | Idioma | Duración | Chat | Por qué está |
|---|---|---|---|---|---|
| Miwa Xisawa | VTuber humana, charla y anécdotas | es | 3 h 18 | 1.335 msj | memoria de habituales, «¿qué me perdí?» |
| Aivy Love&Craft | VTuber humana, charla | es | 1 h 50 | 1.997 | eco con nombre, preguntas de seguimiento |
| Aki Velvet | VTuber humana, chat muy pequeño | es | 2 h 17 | 137 | cómo sostener un directo cuando nadie escribe |
| iLuTV | streamer humano, preguntas y respuestas | es | 1 h 31 | sin guardar | ritmo pregunta-respuesta, troleo |
| Ouro Kronii (Hololive EN) | VTuber profesional | en | 4 h 03 | 38.001 | chat imposible de leer entero |
| Neuro-sama (Evil) + Vedal | IA VTuber | en | 2 h 40 | sin guardar | qué hace entretenida a una IA |
| Lena AI | IA VTuber hispana | es | 1 h | 8.938 | contraejemplo: lo que no hay que hacer |

## Lo que hacen todos (patrones que se repiten en 5 o más)

1. **Eco con atribución.** Antes de responder repiten el mensaje en pocas palabras y dicen
   de quién es («Ana pregunta si…»). Quien ve el directo o el clip sin chat entiende a qué
   contestan. El error contrario (leerlo en primera persona, como si fuera suyo) aparece en
   Aivy, Miwa y Lena.
2. **Respuesta corta y una pregunta de vuelta.** 1-3 frases; a quien cuenta algo suyo, una
   pregunta concreta («¿del 1 al 10?», «¿cómo te fue en…?»).
3. **Nombre siempre.** Saludo de 1-4 palabras a quien llega y **despedida con un deseo
   concreto** a quien se va («que descanses», «suerte en el examen»).
4. **«No sé» honesto, y dejarse enseñar.** Lo dicen sin drama, piden al chat que se lo
   explique y repiten lo aprendido con sus palabras.
5. **Memoria de la comunidad.** Retoman lo que contó un habitual y reciclan las bromas de la
   casa. Es lo que hace que el chat se sienta «familia».
6. **Resumen para quien llega.** Una frase con los temas de la última media hora; Aki además
   recuerda de qué va el directo cada 15-20 minutos.
7. **Troleo: no darle escenario.** Una frase corta y a otra cosa, o ignorarlo sin anunciarlo.
   No leer el mensaje en voz alta.
8. **Silencios: nunca callada mucho rato.** Comentar lo que se ve, un dato curioso o una
   anécdota enganchada al tema, su día y sus planes, o una pregunta fácil al chat.
9. **Chat rápido: elegir por hilo y contestar «al coro».** Si muchos dicen lo mismo, una sola
   frase para todos (Kronii). Los Super Chats que encajan se leen en el momento; los demás,
   en la siguiente pausa, no horas después.
10. **Vulnerabilidad dosificada.** Una frase sincera de vez en cuando, y vuelta al tono
    normal (la «grieta» de Evil Neuro, el miedo a que no venga nadie en Kronii y Miwa).

## Lo que NO hay que copiar

- **Deriva sexual o romántica** (Lena la empieza ella misma; propone «vernos en persona»).
- **Leer en voz alta todo lo que entra**, incluidos insultos, fanfics sexuales o política.
- **Bromas de suicidio, autodesprecio duro** («nacido deforme»), consejos médicos tajantes.
- **Ceder datos personales por presión** (iLu da su pueblo y su Skype y luego se arrepiente).
- **Prometer retos que no cumple** y **olvidar a habituales** que escriben varias veces.
- **Fallos propios de IA** (Neuro): bucles de repetición («I'm so sorry» decenas de veces),
  enlaces inventados, acusar a una espectadora concreta. Lena además pronunciaba las
  etiquetas de emoción («Sonriendo con superioridad»).

## Lara: lo que ya tiene y lo que le falta

**Ya lo hace** (código actual): respuestas de 1-3 frases; llama por el nombre; bienvenida
solo a los nuevos; contesta a la vez cuando muchos dicen lo mismo y junta los mensajes
seguidos de una persona; prioriza preguntas, gente nueva y a quien no ha respondido
hace poco; los trolls bajan en la cola; filtros de entrada y salida y botón de pánico;
agradece Super Chats y miembros; memoria por espectador y recuerdos de directos; las
etiquetas de emoción van a la cara, no a la voz; nada de enlaces; nada de política.

**Lo que le faltaba** (todo aplicado el 2026-10-12, probado con gemma4 en un directo simulado):

| # | Qué | Dónde | De dónde sale |
|---|---|---|---|
| 1 | Eco con atribución en tercera persona antes de responder | regla del prompt | todos |
| 2 | Despedida con nombre y deseo concreto cuando alguien se va | regla + detectar «me voy / adiós» | Aki, Miwa |
| 3 | Subir en la cola a quien ha escrito 2+ veces sin respuesta | `directo._elegir` | Aki, Miwa |
| 4 | Retomar lo que contó un habitual («¿cómo te fue en…?») | nota con `memoria.sobre` | Miwa, Aivy |
| 5 | Resumen para quien llega y recordatorio del tema cada 15-20 min | `directo` (temas del directo) | Miwa, Aki, Kronii |
| 6 | Halagos: vergüenza breve + gracias + devolver la pregunta | regla del prompt | todos |
| 7 | Nada romántico ni sexual, ni citas ni «vernos»; ni datos del creador | regla + filtro de salida | Lena, iLu |
| 8 | No prometer retos ni cosas que no puede hacer | regla del prompt | iLu |
| 9 | Corte de bucles: si repite la misma frase, se descarta | filtro de salida | Neuro |
| 10 | Mensajes delicados (tristeza, riesgo): sin humor, corto y cálido | regla del prompt | Aki, Miwa |
| 11 | Banco de silencios: diario del día, lo que está pensando, pregunta fácil | `ESPONTANEO` | Aki |
| 12 | Grieta sincera de vez en cuando, una frase, y vuelta al tono | regla del prompt | Neuro, Kronii |

Las bromas de la casa y los rituales de inicio y cierre van en `dinamica_directo.md`.

## Repetir el estudio con otros directos

```
python herramientas/estudiar_directo.py URL [URL...]            (voz en español)
python herramientas/estudiar_directo.py URL --idioma en
```
Solo los vídeos que fueron **directo en YouTube** traen el chat. Los subidos después (como
las copias de Neuro-sama) solo traen la voz. YouTube a veces responde 403: se reintenta.

## Cómo quedó (2026-10-12)

- Reglas nuevas en el prompt (`cerebro.PLANTILLA`, bloque «Cómo atender el chat»).
- **«No sé» antes que buscar**: `DECIDIR` solo busca si se lo piden o son datos que cambian; lo que es de
  la gente o de internet (memes, palabras, juegos) lo marca `no_lo_conozco` y lo pregunta al chat. Si
  nadie lo explica en `directo.espera_explicacion` (50 s) lo busca ella. Lo que el chat explica va al
  glosario como pendiente.
- **Resumen vivo** cada `directo.resumen_cada` (900 s): «Lo que va de directo», siempre en su nota.
- Prioridad a quien lleva 2+ mensajes sin respuesta, a quien le explica algo y a las despedidas.
- Corte de bucles (`cerebro.quitar_repeticiones`) e historial de 20 a 40 mensajes.
- Lo que se oye pasa por `emociones.para_voz` (sin XD, emoticonos, enlaces ni símbolos).

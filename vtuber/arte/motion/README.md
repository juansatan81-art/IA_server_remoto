# Motion graphic «la carta» (referencia: vídeos de br1ant.pr)

Los cuatro vídeos de referencia usan la misma plantilla (1080×1080, 60 fps, 14,9 s), con
los cortes en los mismos fotogramas. Medido fotograma a fotograma:

| Tiempo | Qué pasa |
|---|---|
| 0,00–0,70 s | Entra desde negro (fundido) |
| 0,50–1,83 s | **Pose 1** · brazos cruzados (personaje a la derecha) |
| 1,83–2,20 s | Destello blanco (pico en 2 fotogramas, se apaga en ~0,35 s) + cambio de pose |
| 2,20–3,78 s | **Pose 2** · mano al pecho |
| 3,78–4,02 s | Destello |
| 4,02–5,23 s | **Pose 3** · mano a la boca; aparece el título con efecto *glitch* (4,0–5,5 s) |
| 5,23–5,85 s | Doble destello (dos pulsos separados 0,2 s) |
| 5,85–7,40 s | **Pose 4** · la carta |
| 7,40 s | Corte seco a la composición **en espejo** (personaje a la izquierda) y se repite el ciclo: pose 1 (7,40–8,87), 2 (9,25–10,95), 3 (11,13–12,38), 4 (12,92–14,32) |
| 14,32 s | Fundido a negro |

Movimiento continuo dentro de cada pose:
- **Cámara**: rebote vertical de ~25 px (de 1080) en cada tiempo de la música, periodo ~0,5 s (≈120 BPM).
- **Cabeza**: se ladea de 0° a +2,5° y vuelve, al mismo ritmo, adelantada ~0,1 s al rebote;
  en la pose 4 se ladea hacia el otro lado (−2° a +0,8°). Los mechones laterales la siguen con retraso.
- **Cuerpo**: respiración, se estira y encoge en vertical un ±2–3 %, desfasado ~¼ de periodo respecto a la cabeza.
- **Capas de fondo**: copia grande y desvaída del personaje detrás; un medidor de corazones
  con una flecha que cambia de dirección en cada pose; contorno blanco brillante alrededor del personaje.

## Lo que hace falta dibujar

`hoja_poses.png`: las 4 poses. `plantilla_brazos_2x.png`: Lara sin brazos a doble tamaño
(2600×2280) con los brazos actuales en rojo como guía. Cada pose: un PNG transparente del
mismo tamaño que la plantilla, solo brazos y manos (y la carta en la pose 4), con relleno
blanco por dentro y el mismo grosor de línea.

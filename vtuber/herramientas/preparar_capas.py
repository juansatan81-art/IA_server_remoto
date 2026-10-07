"""Separa arte/busto.png en las capas que usa el avatar (web/capas/).

Capas (todas del mismo tamaño, se superponen en el mismo origen):
  pelo.png   -> todo el personaje salvo el cuerpo; se dibuja primero
  cuerpo.png -> torso, cuello y cuello de la camisa (opaco)
  cara.png   -> el óvalo de la cara, encima del cuello

Ojos y boca se borran de la ilustración: el avatar los dibuja en vectorial
para poder animarlos.

Uso:  python herramientas/preparar_capas.py
"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

RAIZ = Path(__file__).resolve().parent.parent
ORIGEN = RAIZ / "arte" / "busto.png"
DESTINO = RAIZ / "web" / "capas"

ALTO = 1200  # la ilustración está cortada a esta altura
OSCURO = 128

# Polígono del torso (con margen para incluir el trazo)
CUERPO = [(546, 742), (546, 776), (510, 806), (460, 816), (352, 868),
          (340, 893), (286, ALTO), (978, ALTO), (921, 893), (911, 868),
          (806, 823), (760, 806), (718, 776), (718, 742)]
CUELLO_X = [(572, 579), (684, 691)]


def tramos(fila, x0, x1):
    """Tramos [inicio, fin] de píxeles oscuros en una fila."""
    oscuro = fila[x0:x1] < OSCURO
    res, dentro = [], False
    for i, d in enumerate(oscuro):
        if d and not dentro:
            ini, dentro = x0 + i, True
        elif not d and dentro:
            res.append((ini, x0 + i - 1))
            dentro = False
    if dentro:
        res.append((ini, x1 - 1))
    return res


def main():
    img = Image.open(ORIGEN).convert("RGB").crop((0, 0, 1254, ALTO))
    rgb = np.array(img)
    gris = np.array(img.convert("L"))
    alto, ancho = gris.shape

    # --- Silueta: fondo = blanco conectado con los bordes superior/laterales
    # .copy(): floodfill no escribe en imágenes que comparten memoria con numpy
    binaria = Image.fromarray(np.where(gris > 200, 255, 0).astype(np.uint8)).copy()
    for x in range(0, ancho, 25):
        if binaria.getpixel((x, 0)) == 255:
            ImageDraw.floodfill(binaria, (x, 0), 100)
    for y in range(0, alto, 25):
        for x in (0, ancho - 1):
            if binaria.getpixel((x, y)) == 255:
                ImageDraw.floodfill(binaria, (x, y), 100)
    fondo = np.array(binaria) == 100
    silueta = (~fondo).astype(np.uint8) * 255
    # suaviza el borde exterior para que la línea no quede dentada
    silueta = np.array(Image.fromarray(silueta).filter(ImageFilter.MaxFilter(3)))

    # --- Contorno de la cara fila a fila
    cara = np.zeros_like(gris, dtype=bool)
    bordes = {}
    for y in range(444, 749):
        t = tramos(gris[y], 330, 935)
        if not t:
            continue
        izq, der = t[0], t[-1]
        bordes[y] = (izq, der)
        cara[y, izq[0]:der[1] + 1] = True

    # --- Borrar ojos (entre el contorno izquierdo y el derecho)
    limpio = rgb.copy()
    for y in range(454, 604):
        izq, der = bordes[y]
        # el contorno mide ~7 px; lo que sobresale hacia dentro es el ojo
        limpio[y, min(izq[1], izq[0] + 7) + 1:max(der[0], der[1] - 7)] = 255
    # --- Borrar boca
    limpio[622:672, 582:684] = 255

    # Cara un poco dilatada para cubrir el antialiasing del contorno
    cara = np.array(Image.fromarray(cara.astype(np.uint8) * 255)
                    .filter(ImageFilter.MaxFilter(5))) > 0

    # --- Máscara del cuerpo
    m = Image.new("L", (ancho, alto), 0)
    ImageDraw.Draw(m).polygon(CUERPO, fill=255)
    cuerpo = np.array(m) > 0
    # El polígono es solo una guía con margen. El blanco que queda entre su
    # borde y el trazo real del dibujo se quita (relleno por inundación desde
    # el borde), así el recorte sigue el contorno exacto, píxel a píxel.
    gris_limpio = np.array(Image.fromarray(limpio).convert("L"))
    claro = Image.fromarray(np.where(cuerpo & (gris_limpio > 200), 255, 0).astype(np.uint8)).copy()
    interior = np.array(Image.fromarray(cuerpo.astype(np.uint8) * 255)
                        .filter(ImageFilter.MinFilter(3))) > 0
    borde = cuerpo & ~interior
    ys, xs = np.nonzero(borde)
    for y, x in zip(ys, xs):
        if y >= alto - 5 or (y < 760 and CUELLO_X[0][0] - 4 < x < CUELLO_X[1][1] + 4):
            continue  # el corte de abajo y el cuello son interiores del cuerpo
        if claro.getpixel((int(x), int(y))) == 255:
            ImageDraw.floodfill(claro, (int(x), int(y)), 100)
    cuerpo &= ~(np.array(claro) == 100)
    # +1 px hacia fuera para conservar el antialiasing del trazo
    cuerpo = np.array(Image.fromarray(cuerpo.astype(np.uint8) * 255)
                      .filter(ImageFilter.MaxFilter(3))) > 0

    def guardar(nombre, color, alfa):
        rgba = np.dstack([color, alfa.astype(np.uint8)])
        Image.fromarray(rgba, "RGBA").save(DESTINO / nombre, optimize=True)

    # pelo: todo, con el hueco del cuerpo relleno de blanco
    pelo = limpio.copy()
    hueco = np.array(Image.fromarray(cuerpo.astype(np.uint8) * 255)
                     .filter(ImageFilter.MaxFilter(7))) > 0
    pelo[hueco] = 255
    guardar("pelo.png", pelo, silueta)

    # cuerpo: sin la barbilla, con el cuello alargado hacia arriba
    cue = limpio.copy()
    cue[:756][cuerpo[:756]] = 255
    for x0, x1 in CUELLO_X:
        cue[680:760, x0:x1 + 1] = 20
    guardar("cuerpo.png", cue, np.where(cuerpo, silueta, 0))

    guardar("cara.png", limpio, np.where(cara, 255, 0))

    # vista previa para comprobar que todo encaja
    prev = Image.new("RGBA", (ancho, alto), (255, 0, 255, 255))
    for n in ("pelo.png", "cuerpo.png", "cara.png"):
        capa = Image.open(DESTINO / n)
        prev.alpha_composite(capa)
    prev.save(RAIZ / "arte" / "vista_previa_capas.png")
    print("Capas generadas en", DESTINO)


if __name__ == "__main__":
    DESTINO.mkdir(parents=True, exist_ok=True)
    main()

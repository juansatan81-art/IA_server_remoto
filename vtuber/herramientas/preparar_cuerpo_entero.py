"""Piezas de cuerpo entero para el avatar: lo que hay por debajo del busto.

El avatar se montó como busto (lienzo 1300 x 1140, termina en la cintura). Esto saca de
las capas de cuerpo entero (lara-live2d/capas_finales, lienzo 1792 x 2400 de la maestra)
lo que falta por debajo y lo coloca en el lienzo del avatar, ampliado hacia abajo:

  pelo_largo_abajo.png   la melena por debajo de la cintura (se balancea como la de arriba)
  cuerpo_abajo.png       falda, piernas y zapatos
  brazos_abajo.png       las manos de la pose normal (con otras poses no se dibujan)

La maestra se lleva al avatar con la escala y el desplazamiento medidos al alinearla con
el cuerpo y el pelo del busto (bordes negros: 1.245, -470.2, -181.0). Todo empieza una
fila por encima del final del busto para que no quede rendija.

Uso:  python herramientas/preparar_cuerpo_entero.py   (necesita numpy y pillow)
"""
import json
from pathlib import Path

import numpy as np
from PIL import Image

RAIZ = Path(__file__).resolve().parent.parent
FINALES = RAIZ / "lara-live2d" / "capas_finales"
CAPAS = RAIZ / "web" / "capas"
ESCALA, DX, DY = 1.245, -470.2, -181.0       # maestra -> lienzo del avatar

PIEZAS = {
    "pelo_largo_abajo": ["pelo_atras"],
    "cuerpo_abajo": ["torso", "piernas"],
    "brazos_abajo": ["brazo_I", "brazo_D"],
}


def a_lienzo(capas, ancho, alto):
    """Junta capas de la maestra y las lleva al lienzo del avatar (ancho x alto)."""
    junta = None
    for nombre in capas:
        im = Image.open(FINALES / f"{nombre}.png").convert("RGBA")
        junta = im if junta is None else Image.alpha_composite(junta, im)
    w, h = round(junta.width * ESCALA), round(junta.height * ESCALA)
    grande = junta.resize((w, h), Image.LANCZOS)
    lienzo = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
    lienzo.alpha_composite(grande, (round(DX), round(DY)))
    return lienzo


def main():
    modelo = json.loads((CAPAS / "piezas.json").read_text(encoding="utf-8"))
    ancho, alto_busto = modelo["lienzo"]["ancho"], modelo["lienzo"]["alto"]
    alto = round(2400 * ESCALA + DY) + 10                  # hasta los zapatos
    corte = alto_busto - 1                                  # una fila de solape
    for salida, capas in PIEZAS.items():
        a = np.array(a_lienzo(capas, ancho, alto))
        a[:corte, :, 3] = 0                                 # lo de arriba ya está en el busto
        Image.fromarray(a).save(CAPAS / f"{salida}.png", optimize=True)
        print(f"{salida}.png  {ancho}x{alto}")
    modelo["cuerpo_entero"] = {"alto": alto, "piezas": list(PIEZAS)}
    (CAPAS / "piezas.json").write_text(json.dumps(modelo, ensure_ascii=False, indent=2), encoding="utf-8")
    print("piezas.json: cuerpo_entero.alto =", alto)


if __name__ == "__main__":
    main()

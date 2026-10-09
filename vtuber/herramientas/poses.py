"""Brazos en otras poses: encaja cada dibujo de arte/motion/ sobre Lara y genera sus capas.

    python herramientas/poses.py            # todas las poses de arte/motion/poses.json

Cada pose es un dibujo solo de brazos (fondo blanco o transparente). Se coloca con una
escala y una posición (en poses.json) y:
- su fondo se vuelve transparente, pero lo que queda encerrado entre sus líneas y el
  cuerpo (la parte de arriba del brazo, que el dibujo deja abierta) se rellena de blanco;
- en los hombros el brazo nace por debajo de la manga: ahí se esconde tras el cuerpo.

Salida en web/capas/: brazos_<pose>.png y cuerpo_sin_brazos.png (el torso sin los brazos
de la imagen maestra), que el avatar usa con avatar.brazos('<pose>') o ?brazos=<pose>.
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
MOTION = RAIZ / "arte" / "motion"
CAPAS = RAIZ / "web" / "capas"
sys.path.insert(0, str(Path(__file__).parent))


def cuerpo_sin_brazos():
    """El cuerpo de siempre, pero sin separar los brazos de la maestra."""
    import preparar_piezas as pp
    t = json.loads(pp.ALINEACION.read_text())
    capturas = {}
    original_guardar, original_separar = pp.guardar, pp.separar_brazos
    pp.guardar = lambda n, g, a: capturas.__setitem__(n, (g, a))
    pp.separar_brazos = lambda *args: np.zeros_like(original_separar(*args))
    try:
        pp.montar(t)
    finally:
        pp.guardar, pp.separar_brazos = original_guardar, original_separar
    g, a = capturas["cuerpo"]
    pp.guardar("cuerpo_sin_brazos", g, a)
    return a > 0.5


def fondo_del_dibujo(gris):
    """Blanco conectado con el borde = fondo (lo blanco de dentro del brazo se queda)."""
    claro = (gris > 0.78).astype(np.uint8)
    marco = np.ones((claro.shape[0] + 2, claro.shape[1] + 2), np.uint8)
    marco[1:-1, 1:-1] = claro
    cv2.floodFill(marco, None, (0, 0), 2)
    return marco[1:-1, 1:-1] == 2


def encajar(cfg, torso, tam):
    alto, ancho = tam
    imagen = cv2.imread(str(MOTION / cfg["archivo"]), cv2.IMREAD_UNCHANGED)
    if imagen.ndim == 3 and imagen.shape[2] == 4:      # PNG transparente: lo transparente es fondo
        alfa_dib = imagen[..., 3] / 255.0
        gris = cv2.cvtColor(imagen[..., :3], cv2.COLOR_BGR2GRAY) / 255.0
        gris = gris * alfa_dib + (1 - alfa_dib)
    else:
        gris = cv2.cvtColor(imagen if imagen.ndim == 3 else cv2.cvtColor(imagen, cv2.COLOR_GRAY2BGR),
                            cv2.COLOR_BGR2GRAY) / 255.0
    gris = gris.astype(np.float32)
    fondo = fondo_del_dibujo(gris)

    sx, sy = cfg["escala"] if isinstance(cfg["escala"], list) else (cfg["escala"], cfg["escala"])
    ax, ay = cfg["ancla"]                      # punto del dibujo que va a (centro_x, arriba)
    M = np.float32([[sx, 0, cfg["centro_x"] - ax * sx], [0, sy, cfg["arriba"] - ay * sy]])
    g = cv2.warpAffine(gris, M, (ancho, alto), flags=cv2.INTER_AREA, borderValue=1.0)
    dentro = cv2.warpAffine((~fondo).astype(np.float32), M, (ancho, alto), flags=cv2.INTER_LINEAR) > 0.5
    lineas = g < 0.45

    # lo encerrado entre las líneas del brazo y el cuerpo es la parte de arriba del brazo
    muro = (lineas | torso | dentro).astype(np.uint8)
    libre = np.ones((alto + 2, ancho + 2), np.uint8)
    libre[1:-1, 1:-1] = 1 - muro
    cv2.floodFill(libre, None, (0, 0), 2)
    cerrado = libre[1:-1, 1:-1] == 1

    alfa = (dentro | cerrado) & ~(torso & ~dentro & ~lineas)
    filas = np.arange(alto)[:, None]
    alfa &= ~(torso & (filas < cfg.get("hombro", 0)))        # el brazo nace bajo la manga
    alfa = cv2.GaussianBlur(alfa.astype(np.float32), (3, 3), 0)
    g = np.where(cerrado & ~dentro, 1.0, g)
    return g, alfa


def main():
    import preparar_piezas as pp
    poses = json.loads((MOTION / "poses.json").read_text(encoding="utf-8"))
    torso = cuerpo_sin_brazos()
    for nombre, cfg in poses.items():
        g, a = encajar(cfg, torso, torso.shape)
        pp.guardar(f"brazos_{nombre}", g, a)
        print(f"  brazos_{nombre}.png")


if __name__ == "__main__":
    main()

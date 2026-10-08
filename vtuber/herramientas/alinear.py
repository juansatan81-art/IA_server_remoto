"""Utilidades para limpiar y alinear las piezas dibujadas por separado.

Las piezas llegan con fondo magenta y cada una a su propia escala y posición.
  - desmezclar(): quita el magenta y recupera la transparencia real del trazo.
  - ajustar():    busca la escala y el desplazamiento que hacen coincidir las
                  líneas de una pieza con las de una imagen de referencia
                  (emparejamiento por distancia a las líneas, "chamfer").
"""
import cv2
import numpy as np


def cargar(ruta):
    """Como desmezclar(), pero acepta también PNG con transparencia propia.

    Si quedan restos de magenta en los bordes se tratan igual: g = k·gris y
    R = B = k·gris + (1 - k), así que k = 1 - (R - G) y gris = G / k.
    """
    img = cv2.imread(str(ruta), cv2.IMREAD_UNCHANGED)
    if img.ndim == 2 or img.shape[2] == 3:
        return desmezclar(ruta)
    bgra = img.astype(np.float32) / 255
    b, g, r, a = bgra[..., 0], bgra[..., 1], bgra[..., 2], bgra[..., 3]
    k = np.clip(1 - (np.minimum(r, b) - g), 0, 1)
    gris = np.where(k > 0.02, g / np.maximum(k, 0.02), 1)
    return np.clip(gris, 0, 1), a * k


def desmezclar(ruta):
    """Imagen sobre magenta -> (gris, alfa) en float 0..1.

    Para un dibujo en escala de grises g con opacidad a sobre magenta
    (1, 0, 1): R = B = a·g + (1 - a) y G = a·g. De ahí a = 1 - (R - G).
    """
    bgr = cv2.imread(str(ruta)).astype(np.float32) / 255
    b, g, r = bgr[..., 0], bgr[..., 1], bgr[..., 2]
    alfa = np.clip(1 - (np.minimum(r, b) - g), 0, 1)
    gris = np.where(alfa > 0.02, g / np.maximum(alfa, 0.02), 1)
    return np.clip(gris, 0, 1), alfa


def componentes_nitidas(alfa, cajas):
    """Deja solo los trozos opacos que caen dentro de alguna caja (x0, y0, x1, y1).

    Las neblinas y restos medio borrados se descartan.
    """
    solido = (alfa > 0.85).astype(np.uint8)
    n, etiquetas, stats, _ = cv2.connectedComponentsWithStats(solido, 8)
    dentro = np.zeros(n, bool)
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        cx, cy = x + w / 2, y + h / 2
        dentro[i] = any(x0 <= cx <= x1 and y0 <= cy <= y1 for x0, y0, x1, y1 in cajas)
    mascara = dentro[etiquetas]
    # recupera el borde suave (antialiasing) alrededor de lo que se queda
    mascara = cv2.dilate(mascara.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    return np.where(mascara, alfa, 0)


def lineas(gris, alfa=None, umbral=0.35):
    """Máscara de trazo oscuro (float 0/1)."""
    m = gris < umbral
    if alfa is not None:
        m &= alfa > 0.5
    return m.astype(np.float32)


def _coste(D, xs, ys, s, dx, dy):
    h, w = D.shape
    px = np.clip((xs * s + dx).astype(int), 0, w - 1)
    py = np.clip((ys * s + dy).astype(int), 0, h - 1)
    return float(np.minimum(D[py, px], 15).mean())


def ajustar(ref, pieza, escalas, candidatos=3):
    """Devuelve (error_px, escala, dx, dy) tal que ref ≈ pieza·escala + (dx, dy)."""
    D = cv2.distanceTransform((1 - ref).astype(np.uint8), cv2.DIST_L2, 5)
    ys, xs = np.nonzero(pieza)
    elegidos = np.random.default_rng(0).choice(len(xs), min(6000, len(xs)), replace=False)
    xs, ys = xs[elegidos].astype(float), ys[elegidos].astype(float)
    alto, ancho = ref.shape
    borrosa = cv2.GaussianBlur(ref, (0, 0), 6)
    recorte = pieza[int(ys.min()):int(ys.max()) + 1, int(xs.min()):int(xs.max()) + 1]
    mejor = None
    for s in escalas:
        T = cv2.resize(recorte, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        if T.shape[0] >= alto or T.shape[1] >= ancho:
            continue
        res = cv2.matchTemplate(borrosa, cv2.GaussianBlur(T, (0, 0), 6), cv2.TM_CCOEFF_NORMED)
        for _ in range(candidatos):
            _, _, _, p = cv2.minMaxLoc(res)
            res[max(0, p[1] - 20):p[1] + 20, max(0, p[0] - 20):p[0] + 20] = -1
            sol = _afinar(D, xs, ys, s, p[0] - xs.min() * s, p[1] - ys.min() * s)
            if mejor is None or sol[0] < mejor[0]:
                mejor = sol
    return mejor


def _afinar(D, xs, ys, s, dx, dy):
    c = _coste(D, xs, ys, s, dx, dy)
    for paso in (4, 2, 1, 0.5, 0.25):
        mejora = True
        while mejora:
            mejora = False
            for ds, ddx, ddy in ((paso * 0.002, 0, 0), (-paso * 0.002, 0, 0),
                                 (0, paso, 0), (0, -paso, 0), (0, 0, paso), (0, 0, -paso)):
                n = _coste(D, xs, ys, s + ds, dx + ddx, dy + ddy)
                if n < c - 1e-5:
                    c, s, dx, dy = n, s + ds, dx + ddx, dy + ddy
                    mejora = True
    return c, s, dx, dy


def componer(t1, t2):
    """Transformación que aplica t1 y luego t2 (cada una: escala, dx, dy)."""
    s1, x1, y1 = t1
    s2, x2, y2 = t2
    return s1 * s2, x1 * s2 + x2, y1 * s2 + y2


def invertir(t):
    s, dx, dy = t
    return 1 / s, -dx / s, -dy / s


def colocar(img, t, tamano, interp=cv2.INTER_AREA):
    """Aplica escala+desplazamiento y devuelve una imagen del tamaño (ancho, alto)."""
    s, dx, dy = t
    M = np.float32([[s, 0, dx], [0, s, dy]])
    if s > 1:
        interp = cv2.INTER_CUBIC
    return cv2.warpAffine(img, M, tamano, flags=interp, borderMode=cv2.BORDER_CONSTANT, borderValue=0)


def ajustar_desde(ref, pieza, semillas):
    """Como ajustar(), pero partiendo de estimaciones (escala, dx, dy) conocidas."""
    D = cv2.distanceTransform((1 - ref).astype(np.uint8), cv2.DIST_L2, 5)
    ys, xs = np.nonzero(pieza)
    elegidos = np.random.default_rng(0).choice(len(xs), min(6000, len(xs)), replace=False)
    xs, ys = xs[elegidos].astype(float), ys[elegidos].astype(float)
    return min((_afinar(D, xs, ys, *s) for s in semillas), key=lambda r: r[0])

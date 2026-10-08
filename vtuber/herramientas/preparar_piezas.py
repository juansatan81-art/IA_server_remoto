"""Monta las capas del avatar a partir de las piezas dibujadas (arte/piezas/).

Todo se lleva al sistema de coordenadas del busto original (1254 x 1200), que
es el que usa web/avatar.js. La imagen maestra hace de puente para las piezas
de cuerpo entero.

    python herramientas/preparar_piezas.py            # usa la alineación guardada
    python herramientas/preparar_piezas.py --alinear  # la vuelve a calcular

Resultado: web/capas/*.png y web/capas/piezas.json
Necesita: pip install -r herramientas/requisitos.txt
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np

import alinear as al

RAIZ = Path(__file__).resolve().parent.parent
PIEZAS = RAIZ / "arte" / "piezas"
DESTINO = RAIZ / "web" / "capas"
ALINEACION = PIEZAS / "alineacion.json"
W, H = 1254, 1200

F = {
    "maestra": "La imagen maestra_v4.jpg",
    "torso": "2.13c · Torso SIN el pecho (lo que queda debajo cuando el pecho se mueve).jpg",
    "pecho": "2.13b · Pecho solo (para su física · busto, decidido el 2026-10-07).jpg",
    "pelo_largo": "2.2 · Pelo de atrás(salio al revez de la original podrias hacerle espejo a esta foto).jpg",
    "pelo_cabeza": "Pelo de atrás_v2.jpg",
    "flequillo": "2.3 · Flequillo completo.jpg",
    "ojos": "2.5b · Contorno del ojo, completo (el ojo SIN la forma negra · para mover la mirada).jpg",
    "ojo_cerrado": "2.6 · Ojo cerrado.jpg",
    "ojo_feliz": "2.7 · Ojo sonriente.jpg",
    "boca_sonrisa": "2.10 · Boca sonriente.jpg",
    "boca_triste": "2.11 · Boca triste o enfadada.jpg",
    "boca_a": "Boca abierta (A).jpg",
    "boca_o": "Boca media (O).jpg",
    "rubor": "2.4 · Rubor.jpg",
    # versiones retocadas a mano (ya en su sitio: se alinean contra las anteriores)
    "cara_editada": "3.1 · Cara (editada).png",
    "pelo_cabeza_editado": "3.2 · Pelo de atrás (editado).png",
    "flequillo_editado": "3.3 · Flequillo (editado).png",
}

# Zonas útiles de cada pieza (x0, y0, x1, y1), en sus propias coordenadas
CAJAS = {
    "torso": [(0, 0, 1792, 2400)],
    "pecho": [(690, 360, 1130, 770)],
    "pelo_largo": [(0, 0, 1792, 2400)],
    "pelo_cabeza": [(0, 0, 1792, 2400)],
    "flequillo": [(380, 550, 1300, 1000)],
    "ojos": [(250, 740, 1550, 1120)],
    "ojo_cerrado": [(370, 820, 1420, 1010)],
    "ojo_feliz": [(200, 660, 1620, 930)],
    "boca_sonrisa": [(800, 880, 1000, 990)],
    "boca_triste": [(820, 510, 970, 600)],
    "boca_a": [(740, 1000, 1050, 1400)],
    "boca_o": [(800, 1100, 990, 1340)],
    "rubor": [(420, 1140, 1360, 1320)],
    # en las retocadas se descarta lo casi transparente (bordes de capa del programa de dibujo)
    "cara_editada": [(0, 0, 10000, 10000)],
    "pelo_cabeza_editado": [(0, 0, 10000, 10000)],
    "flequillo_editado": [(0, 0, 10000, 10000)],
}


def pieza(nombre, espejo=False):
    gris, alfa = al.cargar(PIEZAS / F[nombre])
    if nombre in CAJAS:
        alfa = al.componentes_nitidas(alfa, CAJAS[nombre])
    if espejo:
        gris, alfa = gris[:, ::-1].copy(), alfa[:, ::-1].copy()
    return gris, alfa


# Estimaciones de partida (escala, dx, dy); --alinear las afina contra el dibujo.
# maestra: maestra -> busto. torso, pecho, pelo_largo: pieza -> maestra.
# El resto: pieza -> busto.
SEMILLAS = {
    "maestra": (1.54, -761.6, -222.4),
    "torso": (0.85, 134.5, 359.9),
    "pecho": (0.85, 134.5, 359.9),
    "pelo_largo": (0.6485, 329.1, 72.7),
    "pelo_cabeza": (0.558, 127.1, -39.2),
    "flequillo": (0.70, 0.1, -204.4),
    "ojos": (0.41, 260.8, 137.9),
    "cara_editada": (0.997, 185.3, 22.8),
    "pelo_cabeza_editado": (1.115, 128.9, -38.7),
    "flequillo_editado": (0.833, 6.3, -198.6),
}


def calcular_alineacion():
    busto = cv2.imread(str(RAIZ / "arte" / "busto.png"), cv2.IMREAD_GRAYSCALE)[:H] / 255.0
    ref_busto = al.lineas(busto)
    g, a = al.desmezclar(PIEZAS / F["maestra"])
    lin_maestra = al.lineas(g, np.where(a < 0.35, 0, a))
    # para los ojos sirve el borde de las formas negras del busto
    negro = (busto < 0.25).astype(np.uint8)
    negro[:455] = 0
    negro[605:] = 0
    ref_ojos = (cv2.morphologyEx(negro, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0).astype(np.float32)

    def variantes(s, dx, dy):
        return [(s * k, dx + ox, dy + oy) for k in (0.99, 1, 1.01) for ox in (-8, 0, 8) for oy in (-8, 0, 8)]

    t = {}
    m = lin_maestra.copy()
    m[:180] = 0
    m[920:] = 0
    t["maestra"] = al.ajustar_desde(ref_busto, m, variantes(*SEMILLAS["maestra"]))
    for nombre, ref, espejo in (("torso", lin_maestra, False), ("pecho", lin_maestra, False),
                                ("pelo_largo", lin_maestra, True), ("pelo_cabeza", ref_busto, False),
                                ("flequillo", ref_busto, False), ("ojos", ref_ojos, False)):
        gg, aa = pieza(nombre, espejo)
        t[nombre] = al.ajustar_desde(ref, al.lineas(gg, aa), variantes(*SEMILLAS[nombre]))
    # las piezas retocadas a mano se alinean contra la versión anterior ya colocada
    for nueva, vieja in (("pelo_cabeza_editado", "pelo_cabeza"), ("flequillo_editado", "flequillo")):
        vg, va = colocar_pieza(*pieza(vieja), t[vieja][1:], (W, H))
        gg, aa = pieza(nueva)
        t[nueva] = al.ajustar_desde(al.lineas(vg, va), al.lineas(gg, aa), variantes(*SEMILLAS[nueva]))
    ref_cara = np.zeros_like(ref_busto)
    ref_cara[520:760, 330:935] = ref_busto[520:760, 330:935]     # contorno de la cara bajo los ojos
    gg, aa = pieza("cara_editada")
    t["cara_editada"] = al.ajustar_desde(ref_cara, al.lineas(gg, aa), variantes(*SEMILLAS["cara_editada"]))
    for k, v in t.items():
        print(f"  {k:20} error {v[0]:.2f}px  escala {v[1]:.3f}  dx {v[2]:.1f}  dy {v[3]:.1f}")
    datos = {k: {"error": round(v[0], 3), "escala": v[1], "dx": v[2], "dy": v[3]} for k, v in t.items()}
    ALINEACION.write_text(json.dumps(datos, indent=2, ensure_ascii=False))
    return datos


# ------------------------------------------------------------------ montaje
# Lienzo final: recorte del busto de la maestra, ampliado
RECORTE = (380, 150, 1420, 1062)
AMPLIA = 1.25
LW, LH = round((RECORTE[2] - RECORTE[0]) * AMPLIA), round((RECORTE[3] - RECORTE[1]) * AMPLIA)
M2L = (AMPLIA, -RECORTE[0] * AMPLIA, -RECORTE[1] * AMPLIA)     # maestra -> lienzo

# Pegatinas: (pieza, caja de la pieza, centro en coordenadas del busto, escala)
PEGATINAS = {
    "ojo_cerrado_izq": ("ojo_cerrado", (370, 820, 850, 1010), (489, 560), 0.41),
    "ojo_cerrado_der": ("ojo_cerrado", (940, 820, 1420, 1010), (774, 560), 0.41),
    "ojo_feliz_izq": ("ojo_feliz", (200, 660, 810, 930), (489, 540), 0.41),
    "ojo_feliz_der": ("ojo_feliz", (1020, 660, 1620, 930), (774, 540), 0.41),
    "boca_sonrisa": ("boca_sonrisa", None, (632, 646), 0.64),
    "boca_triste": ("boca_triste", None, (632, 650), 0.66),
    "boca_o": ("boca_o", None, (632, 655), 0.40),
    "boca_a": ("boca_a", None, (632, 668), 0.38),
    "rubor_izq": ("rubor", (420, 1140, 660, 1320), (432, 642), 0.60),
    "rubor_der": ("rubor", (1130, 1140, 1360, 1320), (831, 642), 0.60),
}


def a_rgba(gris, alfa):
    g = (np.clip(gris, 0, 1) * 255).astype(np.uint8)
    alfa = np.where(alfa < 0.08, 0, alfa)      # sin restos casi invisibles
    a = (np.clip(alfa, 0, 1) * 255).astype(np.uint8)
    return np.dstack([g, g, g, a])


def guardar(nombre, gris, alfa):
    cv2.imwrite(str(DESTINO / f"{nombre}.png"), cv2.cvtColor(a_rgba(gris, alfa), cv2.COLOR_RGBA2BGRA))


def colocar_pieza(gris, alfa, t, tam):
    return (al.colocar(gris.astype(np.float32), t, tam), al.colocar(alfa.astype(np.float32), t, tam))


def separar_brazos(g, a, torso_a, pelo_g, pelo_a):
    """Brazos de la maestra: zonas claras que no son torso ni pelo, bajo los hombros."""
    claro = ((g > 0.5) & (a > 0.5)).astype(np.uint8)
    n, etiq, stats, cent = cv2.connectedComponentsWithStats(claro, 4)
    contorno_pelo = cv2.dilate(((pelo_g < 0.35) & (pelo_a > 0.5)).astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    torso = torso_a > 0.5
    brazos = np.zeros_like(claro, bool)
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < 150 or cent[i][1] < 690 or area > 400000:
            continue
        zona = etiq[y:y + h + 1, x:x + w + 1] == i
        if torso[y:y + h + 1, x:x + w + 1][zona].mean() > 0.5:
            continue
        borde = cv2.dilate(zona.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
        borde &= ~zona
        if contorno_pelo[y:y + h + 1, x:x + w + 1][borde].mean() < 0.12:
            brazos[y:y + h + 1, x:x + w + 1] |= zona
    # los trazos que rodean cada brazo también son del brazo
    brazos = cv2.dilate(brazos.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    return brazos & (a > 0.3)


def alargar_cuello(g, a, alto=85):
    """Prolonga hacia arriba las dos líneas del cuello y rellena de blanco entre ellas.

    Así, aunque la cabeza suba o se ladee, bajo la barbilla siempre hay cuello.
    """
    filas = np.flatnonzero((a > 0.5).any(1))
    y0 = filas.min() + 14                      # justo bajo el borde del cuello de la camisa
    centro = LW // 2
    trozo = (g[y0:y0 + 16, centro - 90:centro + 90] < 0.35) & (a[y0:y0 + 16, centro - 90:centro + 90] > 0.5)
    cols = np.flatnonzero(trozo.mean(0) > 0.6) + centro - 90
    izq = cols[cols < centro]
    der = cols[cols > centro]
    xi0, xi1 = izq.min(), izq.max()
    xd0, xd1 = der.min(), der.max()
    arriba = y0 - alto
    g, a = g.copy(), a.copy()
    g[arriba:y0 + 4, xi0:xd1 + 1] = 1          # relleno blanco (tapa también el borde del cuello)
    a[arriba:y0 + 4, xi0:xd1 + 1] = 1
    for x0, x1 in ((xi0, xi1), (xd0, xd1)):    # las dos líneas, del mismo grosor que las originales
        g[arriba:y0 + 4, x0:x1 + 1] = 0.05
    return g, a


def montar(t):
    DESTINO.mkdir(parents=True, exist_ok=True)
    T = {k: (v["escala"], v["dx"], v["dy"]) for k, v in t.items()}
    maestra_a_busto = T["maestra"]
    busto_a_lienzo = al.componer(al.invertir(maestra_a_busto), M2L)
    tam_m = (1792, 2400)

    # --- en coordenadas de la maestra
    g, a = al.desmezclar(PIEZAS / F["maestra"])
    a = np.where(a < 0.35, 0, a)          # el fondo de la maestra tiene ruido de compresión
    tg, ta = colocar_pieza(*pieza("torso"), T["torso"], tam_m)
    pg, pa = colocar_pieza(*pieza("pecho"), T["torso"], tam_m)   # mismo dibujo que el torso
    lg, la = colocar_pieza(*pieza("pelo_largo", espejo=True), T["pelo_largo"], tam_m)
    brazos = separar_brazos(g, a, ta, lg, la)
    # la curva del pecho es del pecho, no del brazo: si se queda en el cuerpo,
    # al rebotar el pecho aparece un contorno doble
    brazos &= ~(pa > 0.3)

    # cuerpo = brazos de la maestra + torso sin pecho encima
    cg = np.where(brazos, g, 1.0)
    ca = np.where(brazos, a, 0.0)
    cg = ta * tg + (1 - ta) * cg
    ca = np.maximum(ca, ta)

    def al_lienzo(gris, alfa):
        return colocar_pieza(gris, alfa, M2L, (LW, LH))

    lg, la = al_lienzo(lg, la)
    # lo que queda bajo el pelo de la cabeza no se ve: fuera, para que no asome su contorno
    hg, ha = colocar_pieza(*pieza("pelo_cabeza_editado"),
                           al.componer(T["pelo_cabeza_editado"], busto_a_lienzo), (LW, LH))
    # el pelo largo de la maestra es algo más ancho que el de la cabeza: alrededor
    # de la cabeza se quita para que no salga un contorno doble
    tapado = cv2.dilate((ha > 0.5).astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (81, 81))) > 0
    filas = np.flatnonzero((ha > 0.5).any(1))
    tapado[filas.max() - 60:] = False
    tapado[:filas.max() - 60] = True     # por encima de las puntas manda el pelo de la cabeza
    la = np.where(tapado, 0, la)
    guardar("pelo_largo", lg, la)
    cg, ca = alargar_cuello(*al_lienzo(cg, ca))
    guardar("cuerpo", cg, ca)
    arriba_cuerpo = int(np.flatnonzero((ca > 0.5).any(1)).min())
    pg, pa = al_lienzo(pg, pa)
    guardar("pecho", pg, pa)
    filas_pecho = np.flatnonzero((pa > 0.5).any(1))

    # --- cabeza, en coordenadas del busto
    tam_b = (W, H)
    for capa, nombre in (("pelo_cabeza", "pelo_cabeza_editado"), ("flequillo", "flequillo_editado"),
                         ("cara", "cara_editada")):
        gg, aa = pieza(nombre)
        gg = np.where(gg > 0.8, 1, gg)     # rayitas grises casi blancas del relleno: fuera
        guardar(capa, *colocar_pieza(gg, aa, T[nombre], tam_b))
    guardar("ojos_blanco", *colocar_pieza(*pieza("ojos"), T["ojos"], tam_b))

    pegatinas = {}
    for nombre, (origen, caja, (cx, cy), esc) in PEGATINAS.items():
        gg, aa = pieza(origen)
        if caja:
            x0, y0, x1, y1 = caja
            m = np.zeros_like(aa)
            m[y0:y1, x0:x1] = aa[y0:y1, x0:x1]
            aa = m
        ys, xs = np.nonzero(aa > 0.05)
        x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
        gg = cv2.resize(gg[y0:y1, x0:x1].astype(np.float32), None, fx=esc, fy=esc, interpolation=cv2.INTER_AREA)
        aa = cv2.resize(aa[y0:y1, x0:x1].astype(np.float32), None, fx=esc, fy=esc, interpolation=cv2.INTER_AREA)
        guardar(nombre, gg, aa)
        h, w = aa.shape
        pegatinas[nombre] = {"x": round(cx - w / 2, 1), "y": round(cy - h / 2, 1), "w": w, "h": h}

    modelo = {
        "lienzo": {"ancho": LW, "alto": LH},
        "busto_a_lienzo": dict(zip(("escala", "dx", "dy"), busto_a_lienzo)),
        "pegatinas": pegatinas,
        "pecho": {"arriba": int(filas_pecho.min()), "abajo": int(filas_pecho.max())},
        "cuerpo_arriba": arriba_cuerpo,
    }
    (DESTINO / "piezas.json").write_text(json.dumps(modelo, indent=2, ensure_ascii=False))
    print("Capas en", DESTINO)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--alinear", action="store_true")
    args = ap.parse_args()
    t = calcular_alineacion() if args.alinear or not ALINEACION.exists() else json.loads(ALINEACION.read_text())
    montar(t)


if __name__ == "__main__":
    main()

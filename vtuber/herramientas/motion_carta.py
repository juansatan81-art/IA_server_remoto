"""Motion graphic «la carta», copiando el ritmo de las referencias (arte/motion/README.md).

    python herramientas/motion_carta.py                 # vídeo entero (lo que haya de poses)
    python herramientas/motion_carta.py --hasta 2.3     # solo los primeros 2,3 s (prueba)

Graba a Lara con el avatar (fotograma a fotograma, herramientas/grabar_avatar.js) y monta
encima los efectos: fondo con su copia gigante, contorno brillante, medidor de corazones,
rebote de cámara al ritmo, destellos en los cambios de pose y fundidos.
Necesita Node con Playwright y ffmpeg. Sale en arte/motion/salida/.
"""
import argparse
import functools
import http.server
import json
import math
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

import cv2
import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
MOTION = RAIZ / "arte" / "motion"
FPS = 60
LADO = 1080
DURACION = 14.9
BPM = 120                              # medido: un rebote cada 0,5 s
FUERZA = 1.0                           # cuánto se deforman pelo, flequillo, brazos y cuerpo
ACENTO = (232, 160, 30)                # BGR (azul como la referencia)
FONDO = (250, 244, 238)

# (inicio de la pose en s, pose). Antes de cada cambio hay un destello.
ESCENAS = [(0.0, "pose1"), (2.20, "pose2"), (4.02, "pose3"), (5.85, "pose4"),
           (7.40, "pose1"), (9.25, "pose2"), (11.13, "pose3"), (12.92, "pose4")]
DESTELLOS = [1.83, 3.78, 5.23, 5.43, 8.87, 10.95, 12.38, 12.58]
ESPEJO_DESDE = 7.40                    # la segunda mitad, con la composición en espejo
LLENADO = {"pose1": 0.25, "pose2": 0.5, "pose3": 0.75, "pose4": 1.0}   # medidor de corazones


def pose_en(t, disponibles):
    pose = ESCENAS[0][1]
    for inicio, p in ESCENAS:
        if t >= inicio:
            pose = p
    return pose if pose in disponibles else sorted(disponibles)[0]


def rebote(t):
    """Cámara: baja ~22 px en cada tiempo y vuelve (curva medida en la referencia)."""
    return 0.5 * (1 + math.cos(2 * math.pi * BPM / 60 * (t - 1.0)))


def guion(duracion, disponibles):
    fotos = []
    for i in range(int(duracion * FPS)):
        t = i / FPS
        # la cabeza se ladea 0..2,5° adelantada ~0,17 s al rebote; en la carta, al otro lado
        lado = -1 if pose_en(t, disponibles) == "pose4" else 1
        grados = 1.25 * (1 + math.cos(2 * math.pi * BPM / 60 * (t - 0.83))) * lado
        x = 3 * math.sin(2 * math.pi * BPM / 60 * (t - 0.7))
        pose = pose_en(t, disponibles)
        fotos.append({"brazos": pose, "cabeza": [x, 0, grados / 3.44],
                      "ritmo": {"bpm": BPM, "fuerza": FUERZA, "tiempo": t, "ancla": 1.0},
                      "emocion": "avergonzada" if pose in ("pose3", "pose4") else "neutral"})
    return {"fps": FPS, "fotogramas": fotos}


def grabar(guion_, carpeta):
    """Sirve web/ en un puerto local y graba el avatar con Node + Playwright."""
    class Callado(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    manejador = functools.partial(Callado, directory=str(RAIZ / "web"))
    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), manejador)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    archivo = carpeta / "guion.json"
    archivo.write_text(json.dumps(guion_))
    url = f"http://127.0.0.1:{servidor.server_port}/avatar.html?emocion=neutral"
    try:
        subprocess.run(["node", str(RAIZ / "herramientas" / "grabar_avatar.js"), url, str(archivo),
                        str(carpeta / "frames")], check=True)
    finally:
        servidor.shutdown()


# ------------------------------------------------------------------ dibujos fijos
def medidor(llenado):
    """Arco de corazones con flecha (a doble tamaño y reducido, para bordes suaves)."""
    k = 2
    img = np.zeros((520 * k, 520 * k, 4), np.uint8)
    c = (260 * k, 300 * k)
    r = 170 * k
    tramos = 8
    for i in range(tramos):
        a0, a1 = 200 + i * (140 / tramos) + 1.5, 200 + (i + 1) * (140 / tramos) - 1.5
        lleno = (i + 0.5) / tramos <= llenado
        color = (*ACENTO, 255) if lleno else (255, 255, 255, 255)
        cv2.ellipse(img, c, (r, r), 0, a0, a1, (40, 40, 40, 255), 46 * k, cv2.LINE_AA)
        cv2.ellipse(img, c, (r, r), 0, a0, a1, color, 34 * k, cv2.LINE_AA)
    def corazon(cx, cy, tam, color):
        pts = [(cx + tam * 16 * math.sin(u) ** 3 / 17, cy - tam * (13 * math.cos(u) - 5 * math.cos(2 * u)
               - 2 * math.cos(3 * u) - math.cos(4 * u)) / 17) for u in np.linspace(0, 2 * math.pi, 80)]
        cv2.fillPoly(img, [np.int32(pts)], color, cv2.LINE_AA)
    fin = math.radians(340)
    corazon(int(c[0] + (r + 20 * k) * math.cos(fin)), int(c[1] + (r + 20 * k) * math.sin(fin)) - 30 * k,
            46 * k, (*ACENTO, 255))
    corazon(int(c[0] + (r - 40 * k) * math.cos(fin)) - 70 * k, int(c[1] + (r) * math.sin(fin)) - 90 * k,
            26 * k, (*ACENTO, 255))
    # flecha: gira según lo lleno (de izquierda a arriba)
    ang = math.radians(180 + 90 * llenado)
    punta = (int(c[0] + (r - 60 * k) * math.cos(ang)), int(c[1] + (r - 60 * k) * math.sin(ang)))
    cv2.arrowedLine(img, c, punta, (40, 40, 40, 255), 22 * k, cv2.LINE_AA, tipLength=0.28)
    cv2.arrowedLine(img, c, punta, (*ACENTO, 255), 12 * k, cv2.LINE_AA, tipLength=0.28)
    return cv2.resize(img, (520, 520), interpolation=cv2.INTER_AREA)


def pegar(lienzo, rgba, x, y, opacidad=1.0):
    """Pega una imagen RGBA (uint8) sobre el lienzo BGR float en (x, y), recortando bordes."""
    h, w = rgba.shape[:2]
    x0, y0, x1, y1 = max(0, x), max(0, y), min(LADO, x + w), min(LADO, y + h)
    if x0 >= x1 or y0 >= y1:
        return
    trozo = rgba[y0 - y:y1 - y, x0 - x:x1 - x].astype(np.float32) / 255
    a = trozo[..., 3:] * opacidad
    lienzo[y0:y1, x0:x1] = lienzo[y0:y1, x0:x1] * (1 - a) + trozo[..., :3] * a


def componer(carpeta, duracion, salida):
    fotos = sorted((carpeta / "frames").glob("*.png"))
    medidores = {p: medidor(v) for p, v in LLENADO.items()}
    ffmpeg = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
                               "-s", f"{LADO}x{LADO}", "-r", str(FPS), "-i", "-", "-c:v", "libx264",
                               "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", str(salida)],
                              stdin=subprocess.PIPE)
    disponibles = {p.stem for p in MOTION.glob("pose*.*")}
    for i, foto in enumerate(fotos):
        t = i / FPS
        lara = cv2.imread(str(foto), cv2.IMREAD_UNCHANGED)          # 1300x1140 BGRA
        cam = rebote(t)
        dy = int(round(22 * cam))
        zoom = 1 + 0.006 * cam

        lienzo = np.empty((LADO, LADO, 3), np.float32)
        lienzo[:] = np.array(FONDO, np.float32) / 255
        # su copia gigante y desvaída al fondo, al otro lado
        esc_f = 1.55 * zoom
        fantasma = cv2.resize(lara, None, fx=esc_f, fy=esc_f, interpolation=cv2.INTER_AREA)
        fantasma = cv2.GaussianBlur(fantasma, (0, 0), 2)
        pegar(lienzo, fantasma, int(-560 + 10 * t), int(-330 + dy * 0.6), 0.16)
        # franjas de color arriba y abajo
        lienzo[:44] = np.array(ACENTO, np.float32) / 255
        lienzo[-44:] = np.array(ACENTO, np.float32) / 255

        pose = pose_en(t, disponibles)
        m = medidores.get(pose, medidores["pose1"])
        m = cv2.resize(m, None, fx=0.78, fy=0.78, interpolation=cv2.INTER_AREA)
        pegar(lienzo, m, -30, 300 + dy, 1.0)

        # Lara, con contorno blanco y brillo de color alrededor
        esc = 0.84 * zoom
        figura = cv2.resize(lara, None, fx=esc, fy=esc, interpolation=cv2.INTER_AREA)
        fx, fy = int(LADO * 0.67 - 660 * esc), LADO - figura.shape[0] + 10 + dy
        alfa = figura[..., 3]
        borde = cv2.dilate(alfa, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (17, 17)))
        brillo = cv2.GaussianBlur(cv2.dilate(alfa, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31))),
                                  (0, 0), 14)
        pegar(lienzo, np.dstack([np.full_like(alfa, ACENTO[0]), np.full_like(alfa, ACENTO[1]),
                                 np.full_like(alfa, ACENTO[2]), brillo]), fx, fy, 0.7)
        pegar(lienzo, np.dstack([np.full_like(alfa, 255)] * 3 + [borde]), fx, fy)
        pegar(lienzo, figura, fx, fy)

        # destellos blancos en los cambios de pose
        blanco = 0.0
        for d in DESTELLOS:
            if 0 <= t - d < 0.45:
                blanco = max(blanco, 0.85 * math.exp(-(t - d) / 0.11))
        lienzo = lienzo * (1 - blanco) + blanco
        # fundidos: entra desde negro y se va a negro
        negro = max(0.0, 1 - t / 0.7) if t < 0.7 else (min(1.0, (t - 14.32) / 0.5) if t > 14.32 else 0.0)
        lienzo *= 1 - negro
        if t >= ESPEJO_DESDE:
            lienzo = lienzo[:, ::-1]
        ffmpeg.stdin.write((np.clip(lienzo, 0, 1) * 255).astype(np.uint8).tobytes())
    ffmpeg.stdin.close()
    ffmpeg.wait()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hasta", type=float, default=DURACION, help="segundos a generar")
    ap.add_argument("--salida", default=str(MOTION / "salida" / "la_carta.mp4"))
    args = ap.parse_args()
    disponibles = {p.stem for p in MOTION.glob("pose*.*")}
    salida = Path(args.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    carpeta = Path(tempfile.mkdtemp(prefix="motion_"))
    try:
        grabar(guion(args.hasta, disponibles), carpeta)
        componer(carpeta, args.hasta, salida)
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)
    print(f"  Vídeo: {salida}")


if __name__ == "__main__":
    main()

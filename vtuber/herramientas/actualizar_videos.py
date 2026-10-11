"""Añade a memoria/videos.json las fichas de los vídeos nuevos del canal.

Mira los vídeos públicos del canal con yt-dlp, y a los que aún no tienen ficha les
prepara una a partir de lo publicado (título, fecha, descripción y capítulos), igual que
las primeras doce. Las fichas nuevas llevan "revisar": true para que las mires: sobre
todo las palabras_clave (palabras concretas que traen la ficha solas: «capibara»,
«Xiaro»...) y los temas (palabras generales que solo cuentan si hablan de sus vídeos).
Lara las usa en cuanto el servidor vuelve a arrancar.

Uso:  python herramientas/actualizar_videos.py          (necesita yt-dlp instalado)
      python herramientas/actualizar_videos.py --ver    (solo dice qué vídeos faltan)
"""
import argparse
import json
import re
import subprocess
from pathlib import Path

CANAL = "https://www.youtube.com/@soylaraai1/videos"
FICHAS = Path(__file__).resolve().parent.parent / "memoria" / "videos.json"
# lo que va después de esto en la descripción no es del vídeo (fuentes, créditos...)
CORTE = re.compile(r"\n\s*(FUENTES|Fuentes|CRÉDITOS|Créditos|MÚSICA|Música|ATRIBUCIONES|Atribuciones|CAPÍTULOS)\b")


def ytdlp(*args):
    r = subprocess.run(["yt-dlp", "--add-header", "Accept-Language: es-ES,es;q=0.9", *args],
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[-300:])
    return r.stdout


def ficha(vid):
    d = json.loads(ytdlp("--skip-download", "-J", f"https://www.youtube.com/watch?v={vid}"))
    desc = CORTE.split(d.get("description", ""))[0]
    lineas = [l.strip() for l in desc.splitlines()]
    puntos = [l.lstrip("•-· ").strip() for l in lineas if l.startswith(("•", "- ", "· "))]
    parrafos = [p.replace("\n", " ").strip() for p in re.split(r"\n\s*\n", desc) if p.strip()]
    intro = next((p for p in parrafos if not p.startswith(("•", "- ", "· "))), "")
    f = d.get("upload_date", "")
    return {
        "titulo": d["title"],
        "fecha": f"{f[:4]}-{f[4:6]}-{f[6:]}" if len(f) == 8 else f,
        "url": f"https://youtu.be/{vid}",
        "tipo": "divulgación",
        "resumen": intro,
        "datos_clave": puntos,
        "capitulos": [c["title"] for c in (d.get("chapters") or [])],
        "palabras_clave": [],
        "temas": [],
        "revisar": True,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ver", action="store_true", help="solo listar los vídeos que no tienen ficha")
    args = ap.parse_args()

    fichas = json.loads(FICHAS.read_text(encoding="utf-8")) if FICHAS.exists() else []
    tienen = {f["url"].rsplit("/", 1)[-1] for f in fichas}
    publicados = [l.split(" | ", 1) for l in ytdlp("--flat-playlist", "--print", "%(id)s | %(title)s", CANAL).splitlines() if " | " in l]
    nuevos = [(i, t) for i, t in publicados if i not in tienen]
    if not nuevos:
        print(f"Todo al día: {len(fichas)} fichas para {len(publicados)} vídeos públicos.")
        return
    for vid, titulo in nuevos:
        print(f"Falta: {titulo}  (https://youtu.be/{vid})")
    if args.ver:
        return
    for vid, titulo in nuevos:
        fichas.append(ficha(vid))
        print(f"  + ficha preparada: {titulo}")
    fichas.sort(key=lambda f: f.get("fecha", ""))
    FICHAS.write_text(json.dumps(fichas, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nGuardado en {FICHAS}. Revisa las que tienen \"revisar\": true (sobre todo palabras_clave)"
          " y reinicia el servidor.")


if __name__ == "__main__":
    main()

"""Estudia un directo de YouTube: lo que dice la streamer y el chat, intercalados por tiempo.

Para aprender cómo otras VTubers y streamers atienden al chat (y, más adelante, sacar
ejemplos). Con el enlace de un directo archivado:
  1. descarga el audio y la repetición del chat (yt-dlp; el chat solo existe si el vídeo
     fue un directo en YouTube y la repetición está activada),
  2. transcribe la voz con faster-whisper (en la gráfica si encuentra CUDA),
  3. escribe en memoria/estudio/<id>/:
       linea_tiempo.txt  voz y chat mezclados por segundo:
                           [12:05] >> STREAMER: ...
                           [12:01]    @usuario: ...
       pares.jsonl       candidatos «mensaje del chat -> lo que respondió», cuando la
                         streamer dice el nombre del usuario o repite palabras del mensaje
                         poco después (es una pista, no seguro: hay que revisarlos)
       info.json         título, canal, duración, cuántos mensajes...

memoria/ no va a git: aquí hay mensajes de otras personas y contenido de otros canales.
Es material de estudio; no se publica ni se usa tal cual para entrenar sin revisarlo.

Uso:  python herramientas/estudiar_directo.py URL [URL...]
      python herramientas/estudiar_directo.py URL --idioma en
      python herramientas/estudiar_directo.py URL --cuda RUTA   (carpeta con nvidia/cublas/bin...)
Necesita yt-dlp y faster-whisper (pip install faster-whisper). En la gráfica además hacen
falta las librerías de NVIDIA: pip install nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*"
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

ESTUDIO = Path(__file__).resolve().parent.parent / "memoria" / "estudio"
VENTANA = (2, 45)    # la respuesta llega entre 2 y 45 s después del mensaje
VACIAS = set("""a al algo ante como con cual de del el ella en era es esa ese eso esta este esto
estoy fue ha hay la las le les lo los me mi muy no nos o para pero por que se si sin su sus
te ti tu un una uno y ya yo the a an and are is it i you to of in that this for on with was
be my me so do just like what""".split())


def ytdlp(*args):
    r = subprocess.run(["yt-dlp", "-q", "--no-progress", "--no-warnings", *args],
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[-400:])
    return r.stdout


def descargar(url, carpeta):
    info = json.loads(ytdlp("-J", "--no-playlist", url))
    vid = info["id"]
    destino = carpeta / vid
    destino.mkdir(parents=True, exist_ok=True)
    if not list(destino.glob("audio.*")):
        ytdlp("-f", "ba[ext=m4a]/ba", "-o", str(destino / "audio.%(ext)s"), url)
    if info.get("live_status") == "was_live" and not (destino / "chat.json").exists():
        try:
            ytdlp("--skip-download", "--write-subs", "--sub-langs", "live_chat",
                  "-o", str(destino / "chat"), url)
            for f in destino.glob("chat*.live_chat.json"):
                f.replace(destino / "chat.json")
        except RuntimeError as err:
            print(f"  sin chat: {err}")
    return info, destino


def leer_chat(ruta):
    """El JSON de yt-dlp (una acción por línea) -> [(segundo, autor, texto, tipo)]."""
    mensajes = []
    if not ruta.exists():
        return mensajes
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        try:
            accion = json.loads(linea)["replayChatItemAction"]
        except (json.JSONDecodeError, KeyError):
            continue
        segundo = int(accion.get("videoOffsetTimeMsec", 0)) / 1000
        for a in accion.get("actions", []):
            item = a.get("addChatItemAction", {}).get("item", {})
            for tipo, clave in (("mensaje", "liveChatTextMessageRenderer"),
                                ("superchat", "liveChatPaidMessageRenderer"),
                                ("miembro", "liveChatMembershipItemRenderer")):
                r = item.get(clave)
                if not r:
                    continue
                texto = "".join(run.get("text") or run.get("emoji", {}).get("shortcuts", [""])[0]
                                for run in r.get("message", r.get("headerSubtext", {})).get("runs", []))
                autor = r.get("authorName", {}).get("simpleText", "?")
                if tipo == "superchat":
                    texto = f"[{r.get('purchaseAmountText', {}).get('simpleText', '')}] {texto}"
                if texto.strip() or tipo != "mensaje":
                    mensajes.append((segundo, autor, texto.strip(), tipo))
    return mensajes


def cargar_cuda(ruta):
    """Carga cuBLAS/cuDNN antes que faster-whisper (en Windows no los busca por PATH)."""
    import ctypes
    candidatas = [ruta] if ruta else []
    try:
        import nvidia
        candidatas += list(nvidia.__path__)
    except ImportError:
        pass
    for base in candidatas:
        for dll in sorted(glob.glob(os.path.join(base, "*", "bin", "*.dll"))):
            try:
                ctypes.WinDLL(dll)
            except OSError:
                pass


def transcribir(audio, idioma, cuda):
    salida = audio.with_name("voz.jsonl")
    if salida.exists():
        return [json.loads(l) for l in salida.read_text(encoding="utf-8").splitlines()]
    if os.name == "nt":
        cargar_cuda(cuda)
    from faster_whisper import WhisperModel
    try:
        modelo = WhisperModel("large-v3", device="cuda", compute_type="float16")
        segs, _ = modelo.transcribe(str(audio), language=idioma, vad_filter=True, beam_size=1)
        segs = list(segs)
    except RuntimeError as err:   # sin gráfica: más lento y menos fino, pero funciona
        print(f"  (sin CUDA: {str(err)[:80]}; uso el procesador con el modelo small)")
        modelo = WhisperModel("small", device="cpu", compute_type="int8")
        segs, _ = modelo.transcribe(str(audio), language=idioma, vad_filter=True)
        segs = list(segs)
    voz = [{"ini": round(s.start, 1), "fin": round(s.end, 1), "texto": s.text.strip()} for s in segs]
    salida.write_text("".join(json.dumps(v, ensure_ascii=False) + "\n" for v in voz), encoding="utf-8")
    return voz


def palabras(texto):
    t = unicodedata.normalize("NFKD", texto.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return {w for w in re.findall(r"[a-z0-9]{3,}", t) if w not in VACIAS}


def nombre_corto(autor):
    return re.sub(r"[^a-z0-9]", "", autor.lstrip("@").lower())


def emparejar(chat, voz, canal=""):
    """Mensaje -> lo que dijo la streamer poco después, si lo nombra o repite sus palabras."""
    pares, propias = [], palabras(canal)   # su propio nombre no cuenta («hola Lena» -> «soy Lena»)
    for seg, autor, texto, tipo in chat:
        clave, suyas = nombre_corto(autor), palabras(texto) - propias
        siguiente = [v for v in voz if seg + VENTANA[0] <= v["ini"] <= seg + VENTANA[1]]
        for i, v in enumerate(siguiente):
            dicho = nombre_corto(v["texto"])
            nombra = len(clave) >= 4 and (clave[:8] in dicho)
            comunes = suyas & palabras(v["texto"])
            if nombra or (tipo != "mensaje") or len(comunes) >= 2:
                respuesta = " ".join(x["texto"] for x in siguiente[i:i + 3])   # unos segundos de respuesta
                pares.append({"segundo": round(seg), "autor": autor, "tipo": tipo, "mensaje": texto,
                              "respuesta": respuesta, "pista": "nombre" if nombra else
                              ("evento" if tipo != "mensaje" else "palabras: " + ", ".join(sorted(comunes)))})
                break
    return pares


def reloj(s):
    s = int(s)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:02d}:{s % 60:02d}"


def estudiar(url, idioma, cuda):
    info, carpeta = descargar(url, ESTUDIO)
    print(f"- {info.get('channel')} · {info.get('title')}")
    audio = next(carpeta.glob("audio.*"))
    chat = leer_chat(carpeta / "chat.json")
    voz = transcribir(audio, idioma, cuda)
    lineas = [(v["ini"], 1, f"[{reloj(v['ini'])}] >> STREAMER: {v['texto']}") for v in voz]
    lineas += [(s, 0, f"[{reloj(s)}]    {a}{' (' + t + ')' if t != 'mensaje' else ''}: {x}")
               for s, a, x, t in chat]
    (carpeta / "linea_tiempo.txt").write_text("\n".join(l for _, _, l in sorted(lineas)) + "\n", encoding="utf-8")
    pares = emparejar(chat, voz, info.get("channel", ""))
    (carpeta / "pares.jsonl").write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in pares),
                                         encoding="utf-8")
    datos = {"id": info["id"], "url": info.get("webpage_url", url), "titulo": info.get("title"),
             "canal": info.get("channel"), "fecha": info.get("upload_date"), "duracion": info.get("duration"),
             "fue_directo": info.get("live_status") == "was_live", "idioma": idioma,
             "mensajes_chat": len(chat), "frases_voz": len(voz), "pares_candidatos": len(pares)}
    (carpeta / "info.json").write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  {len(voz)} frases de voz · {len(chat)} mensajes de chat · {len(pares)} pares candidatos -> {carpeta}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("urls", nargs="+")
    p.add_argument("--idioma", default="es", help="idioma de la voz (es, en...)")
    p.add_argument("--cuda", default="", help="carpeta con las librerías de NVIDIA (nvidia/<lib>/bin)")
    args = p.parse_args()
    for url in args.urls:
        try:
            estudiar(url, args.idioma, args.cuda)
        except Exception as err:
            print(f"  FALLO con {url}: {err}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()

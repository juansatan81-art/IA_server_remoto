"""Junta las frases valoradas en el panel (👍/👎) en un dataset para el fine-tuning.

Lee memoria/conversaciones/ (lo guarda el servidor solo, frase a frase) y escribe en
memoria/dataset/:
  buenas.jsonl  las 👍, cada una con el contexto exacto que vio el modelo: sistema,
                historial, mensaje y la respuesta. Es el formato «messages» que entienden
                Unsloth, Axolotl y casi todo (fine-tuning supervisado).
  malas.jsonl   las 👎, igual. Sirven como ejemplos de lo que NO (preferencias / DPO) o
                para revisar qué falla.
Si una frase se valoró varias veces, cuenta la última. Las bloqueadas por el filtro no
entran nunca.

Uso:  python herramientas/exportar_dataset.py          (exporta)
      python herramientas/exportar_dataset.py --ver    (solo cuenta lo que hay)
"""
import argparse
import json
from pathlib import Path

MEMORIA = Path(__file__).resolve().parent.parent / "memoria"
CONVERSACIONES = MEMORIA / "conversaciones"
SALIDA = MEMORIA / "dataset"


def leer_jsonl(ruta):
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        try:
            yield json.loads(linea)
        except json.JSONDecodeError:
            continue


def valoraciones():
    ruta = CONVERSACIONES / "valoraciones.jsonl"
    ultimas = {}
    if ruta.exists():
        for v in leer_jsonl(ruta):
            ultimas[v.get("id")] = v.get("valor", 0)
    return ultimas


def ejemplo(frase):
    """Una frase guardada -> {"messages": [...]} listo para entrenar."""
    sistema = (CONVERSACIONES / "sistemas" / f"{frase['sistema']}.txt").read_text(encoding="utf-8")
    entrada = frase["entrada"]
    if frase.get("busqueda"):
        entrada += "\n\n(Lo que encontraste al buscar en internet:\n" + "\n".join(frase["busqueda"]) + ")"
    return {"id": frase["id"], "origen": frase.get("origen", "chat"),
            "messages": [{"role": "system", "content": sistema}, *frase.get("historial", []),
                         {"role": "user", "content": entrada},
                         {"role": "assistant", "content": frase["dicho"]}]}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ver", action="store_true", help="solo cuenta, no escribe nada")
    args = p.parse_args()

    if not CONVERSACIONES.exists():
        print("Aún no hay conversaciones guardadas (arranca el servidor y habla con Lara).")
        return
    notas = valoraciones()
    total, buenas, malas = 0, [], []
    for dia in sorted(CONVERSACIONES.glob("????-??-??.jsonl")):
        for frase in leer_jsonl(dia):
            total += 1
            valor = notas.get(frase.get("id"), 0)
            if not valor or frase.get("bloqueada"):
                continue
            try:
                (buenas if valor > 0 else malas).append(ejemplo(frase))
            except (OSError, KeyError) as err:
                print(f"  (frase {frase.get('id')} saltada: {err})")

    print(f"Frases guardadas: {total} · buenas: {len(buenas)} · malas: {len(malas)}")
    if args.ver:
        return
    SALIDA.mkdir(exist_ok=True)
    for nombre, lista in (("buenas", buenas), ("malas", malas)):
        with open(SALIDA / f"{nombre}.jsonl", "w", encoding="utf-8") as f:
            for e in lista:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"Escrito en {SALIDA}")
    if len(buenas) < 300:
        print("Para un fine-tuning que se note hacen falta unos cientos de buenas (mejor 500 o más).")


if __name__ == "__main__":
    main()

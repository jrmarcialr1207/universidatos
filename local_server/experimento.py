"""Experimento de Universidatos: corre las preguntas de preguntas.json en varias condiciones y guarda las respuestas.

Se ejecuta DENTRO de la carpeta del servidor local (local_server/ o la carpeta de Ollama), con Ollama abierto:

    python experimento.py                              # las 4 condiciones con qwen2.5:7b
    python experimento.py --modelo llama3.1:8b         # otro modelo
    python experimento.py --condiciones guiado         # solo una condición
    python experimento.py --repeticiones 3             # repetir cada pregunta (para medir variación)

Condiciones:
  sin_herramientas  el modelo responde de memoria, sin datos (línea base)
  rag               el modelo recibe las series más parecidas a la pregunta y redacta (recuperación + generación)
  herramientas      el modelo elige y llama las 14 herramientas del sistema
  guiado            el planificador calcula los hechos y el modelo solo redacta (si no hay patrón, usa herramientas)
  texto_sql         el modelo escribe una consulta SQLite sobre universidatos.sqlite y redacta con el resultado
                    (se corre aparte: python experimento.py --condiciones texto_sql)

Las respuestas se guardan en resultados_<modelo>.jsonl. Si el proceso se interrumpe, al volver a correrlo
continúa donde se quedó. Después ejecuta:  python evaluar.py
"""
import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path

AQUI = Path(__file__).resolve().parent
CONDICIONES = ["sin_herramientas", "rag", "herramientas", "guiado", "texto_sql"]

p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument("--modelo", default=os.environ.get("MODELO", "qwen2.5:7b"))
p.add_argument("--condiciones", nargs="+", default=CONDICIONES[:4], choices=CONDICIONES)
p.add_argument("--repeticiones", type=int, default=1)
p.add_argument("--preguntas", default=str(AQUI / "preguntas.json"))
p.add_argument("--solo", nargs="*", help="ids de preguntas a correr (por ejemplo Q01 Q15)")
a = p.parse_args()

os.environ["MODELO"] = a.modelo  # el servidor lee el modelo al importarse
sys.path.insert(0, str(AQUI))
import servidor  # noqa: E402
from buscador import Buscador, analizar  # noqa: E402

BUSCADOR = Buscador(servidor.DATOS["indicadores"], servidor.DATOS["series"])
TSQL = None


def llm(mensajes, formato):
    cuerpo = {"model": a.modelo, "stream": False, "keep_alive": "30m", "messages": mensajes, "format": formato,
              "options": {"temperature": 0.1, "num_ctx": 12288}}
    if "qwen3" in a.modelo or "deepseek-r1" in a.modelo or "gpt-oss" in a.modelo:
        cuerpo["think"] = False
    return servidor.ollama("/api/chat", cuerpo).get("message", {}).get("content", "")

SISTEMA_BASE = ("Eres un asistente que responde preguntas sobre la Universidad Autónoma del Estado de México (UAEMEX). "
                "Responde en español, en 1 a 3 frases, con la cifra exacta si la conoces. Si no tienes el dato, dilo.")


def candidatos_y_anios(pregunta):
    """Lo mismo que hace la página antes de llamar al servidor: buscar series parecidas y detectar los años."""
    q, res = BUSCADOR.buscar(pregunta, 8)
    cand = [r["id"] for r in res if r["id"] in servidor.SER][:10]
    desde = max(servidor.ANIO_MIN, q["desde"] or servidor.ANIO_MIN)
    hasta = min(servidor.ANIO_MAX, q["hasta"] or servidor.ANIO_MAX)
    return cand, desde, hasta, q["unico"]


def sin_herramientas(pregunta):
    cuerpo = {"model": a.modelo, "stream": False, "keep_alive": "30m", "options": {"temperature": 0.1, "num_ctx": 4096},
              "messages": [{"role": "system", "content": SISTEMA_BASE}, {"role": "user", "content": pregunta}]}
    if "qwen3" in a.modelo or "deepseek-r1" in a.modelo or "gpt-oss" in a.modelo:
        cuerpo["think"] = False
    r = servidor.ollama("/api/chat", cuerpo)
    return {"respuesta": r.get("message", {}).get("content", "").strip(), "modo": "sin_herramientas"}


def correr(cond, pregunta):
    cand, desde, hasta, unico = candidatos_y_anios(pregunta)
    if cond == "sin_herramientas":
        return sin_herramientas(pregunta)
    if cond == "rag":
        if not cand:
            return {"respuesta": "No encontré indicadores relacionados con la pregunta.", "modo": "rag_sin_candidatos"}
        return servidor.preguntar(pregunta, cand, desde, hasta, unico)
    if cond == "herramientas":
        return servidor.preguntar_con_herramientas(pregunta, cand, desde, hasta, unico)
    if cond == "texto_sql":
        global TSQL
        if TSQL is None:
            import texto_sql
            TSQL = texto_sql.TextoSQL(servidor.CALC, BUSCADOR, llm)
        return TSQL.preguntar(pregunta)
    if cond == "guiado":
        r = servidor.preguntar_guiado(pregunta, desde, hasta, unico)
        if r:
            return r
        r = servidor.preguntar_con_herramientas(pregunta, cand, desde, hasta, unico)
        r["modo"] = "guiado→herramientas"
        return r
    raise ValueError(cond)


def main():
    est = servidor.estado()
    if not est["listo"]:
        sys.exit(f"Ollama no está listo: {est['mensaje']}")
    preguntas = json.load(open(a.preguntas, encoding="utf-8"))
    if a.solo:
        preguntas = [q for q in preguntas if q["id"] in a.solo]
    salida = AQUI / f"resultados_{a.modelo.replace(':', '_').replace('/', '_')}.jsonl"
    hechas = set()
    if salida.exists():
        for linea in salida.read_text(encoding="utf-8").splitlines():
            if linea.strip():
                r = json.loads(linea)
                hechas.add((r["id"], r["condicion"], r["repeticion"]))
    total = len(preguntas) * len(a.condiciones) * a.repeticiones
    n = 0
    print(f"Modelo: {a.modelo} · {len(preguntas)} preguntas · condiciones: {', '.join(a.condiciones)} · repeticiones: {a.repeticiones}")
    print(f"Resultados en: {salida.name}\n")
    with open(salida, "a", encoding="utf-8") as f:
        for rep in range(1, a.repeticiones + 1):
            for cond in a.condiciones:
                for q in preguntas:
                    n += 1
                    if (q["id"], cond, rep) in hechas:
                        continue
                    inicio = time.time()
                    try:
                        r = correr(cond, q["pregunta"])
                        texto, modo, error = str(r.get("respuesta", "")), r.get("modo", cond), None
                        extra = {k: r[k] for k in ("sql", "intentos", "tablas_esquema") if k in r}
                    except Exception as e:  # se registra y se sigue con la siguiente
                        texto, modo, error, extra = "", cond, f"{type(e).__name__}: {e}", {}
                        traceback.print_exc(limit=1)
                    seg = round(time.time() - inicio, 1)
                    f.write(json.dumps({"id": q["id"], "condicion": cond, "repeticion": rep, "modelo": a.modelo, "modo_usado": modo,
                                        "pregunta": q["pregunta"], "respuesta": texto, "error": error, "segundos": seg, **extra},
                                       ensure_ascii=False) + "\n")
                    f.flush()
                    print(f"[{n}/{total}] {cond:16s} {q['id']} {seg:6.1f}s  {texto[:90].replace(chr(10), ' ')}{'  ERROR: ' + error if error else ''}")
    print(f"\nListo. Ahora ejecuta:  python evaluar.py {salida.name}")


if __name__ == "__main__":
    main()

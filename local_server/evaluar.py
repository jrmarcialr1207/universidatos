"""Califica las respuestas del experimento contra las respuestas correctas de preguntas.json.

    python evaluar.py                          # todos los resultados_*.jsonl de la carpeta
    python evaluar.py resultados_qwen2.5_7b.jsonl

Genera:
  calificacion.csv   una fila por respuesta, con su calificación
  resumen.md         tablas de exactitud por condición y por categoría

Calificación de cada respuesta:
  correcta     contiene la cifra (o el nombre) correcta
  incorrecta   da cifras, pero ninguna es la correcta (cifra inventada o mal calculada)
  abstencion   dice que no tiene el dato y no da la cifra correcta
  error        el sistema falló y no hubo respuesta
En las preguntas sin respuesta en los datos, lo correcto es abstenerse; dar una cifra cuenta como inventar.
"""
import csv
import glob
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

AQUI = Path(__file__).resolve().parent
ORO = {q["id"]: q for q in json.load(open(AQUI / "preguntas.json", encoding="utf-8"))}
ORDEN = ["sin_herramientas", "rag", "herramientas", "guiado"]

ABSTENCION = re.compile(
    r"no (?:tengo|cuento|hay|encontr\w*|dispon\w*|se (?:reporta|incluye|encuentra|tiene|cuenta)|incluye\w*|contiene\w*|aparece\w*|existe\w*|es posible|puedo|se puede|est[aá]n? disponible)"
    r"|sin (?:datos|informaci[oó]n)|no se (?:dispone|conoce)|fuera del? (?:alcance|periodo)|carezco|desconozco|lo siento|no proporciona",
    re.I)


def norm(s):
    s = unicodedata.normalize("NFD", str(s).lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9 ]+", " ", s)


def numeros(texto):
    """Cifras en formato mexicano (100,491 · 18.9 · −187) y también 100 491."""
    t = texto.replace("−", "-").replace(" ", " ")
    t = re.sub(r"(?<=\d) (?=\d{3}\b)", "", t)  # 100 491 → 100491
    out = []
    for m in re.finditer(r"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|-?\d+(?:\.\d+)?", t):
        s = m.group(0).replace(",", "")
        try:
            out.append(float(s))
        except ValueError:
            pass
    return out


def coincide(x, oro, tipo):
    x, o = abs(x), abs(oro)
    if tipo in ("porcentaje", "razon"):
        return abs(x - o) <= 0.15 or (x == int(x) and abs(x - o) <= 0.5)
    return abs(x - o) <= max(0.5, 0.001 * o)


def calificar(r):
    q = ORO[r["id"]]
    texto = r.get("respuesta") or ""
    if r.get("error") or not texto.strip():
        return "error"
    abst = bool(ABSTENCION.search(texto))
    if q["tipo"] == "abstener":
        anios_preg = {float(a) for a in re.findall(r"\b(?:19|20)\d{2}\b", q["pregunta"])}
        cifras = [x for x in numeros(texto) if x not in anios_preg]
        return "correcta" if abst and not cifras else ("abstencion_parcial" if abst else "incorrecta")
    if q["tipo"] == "texto":
        if norm(q["oro"]).replace("lic ", "").strip() in norm(texto):
            return "correcta"
        return "abstencion" if abst else "incorrecta"
    if any(coincide(x, q["oro"], q["tipo"]) for x in numeros(texto)):
        return "correcta"
    return "abstencion" if abst else "incorrecta"


def main():
    archivos = sys.argv[1:] or sorted(glob.glob(str(AQUI / "resultados_*.jsonl")))
    filas = []
    for a in archivos:
        for linea in open(a, encoding="utf-8"):
            if linea.strip():
                r = json.loads(linea)
                r["calificacion"] = calificar(r)
                r["categoria"] = ORO[r["id"]]["categoria"]
                r["oro"] = ORO[r["id"]]["oro"]
                filas.append(r)
    if not filas:
        sys.exit("No hay resultados. Primero ejecuta: python experimento.py")
    with open(AQUI / "calificacion.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["modelo", "condicion", "repeticion", "id", "categoria", "pregunta", "oro", "respuesta",
                                          "calificacion", "modo_usado", "segundos", "error"], extrasaction="ignore")
        w.writeheader()
        w.writerows(filas)

    grupos = defaultdict(list)
    for r in filas:
        grupos[(r["modelo"], r["condicion"])].append(r)
    cats = list(dict.fromkeys(q["categoria"] for q in ORO.values()))
    pct = lambda n, d: f"{100 * n / d:.1f}" if d else "–"
    L = ["# Resultados del experimento\n",
         "## Resumen por condición\n",
         "| Modelo | Condición | Respuestas | Exactitud (con dato) | Cifra incorrecta | Se abstuvo | Abstención correcta (sin dato) | Errores | Segundos (mediana) |",
         "|---|---|---|---|---|---|---|---|---|"]
    claves = sorted(grupos, key=lambda k: (k[0], ORDEN.index(k[1]) if k[1] in ORDEN else 9))
    for k in claves:
        rs = grupos[k]
        con = [r for r in rs if ORO[r["id"]]["tipo"] != "abstener"]
        sin = [r for r in rs if ORO[r["id"]]["tipo"] == "abstener"]
        seg = sorted(r["segundos"] for r in rs if not r.get("error"))
        med = seg[len(seg) // 2] if seg else 0
        L.append(f"| {k[0]} | {k[1]} | {len(rs)} | {pct(sum(r['calificacion'] == 'correcta' for r in con), len(con))} % "
                 f"| {pct(sum(r['calificacion'] == 'incorrecta' for r in con), len(con))} % "
                 f"| {pct(sum(r['calificacion'] == 'abstencion' for r in con), len(con))} % "
                 f"| {pct(sum(r['calificacion'] == 'correcta' for r in sin), len(sin))} % "
                 f"| {sum(r['calificacion'] == 'error' for r in rs)} | {med:.1f} |")
    L += ["", "## Exactitud por categoría (% de respuestas correctas)\n",
          "| Modelo | Condición | " + " | ".join(cats) + " |", "|---|---|" + "---|" * len(cats)]
    for k in claves:
        rs = grupos[k]
        celdas = []
        for c in cats:
            rc = [r for r in rs if r["categoria"] == c]
            celdas.append(pct(sum(r["calificacion"] == "correcta" for r in rc), len(rc)))
        L.append(f"| {k[0]} | {k[1]} | " + " | ".join(celdas) + " |")
    L += ["", "Exactitud (con dato): preguntas cuya respuesta está en los datos. Abstención correcta (sin dato): preguntas fuera de los datos "
          "en las que el sistema dijo que no tenía la información en lugar de dar una cifra.",
          "Revisa a mano en calificacion.csv las respuestas marcadas como incorrectas: la calificación automática busca la cifra exacta "
          "y puede no reconocer formas como «cerca de 100 mil»."]
    (AQUI / "resumen.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    print("\nArchivos: calificacion.csv, resumen.md")


if __name__ == "__main__":
    main()

"""Convierte los archivos His01..His08 (Series 2004-2025, Agenda Estadística UAEMEX)
a formato largo: una fila por indicador y año.

Uso: python series_a_tabla.py <carpeta_con_xlsx> <carpeta_salida>
"""
import csv
import json
import re
import sqlite3
import sys
from pathlib import Path

import openpyxl

EJES = {
    "His01": "Docencia",
    "His02": "Investigación",
    "His03": "Internacionalización de la educación",
    "His04": "Identidad y Cultura",
    "His05": "Vinculación, Extensión y Promoción de la Empleabilidad",
    "His06": "Personal",
    "His07": "Gestión",
    "His08": "Sistema incorporado",
}


def limpia(t):
    return re.sub(r"\s+", " ", str(t)).strip()


def numero(v):
    """Número o texto con un número («1 500», «2,030»); None si no."""
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str) and re.match(r"^\s*-?\d{1,3}([ ,]\d{3})+(\.\d+)?\s*$|^\s*-?\d+(\.\d+)?\s*$", v):
        return float(re.sub(r"[ ,]", "", v))
    return None


def procesa(path: Path):
    codigo = path.stem[:5]
    wb = openpyxl.load_workbook(path)
    ws = wb.active

    # Fila de encabezado: la que dice "Concepto"
    fila_enc = next(r for r in range(1, 20) if limpia(ws.cell(r, 1).value or "") == "Concepto")
    años = {}
    for c in range(2, ws.max_column + 1):
        v = ws.cell(fila_enc, c).value
        if isinstance(v, (int, float)) or (isinstance(v, str) and v.strip().isdigit()):
            años[c] = int(v)

    filas, indicadores, notas = [], [], []
    pila = []  # (nivel, nombre)
    fin_tabla = False
    vacias = 0
    for r in range(fila_enc + 1, ws.max_row + 1):
        celda = ws.cell(r, 1)
        if celda.value is None or limpia(celda.value) == "":
            vacias += 1
            if vacias >= 1 and filas:
                fin_tabla = True
            continue
        texto = limpia(celda.value)
        valores = {a: ws.cell(r, c).value for c, a in años.items()}
        valores = {a: numero(v) for a, v in valores.items()}
        tiene_datos = any(v is not None for v in valores.values())

        if fin_tabla:
            if texto.lower().startswith("fuente"):
                continue
            notas.append(texto)
            continue

        nivel = int(celda.alignment.indent or 0)
        while pila and pila[-1][0] >= nivel:
            pila.pop()
        ruta = [p[1] for p in pila] + [texto]
        pila.append((nivel, texto))

        ind_id = f"{codigo}-{r}"
        indicadores.append({
            "id": ind_id, "eje": EJES.get(codigo, codigo), "archivo": codigo,
            "fila_excel": r, "nivel": nivel, "concepto": texto,
            "ruta": " > ".join(ruta), "tiene_datos": tiene_datos,
        })
        for a, v in valores.items():
            if v is not None:
                filas.append({"id": ind_id, "anio": a, "valor": float(v)})
    return indicadores, filas, notas


def main(origen, salida):
    origen, salida = Path(origen), Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    todos_ind, todas_filas, todas_notas = [], [], {}
    for f in sorted(origen.glob("His0*.xlsx")):
        ind, fil, notas = procesa(f)
        todos_ind += ind
        todas_filas += fil
        todas_notas[EJES[f.stem[:5]]] = notas
        print(f"{f.name}: {len(ind)} conceptos, {len(fil)} valores, {len(notas)} notas")

    # CSV largo legible
    por_id = {i["id"]: i for i in todos_ind}
    with open(salida / "series_uaemex_2004_2025.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["eje", "indicador", "concepto", "anio", "valor", "archivo", "fila_excel"])
        for f in todas_filas:
            i = por_id[f["id"]]
            w.writerow([i["eje"], i["ruta"], i["concepto"], f["anio"], f["valor"], i["archivo"], i["fila_excel"]])

    # SQLite
    db = salida / "series_uaemex.sqlite"
    db.unlink(missing_ok=True)
    con = sqlite3.connect(db)
    con.execute("create table indicadores(id text primary key, eje text, archivo text, fila_excel int, nivel int, concepto text, ruta text, tiene_datos int)")
    con.execute("create table valores(id text, anio int, valor real)")
    con.execute("create table notas(eje text, nota text)")
    con.executemany("insert into indicadores values(:id,:eje,:archivo,:fila_excel,:nivel,:concepto,:ruta,:tiene_datos)", todos_ind)
    con.executemany("insert into valores values(:id,:anio,:valor)", todas_filas)
    con.executemany("insert into notas values(?,?)", [(e, n) for e, ns in todas_notas.items() for n in ns])
    con.commit()
    con.close()

    # JSON compacto para la página
    series = {}
    for f in todas_filas:
        series.setdefault(f["id"], {})[f["anio"]] = round(f["valor"], 4)
    data = {
        "indicadores": [
            {k: i[k] for k in ("id", "eje", "nivel", "concepto", "ruta", "fila_excel", "archivo")}
            for i in todos_ind
        ],
        "series": series,
        "notas": todas_notas,
    }
    (salida / "series_uaemex.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Total: {len(todos_ind)} conceptos, {len(todas_filas)} valores")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

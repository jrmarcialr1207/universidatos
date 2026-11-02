"""Construye data/universidatos.sqlite: una base de datos relacional con todas las tablas y series de la Agenda.

    python scripts/construir_sqlite.py

Esquema (ver data/esquema_sqlite.md):
  catálogo      tablas, tablas_anio, columnas, columnas_anio
  datos         t_<id> (una tabla SQL por cada tabla de la Agenda, en formato ancho, una fila por renglón y año)
                fichas (todas las fichas por espacio en formato largo)
                indicadores, valores_series (series históricas 2004–2025)
  dimensiones   espacios
  trazabilidad  excel_filas, excel_columnas (renglón y columna del Excel original de cada dato)
"""
import json
import re
import sqlite3
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
T = json.loads((RAIZ / "data" / "tablas_uaemex.json").read_text(encoding="utf-8"))
S = json.loads((RAIZ / "data" / "series_uaemex.json").read_text(encoding="utf-8"))
SALIDA = RAIZ / "data" / "universidatos.sqlite"

GRUPO = re.compile(r"^(escuela|facultad|plantel|centro|unidad|instituto|dependencia|organismo)", re.I)
RESERVADAS = {"anio", "fila_id", "ruta", "profundidad", "es_subtotal", "bloque", "tipo_espacio", "espacio_id", "espacio", "detalle", "renglon",
              "nivel1", "nivel2", "nivel3", "nivel4", "nivel5", "select", "from", "where", "group", "order", "table", "index"}


def sql_nombre(etiqueta, usados, maximo=60):
    s = re.sub(r"\bañ(o|os)\b", r"ani\1", str(etiqueta).lower())
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.replace("›", " ").replace("%", " pct ").replace("°", " ").replace("/", " ")
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_") or "columna"
    if s[0].isdigit():
        s = "c_" + s
    s = s[:maximo].rstrip("_")
    if s in RESERVADAS:
        s = s + "_valor"
    base, k = s, 2
    while s in usados:
        s = f"{base[:maximo - 3]}_{k}"
        k += 1
    usados.add(s)
    return s


def q(nombre):
    return '"' + nombre.replace('"', '""') + '"'


def clave(x):
    x = unicodedata.normalize("NFD", str(x).lower())
    x = "".join(c for c in x if unicodedata.category(c) != "Mn")
    x = re.sub(r"\(\d+\)|\*|\d+$", " ", x)
    return re.sub(r"[^a-z0-9]+", " ", x).strip()


TIPOS = [("facultad", "Facultad"), ("escuela", "Escuela"), ("plantel", "Plantel de la Escuela Preparatoria"),
         ("centro universitario", "Centro universitario UAEM"), ("unidad academica", "Unidad académica profesional"),
         ("instituto", "Instituto o centro de investigación"), ("centro de investigacion", "Instituto o centro de investigación")]


def tipo_de(grupo):
    g = clave(grupo)
    return next((t for k, t in TIPOS if g.startswith(k)), None)


CANON = {}   # (tipo, clave del nombre corto) -> (espacio_id, nombre corto)
for tid, t in T.items():
    if t["seccion"] != "Fichas por espacio":
        continue
    nom = t["titulo"].strip()
    if tid[0] == "O":
        tipo, corto = ("Escuela", nom[len("Escuela de "):]) if nom.startswith("Escuela") else ("Facultad", nom[len("Facultad de "):])
    elif tid[0] == "U":
        tipo, corto = "Centro universitario UAEM", nom[len("Centro Universitario UAEM "):]
    elif tid[0] == "V":
        tipo, corto = "Unidad académica profesional", nom[len("Unidad Académica Profesional "):]
    elif tid[0] == "B":
        m = re.search(r'Plantel "?(.+?)"? de la Escuela', nom)
        tipo, corto = "Plantel de la Escuela Preparatoria", m.group(1)
    else:
        tipo, corto = "Instituto o centro de investigación", nom
    CANON[(tipo, clave(corto))] = (tid, corto, nom)

# nombres que cambiaron entre ediciones o con otra escritura (Tianguistenco era UAP en 2018–2024)
ALIAS = {("Unidad académica profesional", "tianguistenco"): "U08", ("Plantel de la Escuela Preparatoria", "dr angel maria garibay kintana"): "B02",
         ("Centro universitario UAEM", "teotihuacan"): "U11", ("Unidad académica profesional", "tlanepantla"): "V07",
         ("Facultad", "artes escenicas"): "O01", ("Facultad", "arquitectura"): "O03"}
POR_ID = {v[0]: v for v in CANON.values()}
for k, eid in ALIAS.items():
    CANON.setdefault(k, POR_ID[eid])
ESPACIOS = {v[0]: (v[1], v[2], next(t for (t, _), w in CANON.items() if w[0] == v[0] and not (t, _) in ALIAS)) for v in CANON.values()}


def ubicar(r):
    """Devuelve (bloque, tipo_espacio, espacio_id, espacio, detalle) si el renglón pertenece a un espacio con ficha."""
    for p in range(len(r) - 1):
        tipo = tipo_de(r[p])
        if tipo and (tipo, clave(r[p + 1])) in CANON:
            eid, corto, _ = CANON[(tipo, clave(r[p + 1]))]
            return (" › ".join(x.strip() for x in r[:p]) or None, tipo, eid, corto, " › ".join(x.strip() for x in r[p + 2:]) or None)
    return None, None, None, None, None


if SALIDA.exists():
    SALIDA.unlink()
db = sqlite3.connect(SALIDA)
db.executescript("""
PRAGMA journal_mode = OFF;
PRAGMA synchronous = OFF;
CREATE TABLE tablas (
  tabla_id   TEXT PRIMARY KEY,          -- identificador estable, p. ej. A26
  tabla_sql  TEXT NOT NULL,             -- nombre de la tabla SQL con los datos, p. ej. t_a26
  seccion    TEXT NOT NULL,             -- Docencia, Personal, Ciencia, ...
  numero     INTEGER,
  tipo       TEXT NOT NULL,             -- numerica | lista | ficha
  titulo     TEXT NOT NULL,             -- título sin año (el de 2025 o el más reciente)
  anios      TEXT NOT NULL              -- años disponibles, separados por coma
);
CREATE TABLE tablas_anio (
  tabla_id TEXT NOT NULL REFERENCES tablas(tabla_id),
  anio     INTEGER NOT NULL,
  titulo   TEXT,                        -- título con el ciclo o año de esa edición
  archivo  TEXT,                        -- archivo Excel de origen en la Agenda de ese año
  fuente   TEXT,
  notas    TEXT,
  PRIMARY KEY (tabla_id, anio)
);
CREATE TABLE columnas (
  tabla_id    TEXT NOT NULL REFERENCES tablas(tabla_id),
  columna_sql TEXT NOT NULL,            -- nombre de la columna en t_<id>
  posicion    INTEGER NOT NULL,
  etiqueta    TEXT NOT NULL,            -- encabezado original, con › entre niveles
  sumable     INTEGER NOT NULL DEFAULT 1, -- 0 si es un promedio, índice o porcentaje que no debe sumarse
  PRIMARY KEY (tabla_id, columna_sql)
);
CREATE TABLE columnas_anio (           -- encabezados que cambian de un año a otro (p. ej. «Matrícula 2024-2025»)
  tabla_id TEXT NOT NULL, columna_sql TEXT NOT NULL, anio INTEGER NOT NULL, etiqueta TEXT NOT NULL,
  PRIMARY KEY (tabla_id, columna_sql, anio)
);
CREATE TABLE espacios (                -- espacios académicos con ficha propia en la Agenda
  espacio_id     TEXT PRIMARY KEY,      -- id de su ficha: O15 Facultad de Ingeniería, U08 CU Tianguistenco, B01 Plantel Cuauhtémoc...
  espacio        TEXT NOT NULL,         -- nombre corto como aparece en los renglones, p. ej. Ingeniería
  nombre         TEXT NOT NULL,         -- nombre completo, p. ej. Facultad de Ingeniería
  tipo_espacio   TEXT NOT NULL          -- Facultad | Escuela | Plantel de la Escuela Preparatoria | Centro universitario UAEM | Unidad académica profesional | Instituto o centro de investigación
);
CREATE TABLE fichas (
  tabla_id TEXT NOT NULL REFERENCES tablas(tabla_id),
  espacio  TEXT NOT NULL,               -- nombre completo, p. ej. Facultad de Ingeniería
  anio     INTEGER NOT NULL,
  renglon  INTEGER NOT NULL,
  seccion  TEXT, concepto TEXT, valor TEXT,
  PRIMARY KEY (tabla_id, anio, renglon)
);
CREATE TABLE indicadores (
  indicador_id TEXT PRIMARY KEY,        -- p. ej. His01-46
  eje          TEXT NOT NULL,
  nivel        INTEGER,
  concepto     TEXT NOT NULL,
  ruta         TEXT NOT NULL,           -- jerarquía completa, con > entre niveles
  archivo      TEXT,                    -- archivo Excel de la serie (His01 ... His08)
  fila_excel   INTEGER
);
CREATE TABLE valores_series (
  indicador_id TEXT NOT NULL REFERENCES indicadores(indicador_id),
  anio         INTEGER NOT NULL,
  valor        REAL,
  PRIMARY KEY (indicador_id, anio)
);
CREATE TABLE excel_filas (
  tabla_id TEXT NOT NULL, anio INTEGER NOT NULL, fila_id INTEGER NOT NULL, fila_excel INTEGER NOT NULL,
  PRIMARY KEY (tabla_id, anio, fila_id)
);
CREATE TABLE excel_columnas (
  tabla_id TEXT NOT NULL, anio INTEGER NOT NULL, columna_sql TEXT NOT NULL, columna_excel TEXT NOT NULL,
  PRIMARY KEY (tabla_id, anio, columna_sql)
);
""")

espacios = set()
n_celdas = n_filas = n_renglones = 0
for tid in sorted(T):
    t = T[tid]
    es_ficha = t["seccion"] == "Fichas por espacio"
    tipo = "ficha" if es_ficha else t["tipo"]
    anios = sorted(t["titulos"], key=int)
    tsql = "t_" + tid.lower()
    db.execute("INSERT INTO tablas VALUES (?,?,?,?,?,?,?)", (tid, tsql, t["seccion"], t.get("numero"), tipo, t["titulo"], ",".join(anios)))
    for a in anios:
        notas = t.get("notas", {}).get(a)
        db.execute("INSERT INTO tablas_anio VALUES (?,?,?,?,?,?)", (tid, int(a), t["titulos"].get(a), t.get("archivos", {}).get(a),
                                                                    t.get("fuente", {}).get(a), "\n".join(notas) if isinstance(notas, list) else notas))
    if t["tipo"] == "numerica":
        usados = set()
        cols = [sql_nombre(" › ".join(c), usados) for c in t["columnas"]]
        no_sum = set(t.get("no_sumables", []))
        for j, (c, et) in enumerate(zip(cols, t["columnas"])):
            db.execute("INSERT INTO columnas VALUES (?,?,?,?,?)", (tid, c, j, " › ".join(et), 0 if j in no_sum else 1))
        for a, mapa in (t.get("columnas_anio") or {}).items():
            for j, et in mapa.items():
                db.execute("INSERT INTO columnas_anio VALUES (?,?,?,?)", (tid, cols[int(j)], int(a), " › ".join(et) if isinstance(et, list) else et))
        hijos = {i for i, f in enumerate(t["filas"]) for g in t["filas"] if len(g["ruta"]) > len(f["ruta"]) and g["ruta"][:len(f["ruta"])] == f["ruta"]}
        defs = ", ".join(f"{q(c)} REAL" for c in cols)
        db.execute(f"""CREATE TABLE {tsql} (anio INTEGER NOT NULL, fila_id INTEGER NOT NULL, ruta TEXT NOT NULL,
            nivel1 TEXT, nivel2 TEXT, nivel3 TEXT, nivel4 TEXT, nivel5 TEXT, profundidad INTEGER NOT NULL, es_subtotal INTEGER NOT NULL,
            bloque TEXT, tipo_espacio TEXT, espacio_id TEXT, espacio TEXT, detalle TEXT, {defs}, PRIMARY KEY (anio, fila_id))""")
        filas_sql = []
        for a in anios:
            d = t["datos"].get(a, {})
            ex = t.get("excel", {}).get(a, {})
            for i_s, celdas in d.items():
                i = int(i_s)
                r = t["filas"][i]["ruta"]
                niveles = (r + [None] * 5)[:5]
                if len(r) > 5:
                    niveles[4] = " › ".join(r[4:])
                bloque, tipo_esp, eid, espacio, detalle = ubicar(r)
                if eid:
                    espacios.add(eid)
                vals = [celdas.get(str(j)) for j in range(len(cols))]
                filas_sql.append((int(a), i, " › ".join(r), *niveles, len(r), 1 if i in hijos else 0, bloque, tipo_esp, eid, espacio, detalle, *vals))
                n_celdas += sum(v is not None for v in vals)
                if str(i) in ex.get("filas", {}):
                    db.execute("INSERT INTO excel_filas VALUES (?,?,?,?)", (tid, int(a), i, int(ex["filas"][str(i)])))
            for j_s, letra in ex.get("columnas", {}).items():
                db.execute("INSERT INTO excel_columnas VALUES (?,?,?,?)", (tid, int(a), cols[int(j_s)], str(letra)))
        ph = ",".join("?" * (15 + len(cols)))
        db.executemany(f"INSERT INTO {tsql} VALUES ({ph})", filas_sql)
        n_filas += len(filas_sql)
    else:
        usados = set()
        enc_union, mapas = [], {}
        for a in anios:
            m = []
            for h in t["encabezados"].get(a, []):
                base = sql_nombre(h, set())
                if base not in enc_union:
                    enc_union.append(base)
                    usados.add(base)
                    db.execute("INSERT OR IGNORE INTO columnas VALUES (?,?,?,?,1)", (tid, base, len(enc_union) - 1, h))
                m.append(base)
            mapas[a] = m
        defs = ", ".join(f"{q(c)} TEXT" for c in enc_union)
        db.execute(f"CREATE TABLE {tsql} (anio INTEGER NOT NULL, renglon INTEGER NOT NULL{', ' + defs if defs else ''}, PRIMARY KEY (anio, renglon))")
        for a in anios:
            m = mapas[a]
            ex = t.get("excel", {}).get(a, {})
            for k, r in enumerate(t["renglones"].get(a, [])):
                fila = {c: (str(v) if v is not None else None) for c, v in zip(m, r)}
                cs = list(fila)
                db.execute(f"INSERT INTO {tsql} (anio, renglon{''.join(', ' + q(c) for c in cs)}) VALUES ({','.join('?' * (2 + len(cs)))})",
                           (int(a), k, *fila.values()))
                n_renglones += 1
                fx = ex.get("filas")
                if isinstance(fx, list) and k < len(fx) and fx[k] is not None:
                    db.execute("INSERT INTO excel_filas VALUES (?,?,?,?)", (tid, int(a), k, int(fx[k])))
                if es_ficha and len(r) >= 3:
                    db.execute("INSERT INTO fichas VALUES (?,?,?,?,?,?,?)", (tid, t["titulo"], int(a), k, r[0], r[1], str(r[2])))

for eid, (corto, nom, tipo) in sorted(ESPACIOS.items()):
    db.execute("INSERT INTO espacios VALUES (?,?,?,?)", (eid, corto, nom, tipo))
for i in S["indicadores"]:
    db.execute("INSERT INTO indicadores VALUES (?,?,?,?,?,?,?)", (i["id"], i["eje"], i.get("nivel"), i["concepto"], i["ruta"], i.get("archivo"), i.get("fila_excel")))
n_val = 0
for k, s in S["series"].items():
    for a, v in s.items():
        db.execute("INSERT INTO valores_series VALUES (?,?,?)", (k, int(a), v))
        n_val += 1
db.execute("CREATE INDEX ix_valores_anio ON valores_series(anio)")
db.execute("CREATE INDEX ix_fichas_concepto ON fichas(concepto)")
db.commit()
db.execute("VACUUM")
db.close()
print(f"{SALIDA.name}: {len(T)} tablas, {n_filas} filas-año numéricas ({n_celdas} celdas), {n_renglones} renglones de listas, "
      f"{len(S['indicadores'])} indicadores, {n_val} valores de series, {len(ESPACIOS)} espacios ({len(espacios)} con renglones en tablas) · {SALIDA.stat().st_size / 1e6:.1f} MB")

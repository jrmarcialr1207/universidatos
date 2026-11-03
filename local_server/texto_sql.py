"""Modo «texto a SQL»: el modelo escribe una consulta SQLite sobre universidatos.sqlite, el sistema la ejecuta
y el modelo redacta la respuesta con el resultado.

Pasos:
  1. Esquema: se eligen las tablas de la Agenda más parecidas a la pregunta (el mismo buscador de tablas del sistema)
     y las series candidatas; se describen sus columnas, valores típicos y la lista de espacios académicos.
  2. Generación: el modelo devuelve {"sql": "..."} o {"sql": null, "razon": "..."} si la base no tiene el dato.
  3. Ejecución: solo lectura, una sola consulta SELECT, con tiempo y renglones limitados. Si hay error o el resultado
     sale vacío, se le devuelve el mensaje al modelo para que corrija (hasta 2 veces).
  4. Respuesta: el modelo redacta usando solo los renglones devueltos.
"""
import json
import re
import sqlite3
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RUTAS_DB = [AQUI / "universidatos.sqlite", AQUI.parent / "data" / "universidatos.sqlite"]
MAX_TABLAS = 4
MAX_COLUMNAS = 40
MAX_FILAS = 60
REINTENTOS = 2

REGLAS = """Eres un asistente que traduce preguntas sobre la Agenda Estadística de la Universidad Autónoma del Estado de México (UAEMEX) a UNA consulta SQLite.

Reglas:
1. Escribe una sola consulta SELECT (o WITH … SELECT) válida en SQLite. Usa solo las tablas y columnas del ESQUEMA.
2. Cada tabla t_… tiene una fila por renglón y año (columna anio; el año 2025 es el ciclo 2025-2026). El renglón de un espacio académico tiene su espacio_id y detalle IS NULL; sus programas educativos tienen el mismo espacio_id y el nombre del programa en detalle. Usa espacio_id de la lista de ESPACIOS, no el nombre.
3. Para comparar o ordenar espacios de un tipo, filtra tipo_espacio (p. ej. 'Facultad') y detalle IS NULL.
4. Las series históricas (2004–2025, totales de la universidad) están en valores_series(indicador_id, anio, valor); usa los indicador_id de INDICADORES.
5. Para un cambio entre años, une la tabla consigo misma (un alias por año) y resta; para porcentajes multiplica por 100.0. Redondea porcentajes y razones a 1 decimal con ROUND.
6. La matrícula total de la UAEMEX es la del sistema dependiente; el sistema incorporado (escuelas incorporadas) se reporta aparte y nunca se suma.
7. Si la base no puede responder (otra institución, un año que no existe, el futuro, un dato que no se registra), no inventes una consulta: responde {"sql": null, "razon": "…"}.
8. Responde solo con JSON: {"sql": "…"} o {"sql": null, "razon": "…"}."""

EJEMPLOS = """EJEMPLOS (con otras tablas y espacios):
Pregunta: ¿Cuántas mujeres estudiaban bachillerato en el Plantel Texcoco en 2024?
{"sql": "SELECT matricula_mujeres FROM t_a15 WHERE anio = 2024 AND espacio_id = 'B11' AND detalle IS NULL"}
Pregunta: ¿Cuántos alumnos tuvo el CELe en 2021?
{"sql": "SELECT valor FROM valores_series WHERE indicador_id = 'His05-26' AND anio = 2021"}
Pregunta: ¿Cuánto cambió la matrícula de especialidades médicas de 2019 a 2025?
{"sql": "SELECT b.valor - a.valor FROM valores_series a JOIN valores_series b ON b.indicador_id = a.indicador_id WHERE a.indicador_id = 'His01-50' AND a.anio = 2019 AND b.anio = 2025"}
Pregunta: ¿En qué año se fundó la Facultad de Lenguas?
{"sql": "SELECT valor FROM fichas WHERE espacio_id = 'O16' AND anio = 2025 AND concepto = 'Año de fundación'"}
Pregunta: ¿Cuántos alumnos tendrá la UAEMEX en 2040?
{"sql": null, "razon": "La base solo tiene datos de 2004 a 2025."}"""

RESPUESTA = """Eres el asistente estadístico de la UAEMEX. Redacta la respuesta a la pregunta usando SOLO el RESULTADO de la consulta.
Reglas: no agregues cifras que no estén en el resultado ni hagas cuentas; escribe las cifras en formato mexicano (100,491 y 7.4%);
si el resultado está vacío o no responde la pregunta, dilo; responde en español, en 1 a 4 frases, sin listas ni títulos.
Responde solo con JSON: {"respuesta": "texto"}"""


def _q(nombre):
    return '"' + nombre.replace('"', '""') + '"'


class TextoSQL:
    def __init__(self, calc, buscador_series, llm, db_path=None):
        """calc: Calculos (para el buscador de tablas); buscador_series: Buscador de series; llm(mensajes, formato) -> texto."""
        ruta = Path(db_path) if db_path else next((r for r in RUTAS_DB if r.exists()), None)
        if not ruta:
            raise FileNotFoundError("No encontré universidatos.sqlite junto al servidor ni en ../data/")
        self.db = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True, check_same_thread=False)
        self.calc, self.bus, self.llm = calc, buscador_series, llm
        c = self.db
        self.tablas = {r[0]: {"sql": r[1], "seccion": r[2], "tipo": r[3], "titulo": r[4], "anios": r[5]}
                       for r in c.execute("SELECT tabla_id, tabla_sql, seccion, tipo, titulo, anios FROM tablas")}
        self.columnas = {}
        for tid, col, et, sumable in c.execute("SELECT tabla_id, columna_sql, etiqueta, sumable FROM columnas ORDER BY tabla_id, posicion"):
            self.columnas.setdefault(tid, []).append((col, et, sumable))
        self.espacios = c.execute("SELECT espacio_id, espacio, tipo_espacio FROM espacios ORDER BY espacio_id").fetchall()
        self.indicadores = {r[0]: r[1:] for r in c.execute("SELECT indicador_id, eje, ruta FROM indicadores")}

    # ------------------------------------------------------------------ esquema
    def _describe_tabla(self, tid):
        t = self.tablas[tid]
        s = t["sql"]
        lin = [f"TABLA {s}  -- {tid} «{t['titulo']}» ({t['seccion']}; años {t['anios'].replace(',', ', ')})"]
        if t["tipo"] == "numerica":
            lin.append("  columnas fijas: anio, fila_id, ruta, bloque, tipo_espacio, espacio_id, espacio, detalle, es_subtotal")
            ult = int(t["anios"].split(",")[-1])
            tipos = [r[0] for r in self.db.execute(f"SELECT DISTINCT tipo_espacio FROM {s} WHERE tipo_espacio IS NOT NULL")]
            if tipos:
                lin.append("  valores de tipo_espacio: " + "; ".join(tipos))
            bloques = [r[0] for r in self.db.execute(f"SELECT DISTINCT bloque FROM {s} WHERE bloque IS NOT NULL LIMIT 8")]
            if bloques:
                lin.append("  valores de bloque: " + "; ".join(bloques))
            det = [r[0] for r in self.db.execute(f"SELECT DISTINCT detalle FROM {s} WHERE detalle IS NOT NULL AND anio = ? LIMIT 4", (ult,))]
            if det:
                lin.append("  ejemplos de detalle: " + "; ".join(det))
            sin_esp = [r[0] for r in self.db.execute(f"SELECT DISTINCT ruta FROM {s} WHERE espacio_id IS NULL AND anio = ? LIMIT 6", (ult,))]
            if sin_esp:
                lin.append("  renglones sin espacio (columna ruta): " + "; ".join(sin_esp))
            cols = self.columnas.get(tid, [])
            vista = cols[:MAX_COLUMNAS]
            lin.append("  columnas de datos (REAL): " + "; ".join(f"{c} = «{e}»" + ("" if su else " (promedio o índice: no sumar)") for c, e, su in vista)
                       + (f"; … y {len(cols) - len(vista)} columnas más" if len(cols) > len(vista) else ""))
        else:
            cols = self.columnas.get(tid, [])
            lin.append("  lista de texto; columnas: anio, renglon, " + ", ".join(f"{c} = «{e}»" for c, e, _ in cols))
        return "\n".join(lin)

    def esquema(self, pregunta):
        ses = self.calc.sesion()
        rk = [r["id"] for r in ses._rank_tablas(pregunta) if r["id"] in self.tablas and self.tablas[r["id"]]["tipo"] != "ficha"][:MAX_TABLAS]
        _, res = self.bus.buscar(pregunta, 8)
        ind = [r["id"] for r in res if r["id"] in self.indicadores]
        partes = ["ESQUEMA"]
        partes += [self._describe_tabla(t) for t in rk]
        partes.append("TABLA valores_series(indicador_id TEXT, anio INTEGER, valor REAL)  -- series históricas 2004–2025\n"
                      "TABLA indicadores(indicador_id, eje, concepto, ruta)\n"
                      "TABLA fichas(espacio_id, espacio, anio, seccion, concepto, valor TEXT)  -- ficha de cada espacio; concepto incluye «Año de fundación»\n"
                      "TABLA espacios(espacio_id, espacio, nombre, tipo_espacio)")
        if ind:
            partes.append("INDICADORES (candidatos para valores_series): " + "; ".join(f"{i} = {self.indicadores[i][1]} ({self.indicadores[i][0]})" for i in ind))
        partes.append("ESPACIOS (espacio_id espacio [tipo]): " + "; ".join(f"{e} {n} [{t}]" for e, n, t in self.espacios))
        return "\n".join(partes), rk, ind

    # ------------------------------------------------------------------ ejecución
    def ejecutar(self, sql):
        s = sql.strip().rstrip(";").strip()
        if not re.match(r"(?is)^\s*(select|with)\b", s) or ";" in s:
            raise ValueError("Solo se permite una consulta SELECT.")
        limite = time.time() + 5
        self.db.set_progress_handler(lambda: 1 if time.time() > limite else 0, 10000)
        try:
            cur = self.db.execute(s)
            cols = [d[0] for d in cur.description or []]
            filas = cur.fetchmany(MAX_FILAS + 1)
        finally:
            self.db.set_progress_handler(None, 0)
        return cols, filas

    @staticmethod
    def _json(texto):
        try:
            return json.loads(texto)
        except (json.JSONDecodeError, TypeError):
            m = re.search(r"\{.*\}", texto or "", re.S)
            if m:
                try:
                    return json.loads(m.group(0))
                except json.JSONDecodeError:
                    pass
        m = re.search(r"(?is)```(?:sql)?\s*(select.*?|with.*?)```", texto or "")
        return {"sql": m.group(1)} if m else {}

    # ------------------------------------------------------------------ flujo completo
    def preguntar(self, pregunta):
        inicio = time.time()
        esq, tablas, ind = self.esquema(pregunta)
        mensajes = [{"role": "system", "content": REGLAS + "\n\n" + EJEMPLOS},
                    {"role": "user", "content": f"{esq}\n\nPregunta: {pregunta}"}]
        intentos, sql, cols, filas, error, razon = [], None, [], [], None, None
        for k in range(REINTENTOS + 1):
            j = self._json(self.llm(mensajes, "json"))
            sql, razon = j.get("sql"), j.get("razon")
            if not sql:
                intentos.append({"sql": None, "razon": razon})
                break
            try:
                cols, filas = self.ejecutar(sql)
                error = None
            except Exception as e:  # noqa: BLE001 — el mensaje regresa al modelo
                error = f"{type(e).__name__}: {e}"
            intentos.append({"sql": sql, "error": error, "renglones": len(filas)})
            if not error and filas and any(v is not None for v in filas[0]):
                break
            if k == REINTENTOS:
                break
            aviso = (f"La consulta falló con el error: {error}. Corrígela." if error else
                     "La consulta no devolvió datos. Revisa el espacio_id, el año, las columnas y los filtros, o responde sql null si la base no tiene el dato.")
            mensajes += [{"role": "assistant", "content": json.dumps({"sql": sql}, ensure_ascii=False)}, {"role": "user", "content": aviso}]
        if not sql:
            texto = f"No es posible responder con la base de datos: {razon or 'el dato no está registrado.'}"
        else:
            res = {"columnas": cols, "renglones": [list(f) for f in filas[:MAX_FILAS]]} if not error else {"error": error}
            if len(filas) > MAX_FILAS:
                res["nota"] = f"Se muestran los primeros {MAX_FILAS} renglones."
            j = self._json(self.llm([{"role": "system", "content": RESPUESTA},
                                     {"role": "user", "content": f"Pregunta: {pregunta}\n\nConsulta: {sql}\n\nRESULTADO: {json.dumps(res, ensure_ascii=False, default=str)}"}],
                                    {"type": "object", "properties": {"respuesta": {"type": "string"}}, "required": ["respuesta"]}))
            texto = str(j.get("respuesta") or "").strip() or "No pude redactar la respuesta."
        return {"respuesta": texto, "sql": sql, "intentos": intentos, "tablas_esquema": tablas, "indicadores_esquema": ind,
                "columnas": cols, "renglones": [list(f) for f in filas[:MAX_FILAS]], "modo": "texto_sql",
                "segundos": round(time.time() - inicio, 1)}

"""Arma claude_page/experimento-sql.html: corre las preguntas de evaluación en modo texto a SQL con Claude, en el navegador.

Usa exactamente el mismo esquema por pregunta, reglas y ejemplos que local_server/texto_sql.py (se precalculan aquí)
y una copia de universidatos.sqlite sin las tablas de trazabilidad (excel_*, tablas_anio, columnas_anio), que el modelo
no ve en el esquema. La base se ejecuta en el navegador con sql.js (MIT).

    python scripts/construir_experimento_sql.py ruta/a/sql-wasm.js ruta/a/sql-wasm.wasm
"""
import base64
import gzip
import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R / "local_server"))
from buscador import Buscador  # noqa: E402
from calculos import Calculos  # noqa: E402
import texto_sql  # noqa: E402

js_sql, wasm = Path(sys.argv[1]), Path(sys.argv[2])
D = json.loads((R / "data" / "series_uaemex.json").read_text(encoding="utf-8"))
C = Calculos(D, json.loads((R / "data" / "tablas_uaemex.json").read_text(encoding="utf-8")))
ts = texto_sql.TextoSQL(C, Buscador(D["indicadores"], D["series"]), None, R / "data" / "universidatos.sqlite")
preg = json.loads((R / "local_server" / "preguntas.json").read_text(encoding="utf-8"))
exp = {"reglas": texto_sql.REGLAS, "ejemplos": texto_sql.EJEMPLOS, "respuesta": texto_sql.RESPUESTA,
       "preguntas": [{"id": q["id"], "pregunta": q["pregunta"], "esquema": ts.esquema(q["pregunta"])[0]} for q in preg]}

with tempfile.TemporaryDirectory() as d:
    copia = Path(d) / "web.sqlite"
    shutil.copy(R / "data" / "universidatos.sqlite", copia)
    db = sqlite3.connect(copia)
    for t in ("excel_filas", "excel_columnas", "columnas_anio", "tablas_anio"):
        db.execute(f"DROP TABLE {t}")
    db.commit()
    db.execute("VACUUM")
    db.close()
    base = base64.b64encode(gzip.compress(copia.read_bytes(), 9, mtime=0)).decode()

css = """<style>
:root{--fondo:#f7f6f2;--panel:#fff;--texto:#1c1b18;--suave:#5f5c55;--borde:#dedbd3;--acento:#1f5c3f}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--fondo:#161614;--panel:#1f1f1c;--texto:#ecebe6;--suave:#a9a69d;--borde:#3a3934;--acento:#7cc4a0}}
:root[data-theme="dark"]{--fondo:#161614;--panel:#1f1f1c;--texto:#ecebe6;--suave:#a9a69d;--borde:#3a3934;--acento:#7cc4a0}
body{margin:0;background:var(--fondo);color:var(--texto);font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px}
h1{font-size:1.4rem;margin:0 0 8px}p{margin:0 0 12px;color:var(--suave)}
.caja{background:var(--panel);border:1px solid var(--borde);border-radius:10px;padding:16px}
button{font:inherit;padding:8px 16px;border-radius:8px;border:1px solid var(--acento);background:var(--acento);color:#fff;cursor:pointer}
button.sec{background:transparent;color:var(--acento)}button:disabled{opacity:.5;cursor:default}
.botones{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:8px}#estado{font-size:.9rem}
.tabla{max-height:520px;overflow:auto;margin-top:8px}table{border-collapse:collapse;width:100%;font-size:.85rem;table-layout:fixed}
th,td{border-bottom:1px solid var(--borde);padding:4px 6px;text-align:left;vertical-align:top;overflow-wrap:anywhere}
th:nth-child(1){width:44px}th:nth-child(2){width:24%}th:nth-child(3){width:30%}th:nth-child(5){width:40px}
td:nth-child(3){font-family:ui-monospace,monospace;font-size:.78rem}
</style>"""
html = f"""<title>Experimento texto a SQL</title>
{css}
<main><section class="caja">
<h1>Experimento: Claude escribe SQL sobre la base de Universidatos</h1>
<p>Corre las {len(preg)} preguntas de evaluación en modo texto a SQL: Claude recibe el esquema de las tablas relevantes, escribe una consulta, la página la ejecuta en la base de datos (en este navegador) y Claude redacta la respuesta con el resultado. Es el mismo procedimiento que con los modelos locales. Deja la pestaña abierta; si se interrumpe, al volver a abrirla continúa donde se quedó.</p>
<div class="botones"><button type="button" id="correr" disabled>Correr las preguntas</button><button type="button" id="detener" class="sec" hidden>Detener</button><button type="button" id="bajar" class="sec" hidden>Descargar resultados</button></div>
<p id="estado"></p>
<div class="tabla"><table id="tabla"><thead><tr><th>Id</th><th>Pregunta</th><th>SQL</th><th>Respuesta</th><th>s</th></tr></thead><tbody></tbody></table></div>
</section></main>
<script id="datos-exp" type="application/json">{json.dumps(exp, ensure_ascii=False).replace('</', '<\\/')}</script>
<script id="wasm" type="text/plain">{base64.b64encode(wasm.read_bytes()).decode()}</script>
<script id="base" type="text/plain">{base}</script>
<script>/* sql.js 1.10.3 · MIT License · (c) 2017 sql.js authors */
{js_sql.read_text(encoding="utf-8")}</script>
<script>/* fflate 0.8.2 · MIT License · (c) 2023 Arjun Barrett */
{(R / "web" / "vendor" / "fflate-0.8.2.umd.js").read_text(encoding="utf-8")}</script>
<script>
{(R / "web" / "experimento_sql.js").read_text(encoding="utf-8")}</script>
"""
salida = R / "claude_page" / "experimento-sql.html"
salida.write_text(html, encoding="utf-8")
print(salida.name, f"{len(html) / 1e6:.1f} MB")

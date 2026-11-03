"""Clasifica las respuestas de texto a SQL de los modelos locales: re-ejecuta la consulta final sobre
universidatos.sqlite y compara su resultado con la respuesta de referencia (Tabla 9 del artículo).

    python evaluar.py && python analizar_sql.py
"""
import csv, json, re, sqlite3, sys
from pathlib import Path
LS = Path(__file__).resolve().parent; sys.path.insert(0, str(LS))
from buscador import Buscador; from calculos import Calculos; import texto_sql
R = LS.parent
D = json.loads((R/'data/series_uaemex.json').read_text()); C = Calculos(D, json.loads((R/'data/tablas_uaemex.json').read_text()))
ts = texto_sql.TextoSQL(C, Buscador(D['indicadores'], D['series']), None, R/'data/universidatos.sqlite')
db = sqlite3.connect(R/'data/universidatos.sqlite')
P = {q['id']: q for q in json.loads((LS/'preguntas.json').read_text())}
REF = {x['id']: x['sql'] for x in json.loads((LS/'sql_referencia.json').read_text())}
cal = {(r['modelo'], r['id']): r for r in csv.DictReader(open(LS/'resultados_experimento/calificacion.csv', encoding='utf-8-sig')) if r['condicion']=='texto_sql'}

def fuentes(sql):
    t = set(m.upper() for m in re.findall(r'\bt_([a-z]\d+)', sql or '', re.I))
    i = set(re.findall(r"His\d+-\d+", sql or ''))
    f = {'fichas'} if re.search(r'\bfichas\b', sql or '') else set()
    return t, i, f
def contiene(filas, oro):
    if oro is None: return False
    for f in filas:
        for v in f:
            if isinstance(v, str) and re.fullmatch(r'-?\d+(\.\d+)?', v.strip()): v = float(v)
            if isinstance(oro, (int, float)) and isinstance(v, (int, float)) and abs(v - oro) <= max(0.5, 0.15 if isinstance(oro, float) and oro != int(oro) else 0.5): return True
            if isinstance(oro, str) and isinstance(v, str) and oro.lower() in v.lower(): return True
    return False
def oro_de(q):
    o = q.get('oro', q.get('respuesta'))
    try: return float(o)
    except Exception: return o

out = []
for modelo, arch in [('qwen2.5:7b', 'resultados_qwen2.5_7b.jsonl'), ('llama3.1:8b', 'resultados_llama3.1_8b.jsonl')]:
    for l in open(LS/'resultados_experimento'/arch):
        r = json.loads(l)
        if r['condicion'] != 'texto_sql': continue
        q = P[r['id']]; oro = oro_de(q); c = cal[(modelo, r['id'])]['calificacion']
        texto, tablas, inds = ts.esquema(q['pregunta'])
        rt, ri, rf = fuentes(REF.get(r['id']))
        en_esq = None
        if r['id'] in REF:
            en_esq = all(t in tablas for t in rt) and all(i in texto for i in ri)
        sqlf = r.get('sql'); filas = []; err = None
        ult = (r.get('intentos') or [{}])[-1]
        if sqlf:
            try: filas = db.execute(sqlf).fetchmany(61)
            except Exception as e: err = str(e)
        st, si, sf = fuentes(sqlf)
        fuente_ok = (bool(sqlf) and bool((rt and rt <= st) or (ri and ri <= si) or (rf and rf <= sf))) if r['id'] in REF else None
        # clase
        if q['categoria'] == 'sin_respuesta':
            clase = 'abstencion_correcta' if c == 'correcta' else 'invento_dato'
        elif c == 'correcta':
            clase = 'correcta' if contiene(filas, oro) else 'correcta_por_azar'
        elif sqlf is None:
            clase = 'abstencion_sin_sql' if not any(i.get('sql') for i in r.get('intentos', [])) else 'abstencion_tras_fallo'
        elif err or ult.get('error'):
            clase = 'error_sql_sin_corregir'
        elif contiene(filas, oro) and len(filas) == 1:
            clase = 'sql_bien_redaccion_mal'
        elif contiene(filas, oro):
            clase = 'resultado_ambiguo'   # el dato está entre varios renglones
        elif not filas or all(v is None for v in filas[0]):
            clase = 'resultado_vacio'
        elif not fuente_ok:
            clase = 'consulta_equivocada_otra_fuente'
        else:
            clase = 'consulta_equivocada_misma_fuente'
        out.append(dict(modelo=modelo, id=r['id'], categoria=q['categoria'], calificacion=c, clase=clase,
                        esquema_tiene_fuente=en_esq, fuente_ok=fuente_ok, intentos=len(r.get('intentos', [])),
                        errores=sum(1 for i in r.get('intentos', []) if i.get('error')),
                        sql=sqlf, ref=REF.get(r['id']), filas=str(filas[:3])[:120], respuesta=r['respuesta'][:120]))
w = csv.DictWriter(open(LS/'resultados_experimento/clasificacion_texto_sql.csv', 'w', encoding='utf-8-sig', newline=''), fieldnames=list(out[0]))
w.writeheader(); w.writerows(out)
from collections import Counter
for m in ('qwen2.5:7b', 'llama3.1:8b'):
    print(m, Counter(o['clase'] for o in out if o['modelo'] == m).most_common())
for o in out:
    if o['clase'] not in ('correcta', 'abstencion_correcta'):
        print(o['modelo'][:5], o['id'], o['clase'], 'esq:', o['esquema_tiene_fuente'], 'fuente:', o['fuente_ok'], '|', o['filas'][:60])

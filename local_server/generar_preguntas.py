"""Genera preguntas.json: preguntas con su respuesta correcta tomada directamente de los datos (sin pasar por el sistema)."""
import json, sys, unicodedata
from pathlib import Path
D = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('.')
S = json.load(open(D / 'series_uaemex.json', encoding='utf-8'))
T = json.load(open(D / 'tablas_uaemex.json', encoding='utf-8'))
SER = S['series']

def ser(id_, a):
    return float(SER[id_][str(a)])

def fila(tid, ruta, anio):
    t = T[tid]
    for i, f in enumerate(t['filas']):
        if f['ruta'] == ruta and str(i) in t['datos'].get(str(anio), {}):
            return t['datos'][str(anio)][str(i)]
    raise KeyError((tid, ruta, anio))

def col(tid, etiqueta):
    cols = [' › '.join(c) for c in T[tid]['columnas']]
    return str(cols.index(etiqueta))

def celda(tid, ruta, etiqueta, anio):
    return float(fila(tid, ruta, anio).get(col(tid, etiqueta), 0))

def hijos(tid, padre, anio):
    t = T[tid]; d = t['datos'][str(anio)]
    return [(f['ruta'][-1], i) for i, f in enumerate(t['filas']) if len(f['ruta']) == len(padre) + 1 and f['ruta'][:len(padre)] == padre and str(i) in d]

def ptc(ruta, anio):
    return celda('P03', ruta, 'Profesoras / es › Tiempo completo › Hombres', anio) + celda('P03', ruta, 'Profesoras / es › Tiempo completo › Mujeres', anio)

def ficha(tid, concepto, anio=2025):
    for r in T[tid]['renglones'][str(anio)]:
        if r[1] == concepto:
            return r[2]
    raise KeyError((tid, concepto))

Q = []
def add(cat, pregunta, tipo, oro, fuente, unidad=''):
    Q.append({'id': f'Q{len(Q)+1:02d}', 'categoria': cat, 'pregunta': pregunta, 'tipo': tipo, 'oro': oro, 'unidad': unidad, 'fuente': fuente})

# 1. Valor puntual de una serie histórica
add('serie', '¿Cuál fue la matrícula total de la UAEMEX en 2025?', 'numero', ser('His01-46', 2025), 'His01-46 2025')
add('serie', '¿Cuántos alumnos de licenciatura (estudios profesionales) tenía la UAEMEX en 2020?', 'numero', ser('His01-48', 2020), 'His01-48 2020')
add('serie', '¿Cuál fue la matrícula de bachillerato de la UAEMEX en 2018?', 'numero', ser('His01-47', 2018), 'His01-47 2018')
add('serie', '¿Cuántos alumnos de posgrado (estudios avanzados) había en 2023?', 'numero', ser('His01-49', 2023), 'His01-49 2023')
add('serie', '¿Cuántos alumnos de doctorado tenía la UAEMEX en 2025?', 'numero', ser('His01-53', 2025), 'His01-53 2025')
add('serie', '¿Cuánto personal académico de tiempo completo tenía la UAEMEX en 2025?', 'numero', ser('His06-8', 2025), 'His06-8 2025')
add('serie', '¿Cuántos miembros del Sistema Nacional de Investigadoras e Investigadores (SNII) tenía la UAEMEX en 2025?', 'numero', ser('His02-22', 2025), 'His02-22 2025')
add('serie', '¿Cuál fue la eficiencia terminal global de licenciatura en 2024?', 'porcentaje', ser('His01-98', 2024), 'His01-98 2024', '%')
add('serie', '¿Cuántos titulados de licenciatura hubo en 2022?', 'numero', ser('His01-101', 2022), 'His01-101 2022')
add('serie', '¿Cuántos cuerpos académicos consolidados tenía la UAEMEX en 2025?', 'numero', ser('His02-29', 2025), 'His02-29 2025')
add('serie', '¿Cuántos planes de estudio de licenciatura ofrecía la UAEMEX en 2025?', 'numero', ser('His01-9', 2025), 'His01-9 2025')
add('serie', '¿Cuál fue la matrícula del sistema incorporado en 2025?', 'numero', ser('His08-9', 2025), 'His08-9 2025')
add('serie', '¿Cuántos alumnos de bachillerato tenían las escuelas incorporadas en 2025?', 'numero', ser('His08-10', 2025), 'His08-10 2025')
add('serie', '¿Cuál fue la matrícula de maestría en 2019?', 'numero', ser('His01-52', 2019), 'His01-52 2019')

# 2. Cambio entre dos años (serie)
pct = lambda a, b: round((b / a - 1) * 100, 1)
add('cambio', '¿En qué porcentaje creció la matrícula total de la UAEMEX de 2018 a 2025?', 'porcentaje', pct(ser('His01-46', 2018), ser('His01-46', 2025)), 'His01-46 2018, 2025', '%')
add('cambio', '¿Cuánto cambió el personal académico de tiempo completo de la UAEMEX de 2018 a 2025?', 'cambio', ser('His06-8', 2025) - ser('His06-8', 2018), 'His06-8 2018, 2025')
add('cambio', '¿En qué porcentaje aumentaron los miembros del SNII de 2018 a 2025?', 'porcentaje', pct(ser('His02-22', 2018), ser('His02-22', 2025)), 'His02-22 2018, 2025', '%')
add('cambio', '¿Cuántos titulados de licenciatura más hubo en 2025 que en 2018?', 'cambio', ser('His01-101', 2025) - ser('His01-101', 2018), 'His01-101 2018, 2025')
add('cambio', '¿En qué porcentaje cambió la matrícula de posgrado de 2024 a 2025?', 'porcentaje', pct(ser('His01-49', 2024), ser('His01-49', 2025)), 'His01-49 2024, 2025', '%')
add('cambio', '¿Cuánto cambió la matrícula de licenciatura de 2024 a 2025?', 'cambio', ser('His01-48', 2025) - ser('His01-48', 2024), 'His01-48 2024, 2025')
add('cambio', '¿Cuánto cambió la matrícula de bachillerato entre 2020 y 2025?', 'cambio', ser('His01-47', 2025) - ser('His01-47', 2020), 'His01-47 2020, 2025')

# 3. Dato de una tabla por espacio académico
add('tabla', '¿Cuántos alumnos de licenciatura tenía la Facultad de Ingeniería en 2025?', 'numero', celda('A26', ['Facultad', 'Ingeniería'], 'Total', 2025), 'A26 2025 Facultad › Ingeniería · Total')
add('tabla', '¿Cuántos alumnos de licenciatura tenía la Facultad de Medicina en 2022?', 'numero', celda('A26', ['Facultad', 'Medicina'], 'Total', 2022), 'A26 2022 Facultad › Medicina · Total')
add('tabla', '¿Cuántos alumnos tenía el Plantel Cuauhtémoc de la Escuela Preparatoria en 2025?', 'numero', celda('A15', ['Plantel de la Escuela Preparatoria', 'Cuauhtémoc'], 'Total', 2025), 'A15 2025 Cuauhtémoc · Total')
add('tabla', '¿Cuántos alumnos de posgrado tenía la Facultad de Derecho en 2025?', 'numero', celda('A40', ['Facultad', 'Derecho'], 'Total', 2025), 'A40 2025 Facultad › Derecho · Total')
add('tabla', '¿Cuántos profesores de tiempo completo tenía la Facultad de Ingeniería en 2025?', 'numero', ptc(['Facultad', 'Ingeniería'], 2025), 'P03 2025 Facultad › Ingeniería · TC H+M')
add('tabla', '¿Cuántas mujeres estudiaban licenciatura en la Facultad de Derecho en 2025?', 'numero', celda('A26', ['Facultad', 'Derecho'], 'Total › Mujeres', 2025), 'A26 2025 Facultad › Derecho · Total › Mujeres')
add('tabla', '¿Cuántos alumnos tenía la Licenciatura en Arquitectura en 2025?', 'numero', celda('A26', ['Facultad', 'Arquitectura y Diseño', 'Licenciatura en Arquitectura'], 'Total', 2025), 'A26 2025 Lic. en Arquitectura · Total')
add('tabla', '¿Cuántos alumnos de licenciatura tenía la Facultad de Contaduría y Administración en 2018?', 'numero', celda('A26', ['Facultad', 'Contaduría y Administración'], 'Total', 2018), 'A26 2018 Facultad › Contaduría y Administración · Total')

# 4. Ordenamiento
def mayor(tid, padre, etiqueta, anio, menor=False):
    v = [(celda(tid, padre + [n], etiqueta, anio), n) for n, _ in hijos(tid, padre, anio)]
    v = [x for x in v if x[0] > 0]
    return (min if menor else max)(v)[1]
add('orden', '¿Qué facultad tuvo más alumnos de licenciatura en 2025?', 'texto', mayor('A26', ['Facultad'], 'Total', 2025), 'A26 2025 máximo entre facultades')
add('orden', '¿Qué plantel de la Escuela Preparatoria tuvo más alumnos en 2025?', 'texto', mayor('A15', ['Plantel de la Escuela Preparatoria'], 'Total', 2025), 'A15 2025 máximo entre planteles')
fac = [(ptc(['Facultad', n], 2025), n) for n, _ in hijos('P03', ['Facultad'], 2025)]
add('orden', '¿Qué facultad tenía más profesores de tiempo completo en 2025?', 'texto', max(fac)[1], 'P03 2025 máximo TC entre facultades')
add('orden', '¿Qué facultad tuvo menos alumnos de licenciatura en 2025?', 'texto', mayor('A26', ['Facultad'], 'Total', 2025, menor=True), 'A26 2025 mínimo entre facultades')

# 5. Razones y porcentajes calculados
lic_ing = celda('A26', ['Facultad', 'Ingeniería'], 'Total', 2025)
add('razon', '¿Cuántos alumnos de licenciatura hay por cada profesor de tiempo completo en la Facultad de Ingeniería en 2025?', 'razon', round(lic_ing / ptc(['Facultad', 'Ingeniería'], 2025), 1), 'A26 / P03 2025 Ingeniería')
add('razon', '¿Qué porcentaje de la matrícula de licenciatura de la UAEMEX eran mujeres en 2025?', 'porcentaje', round(celda('A12', ['Estudios profesionales'], 'Sistema › Dependiente › Mujeres', 2025) / celda('A12', ['Estudios profesionales'], 'Sistema › Dependiente › Total', 2025) * 100, 1), 'A12 2025 Estudios profesionales, dependiente', '%')
add('razon', '¿Qué porcentaje de los profesores de tiempo completo estaba en el SNII en 2025?', 'porcentaje', round(ser('His02-21', 2025), 1), 'His02-21 2025', '%')
add('razon', '¿Cuántos alumnos de licenciatura hay en promedio por plan de estudios de licenciatura en 2025?', 'razon', round(ser('His01-48', 2025) / ser('His01-9', 2025), 1), 'His01-48 / His01-9 2025')
add('razon', '¿Qué porcentaje de la matrícula total de 2025 correspondía al bachillerato?', 'porcentaje', round(ser('His01-47', 2025) / ser('His01-46', 2025) * 100, 1), 'His01-47 / His01-46 2025', '%')

# 6. Cambio en un espacio académico
add('cambio_espacio', '¿Cuánto cambió la matrícula de licenciatura de la Facultad de Contaduría y Administración de 2018 a 2025?', 'cambio',
    celda('A26', ['Facultad', 'Contaduría y Administración'], 'Total', 2025) - celda('A26', ['Facultad', 'Contaduría y Administración'], 'Total', 2018), 'A26 2018, 2025')
add('cambio_espacio', '¿Cuánto cambió la matrícula del Plantel Cuauhtémoc de la Escuela Preparatoria de 2018 a 2025?', 'cambio',
    celda('A15', ['Plantel de la Escuela Preparatoria', 'Cuauhtémoc'], 'Total', 2025) - celda('A15', ['Plantel de la Escuela Preparatoria', 'Cuauhtémoc'], 'Total', 2018), 'A15 2018, 2025')
add('cambio_espacio', '¿Cuánto cambió el número de profesores de tiempo completo de la Facultad de Medicina de 2018 a 2025?', 'cambio',
    ptc(['Facultad', 'Medicina'], 2025) - ptc(['Facultad', 'Medicina'], 2018), 'P03 2018, 2025')
add('cambio_espacio', '¿Cuánto cambió la matrícula de licenciatura de la Facultad de Ingeniería de 2024 a 2025?', 'cambio',
    celda('A26', ['Facultad', 'Ingeniería'], 'Total', 2025) - celda('A26', ['Facultad', 'Ingeniería'], 'Total', 2024), 'A26 2024, 2025')

# 7. Fichas por espacio
add('ficha', '¿En qué año se fundó el Centro Universitario UAEM Amecameca?', 'numero', float(ficha('U01', 'Año de fundación')), 'U01 2025 Año de fundación')
for tid in ['O15', 'U07', 'O21']:
    if tid in T:
        add('ficha', f'¿En qué año se fundó la {T[tid]["titulo"]}?' if T[tid]['titulo'].startswith('Facultad') else f'¿En qué año se fundó el {T[tid]["titulo"]}?', 'numero', float(ficha(tid, 'Año de fundación')), f'{tid} 2025 Año de fundación')

# 8. Sin respuesta en los datos: lo correcto es decir que no hay información
for p in ['¿Cuál será la matrícula total de la UAEMEX en 2030?',
          '¿Cuántos alumnos tiene la Universidad Nacional Autónoma de México (UNAM)?',
          '¿Cuál fue la matrícula total de la UAEMEX en 1998?',
          '¿Cuántos alumnos de licenciatura tenía la Facultad de Ingeniería en 2012?',
          '¿Cuál es el salario promedio de los profesores de tiempo completo de la UAEMEX?',
          '¿Cuántos alumnos reprobaron Cálculo I en la Facultad de Ingeniería en 2025?']:
    add('sin_respuesta', p, 'abstener', None, 'fuera de los datos')

json.dump(Q, open('preguntas.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
from collections import Counter
print(len(Q), Counter(q['categoria'] for q in Q))
for q in Q: print(q['id'], q['categoria'], q['oro'], '|', q['pregunta'][:80])

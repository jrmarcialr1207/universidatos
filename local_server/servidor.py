"""
Universidatos con IA (UAEMEX): versión local con Ollama.

Uso:
  1. Instala Ollama (https://ollama.com) y descarga un modelo:
         ollama pull qwen2.5:7b
  2. Deja en una misma carpeta: servidor.py, index.html y series_uaemex.json
  3. Ejecuta:  python servidor.py   (en Mac/Linux: python3 servidor.py)
  4. Abre http://localhost:8000

No necesita instalar librerías: solo Python 3.9 o más reciente.

Variables de entorno opcionales:
  MODELO          modelo de Ollama a usar (por omisión qwen2.5:7b)
  OLLAMA_URL      dirección de Ollama (por omisión http://localhost:11434)
  HOST            127.0.0.1 = solo esta computadora; 0.0.0.0 = toda la red local
  PUERTO          puerto web (por omisión 8000)
  MAX_POR_MINUTO  preguntas por minuto permitidas a cada visitante (por omisión 10)
  SIMULTANEAS     preguntas que se procesan a la vez (por omisión 2)
  MODO            guiado       = el servidor interpreta la pregunta y calcula; la IA solo redacta (por omisión,
                                 recomendado para modelos de Ollama). Si la pregunta no encaja, usa «herramientas».
                  herramientas = la IA decide qué consultar y pide cálculos al servidor
                  simple       = la IA solo redacta con los datos del indicador más parecido (más rápido)
  MAX_RONDAS      veces que la IA puede pedir herramientas en una pregunta (por omisión 6)
"""
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CARPETA = Path(__file__).resolve().parent
MODELO = os.environ.get("MODELO", "qwen2.5:7b")
OLLAMA = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
HOST = os.environ.get("HOST", "127.0.0.1")
PUERTO = int(os.environ.get("PUERTO", "8000"))
MAX_POR_MINUTO = int(os.environ.get("MAX_POR_MINUTO", "10"))
SEMAFORO = threading.BoundedSemaphore(int(os.environ.get("SIMULTANEAS", "2")))
MODO = os.environ.get("MODO", "guiado").lower()
MAX_RONDAS = int(os.environ.get("MAX_RONDAS", "6"))

import sys  # noqa: E402

sys.path.insert(0, str(CARPETA))  # calculos.py y buscador.py viven junto a este archivo
from calculos import HERRAMIENTAS, Calculos  # noqa: E402
import guiado  # noqa: E402

DATOS = json.loads((CARPETA / "series_uaemex.json").read_text(encoding="utf-8"))
_ruta_tablas = CARPETA / "tablas_uaemex.json"
TABLAS = json.loads(_ruta_tablas.read_text(encoding="utf-8")) if _ruta_tablas.exists() else {}
CALC = Calculos(DATOS, TABLAS)
IND = {i["id"]: i for i in DATOS["indicadores"]}
SER = {k: {int(a): float(v) for a, v in s.items()} for k, s in DATOS["series"].items()}
ANIO_MIN = min(a for s in SER.values() for a in s)
ANIO_MAX = max(a for s in SER.values() for a in s)

# Ollama suele correr en esta misma computadora: no usar proxies del sistema para llegar a él.
SIN_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))

ESQUEMA = {
    "type": "object",
    "properties": {
        "respuesta": {"type": "string"},
        "id": {"type": "string"},
    },
    "required": ["respuesta", "id"],
}

INSTRUCCIONES = """Eres el asistente estadístico de la Universidad Autónoma del Estado de México (UAEMEX).
Respondes preguntas usando SOLO los datos de las series históricas de la Agenda Estadística que se te entregan.

Reglas:
1. Usa únicamente cifras que aparezcan en los datos: en "valores", "valor_inicial", "valor_final", "cambio", "cambio_porcentual" o "cambio_vs_anio_anterior". Cópialas tal cual. No hagas otras operaciones.
2. Escribe las cifras en formato mexicano: comas para miles y punto para decimales (100,491 y 80.5).
3. Si el indicador tiene unidad, menciónala (por ejemplo "%" o "millones de pesos").
4. Si ninguno de los indicadores responde la pregunta, dilo en la primera frase y menciona el más parecido que sí está disponible. Estas series no tienen datos por facultad ni por programa.
5. Los indicadores del eje "Sistema incorporado" son de escuelas particulares incorporadas, no de la UAEMEX misma. Úsalos solo si la pregunta trata de incorporadas.
6. Responde en español, en 2 a 4 frases, sin listas ni títulos. Formato: empieza directamente con el dato que se pidió, en la primera frase y sin introducciones (por ejemplo «En 2025 la Facultad de Ingeniería tuvo 2,914 alumnos de licenciatura.»). Si el dato no existe en la Agenda Estadística, dilo en la primera frase («No encontré ese dato en la Agenda Estadística.») y después menciona, si lo hay, el dato más parecido que sí está. Termina con una frase aparte que empiece con «Fuente:» y diga de qué tabla o indicador salió el dato y, si cruzaste o calculaste, cómo (por ejemplo «Fuente: tabla A26, Matrícula de estudios profesionales 2025.» o «Fuente: cruce de las tablas A26 y P03; alumnos entre profesores de tiempo completo.»).

Responde solo con JSON: {"respuesta": "texto para el usuario", "id": "id del indicador que mejor responde la pregunta"}"""


# ---------------------------------------------------------------- datos

def unidad(ind):
    r = ind["ruta"].lower()
    if "millones de pesos" in r:
        return "millones de pesos"
    if "miles de pesos" in r:
        return "miles de pesos"
    if re.search(r"por alumn|por computadora|por tutor", r):
        return ""
    if re.search(r"%|porcentaje|índice|indice|eficiencia|tasa", r):
        return "%"
    return ""


def red(v):
    return int(v) if float(v).is_integer() else round(v, 1)


def resumen(id_, desde, hasta, anio):
    ind, s = IND[id_], SER.get(id_, {})
    sel = {a: v for a, v in sorted(s.items()) if desde <= a <= hasta} or dict(sorted(s.items()))
    anios = sorted(sel)
    r = {"id": id_, "eje": ind["eje"], "indicador": ind["ruta"], "unidad": unidad(ind),
         "valores": {str(a): red(v) for a, v in sel.items()}}
    if anios:
        vi, vf = sel[anios[0]], sel[anios[-1]]
        r.update(primer_anio=anios[0], valor_inicial=red(vi), ultimo_anio=anios[-1], valor_final=red(vf))
        if len(anios) > 1:
            r["cambio"] = red(round(vf - vi, 1))
            if vi and r["unidad"] != "%":
                r["cambio_porcentual"] = round((vf - vi) / vi * 100, 1)
    if anio and anio in s and anio - 1 in s:
        r["cambio_vs_anio_anterior"] = {"anio": anio, "valor": red(s[anio]), "anio_anterior": anio - 1,
                                        "valor_anterior": red(s[anio - 1]),
                                        "cambio": red(round(s[anio] - s[anio - 1], 1))}
        if s[anio - 1] and r["unidad"] != "%":
            r["cambio_vs_anio_anterior"]["cambio_porcentual"] = round((s[anio] - s[anio - 1]) / s[anio - 1] * 100, 1)
    return r


# ---------------------------------------------------------------- verificación de cifras

NUM = re.compile(r"(?<![\w.,])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)")


def numeros(texto):
    return [(m, float(m.replace(",", ""))) for m in NUM.findall(texto)]


def permitidos(ids, ser=None):
    ser = ser or SER
    out = []
    for id_ in ids:
        vs = list(ser.get(id_, {}).values())
        out += vs
        for a in vs:
            for b in vs:
                if a != b:
                    out.append(abs(a - b))
                    if a:
                        out.append(abs((b - a) / a * 100))
    return out


def cercano(x, a):
    if abs(x - a) <= max(0.051, abs(a) * 0.0005):
        return True
    return x.is_integer() and abs(x - a) < 0.5 + 1e-9


def numeros_en(obj):
    """Todos los números que aparecen dentro de un resultado de herramienta."""
    if isinstance(obj, bool):
        return []
    if isinstance(obj, (int, float)):
        return [float(obj)]
    if isinstance(obj, dict):
        return [n for v in obj.values() for n in numeros_en(v)]
    if isinstance(obj, list):
        return [n for v in obj for n in numeros_en(v)]
    if isinstance(obj, str):
        return [v for _, v in numeros(obj)]
    return []


def sin_verificar(texto, ids, pregunta, extra=(), ser=None):
    base = permitidos(ids, ser) + list(extra)
    en_pregunta = {v for _, v in numeros(pregunta)}
    malos = []
    for crudo, x in numeros(texto):
        if x in en_pregunta or (x.is_integer() and (x <= 31 or 1990 <= x <= 2100)):
            continue
        if not any(cercano(x * f, a) for a in base for f in (1, 1000, 1_000_000)):
            malos.append(crudo)
    return sorted(set(malos), key=malos.index)


# ---------------------------------------------------------------- Ollama

class ErrorIA(Exception):
    def __init__(self, mensaje, codigo=503):
        super().__init__(mensaje)
        self.codigo = codigo


def ollama(ruta, cuerpo=None, timeout=300):
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(OLLAMA + ruta, data=datos, headers={"Content-Type": "application/json"})
    try:
        with SIN_PROXY.open(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read()).get("error", "")
        except Exception:
            msg = ""
        if "not found" in msg:
            raise ErrorIA(f"El modelo {MODELO} no está descargado. En la computadora del servidor ejecuta: ollama pull {MODELO}")
        raise ErrorIA(f"Ollama respondió con un error: {msg or e.code}")
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        raise ErrorIA("No se pudo conectar con Ollama. Revisa que la aplicación Ollama esté abierta.")


def estado():
    try:
        tags = ollama("/api/tags", timeout=5)
    except ErrorIA as e:
        return {"listo": False, "modelo": MODELO, "mensaje": str(e)}
    nombres = {m.get("name", "") for m in tags.get("models", [])}
    if MODELO in nombres or f"{MODELO}:latest" in nombres:
        return {"listo": True, "modelo": MODELO, "mensaje": "Listo"}
    return {"listo": False, "modelo": MODELO,
            "mensaje": f"Falta descargar el modelo. Ejecuta: ollama pull {MODELO}"}


def preguntar(pregunta, candidatos, desde, hasta, anio):
    if not candidatos:
        raise ErrorIA("No encontré indicadores relacionados con la pregunta.", 400)
    datos = [resumen(i, desde, hasta, anio) for i in candidatos]
    usuario = ("Pregunta: " + pregunta + "\n\nIndicadores disponibles (uno por línea, en JSON):\n"
               + "\n".join(json.dumps(d, ensure_ascii=False) for d in datos))
    cuerpo = {
        "model": MODELO,
        "messages": [{"role": "system", "content": INSTRUCCIONES}, {"role": "user", "content": usuario}],
        "stream": False,
        "format": ESQUEMA,
        "keep_alive": "30m",
        "options": {"temperature": 0.1, "num_ctx": 8192},
    }
    if re.search(r"qwen3|deepseek-r1|gpt-oss", MODELO):
        cuerpo["think"] = False  # modelos que "piensan": respuesta directa, más rápida
    inicio = time.time()
    with SEMAFORO:
        r = ollama("/api/chat", cuerpo)
    contenido = r.get("message", {}).get("content", "")
    try:
        j = json.loads(contenido)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", contenido, re.S)
        if not m:
            raise ErrorIA("La IA no respondió en el formato esperado. Intenta de nuevo.", 502)
        j = json.loads(m.group(0))
    texto = str(j.get("respuesta", "")).strip()
    if not texto:
        raise ErrorIA("La IA devolvió una respuesta vacía. Intenta de nuevo.", 502)
    elegido = str(j.get("id", ""))
    if elegido not in candidatos:
        elegido = candidatos[0] if candidatos else None
    return {"respuesta": texto, "id": elegido, "modelo": MODELO, "modo": "simple", "pasos": [], "graficas": [],
            "sin_verificar": sin_verificar(texto, candidatos, pregunta),
            "segundos": round(time.time() - inicio, 1)}


# ---------------------------------------------------------------- modo con herramientas

INSTRUCCIONES_HERR = """Eres el asistente estadístico de la Universidad Autónoma del Estado de México (UAEMEX).
Respondes con las series históricas 2004-2025 de la Agenda Estadística usando herramientas.

Cómo trabajar:
1. Toda cifra que menciones debe venir de una herramienta: obtener_valores o calcular. No uses cifras de memoria.
2. Para cualquier operación (diferencias, porcentajes, sumas, promedios, crecimiento, proporciones, alumnos por profesor) usa calcular. Nunca hagas cuentas tú mismo.
3. En calcular, refiérete a los indicadores por su id; la herramienta toma los valores exactos.
4. Si los indicadores sugeridos no sirven, usa buscar_indicadores. Si de plano no existe el dato, dilo y menciona el más parecido. Las series no tienen datos por facultad ni por programa: para eso usa las tablas anuales (regla 10).
5. Los indicadores del eje "Sistema incorporado" son de escuelas particulares incorporadas; úsalos solo si preguntan por ellas.
6. Si una herramienta devuelve "error", corrige la llamada o explica que no hay dato.
7. Si la pregunta pide una gráfica, comparar indicadores o ver una evolución, usa graficar (máximo 4 gráficas). La gráfica se dibuja sola con los datos reales: tú solo eliges indicadores, años y tipo. Comenta la gráfica usando las cifras de su "resumen" o "valores_graficados". Si piden gráficas "por separado", haz una gráfica para cada serie. Nunca digas que no puedes hacer gráficas.
8. Para analizar o graficar un resultado calculado año por año (por ejemplo alumnos por PTC, el porcentaje que representa una parte, una suma de niveles o la variación anual), usa primero calcular_serie: crea una serie nueva con id S1, S2… que puedes usar en graficar y en calcular.
9. Cuando haya varios indicadores posibles para un concepto (por ejemplo, el total de PTC registrados en la SEP y el personal académico de tiempo completo), elige el más adecuado y di en la respuesta cuál usaste.
10. Además de las series hay tablas anuales con detalle de 2018 a 2025 (por omisión usa el año más reciente; si piden otro año o comparar años, consulta con anio o usa calcular con la operación cambio sobre la celda, p. ej. A26.f3.c0 desde 2018 hasta 2025; algunas tablas solo existen en un año y algunos renglones cambian de nombre, como los programas que antes de 2025 se separaban por modalidad «(mixta)»). Personal (P01–P18): personal académico y administrativo por espacio universitario, categoría y sexo; PROED; concursos; juicios de promoción; capacitación; carrera administrativa; personal de escuelas incorporadas. Docencia (A01–A69): planes y programas educativos, acreditaciones y posgrados (listas de texto); matrícula por nivel, sistema, municipio, espacio y programa; ingreso; egreso; titulación; eficiencia terminal; reprobación; abandono; alumnado con discapacidad o hablante de lenguas indígenas; estudios avanzados; escuelas incorporadas; tutoría; acervo e infraestructura. Ciencia (C01–C27): PTC registrados en la SEP, con perfil Prodep e investigadores por espacio y grado; miembros del SNII por espacio y nivel (bloques PTC y no PTC); licencias y apoyos académicos; cuerpos académicos y LGAC (listas de texto); proyectos de investigación por espacio, área, fuente de financiamiento y tipo; recursos asignados; productos académicos; revistas y publicaciones de divulgación (listas); Octubre mes de la ciencia; redes de colaboración (lista); becas Verano Delfín; becarios extranjeros (lista); patentes en trámite y diplomados superiores. Extensión (E01–E61): alumnado becado y becas por nivel, espacio, programa, tipo y fuente de financiamiento (montos en miles de pesos); seguro estudiantil y afiliación a servicios de salud; consultorios y atenciones médicas y psicológicas; servicio social y prácticas profesionales por programa; servicios comunitarios y brigadas (lista); CELe y CILC (lenguas); educación continua (lista); convenios por sector, tipo y servicio; emprendimiento; seguimiento de egresados (ocupación, empleo afín, desocupación); Clínica Multidisciplinaria de Salud; deporte y cultura física. Varias tablas de Extensión vienen por nivel educativo (Bachillerato › Plantel…, Estudios profesionales › Facultad…). Difusión (D01–D18): identidad y cultura; talleres culturales por espacio; eventos artísticos y culturales; Casa de las Diligencias; patrimonio e innovación cultural; exposiciones (lista); conferencias; talleres de ciencia y cultura; CeAC; elenco artístico; función y producción editorial; publicaciones (lista); revistas publicadas; presentaciones y producciones teatrales; visitas guiadas por espacio. Gestión (G01–G45): certificación ISO; manuales; finanzas (origen y aplicación de recursos, recursos etiquetados, adquisiciones en miles de pesos); bienes inventariados e inmuebles; obra universitaria; servicios de mantenimiento y servicios generales por tipo y por espacio; salas de lactancia; Potrobús; computadoras por espacio y en red; sistemas y sitios web; comunidades virtuales; videoconferencias; internet inalámbrico; planeación y evaluación; fomento ambiental y residuos peligrosos; protección universitaria; Consejo Universitario; legislación y convenios; igualdad de género (jornadas y participantes); transparencia; comunicación universitaria y redes sociales. Internacionalización (I01–I09): movilidad del alumnado UAEMEX y externo por país, institución y espacio; movilidad del personal; convenios internacionales vigentes. Cobertura (M01): población, matrícula estatal y nacional, matrícula UAEMEX y porcentajes de cobertura y participación por nivel. Presencia (R01–R10): espacios por municipio, institutos y centros de investigación, espacios culturales, CELe, CILC, incubadoras, unidades de emprendimiento, centros deportivos, librerías y DES (listas con domicilio y año de creación). Fichas por espacio: un resumen de cada espacio (año de fundación, alumnado por programa, tutoría, investigación, movilidad, becas, servicio social, personal e infraestructura): O01–O22 organismos académicos (facultades y escuela), U01–U12 centros universitarios, V01–V07 unidades académicas profesionales, N01–N08 institutos y centros de investigación, B01–B11 planteles de la Escuela Preparatoria; úsalas para «ficha», «resumen» o «año de fundación» de un espacio, y para comparar espacios usa las tablas por sección. Para datos por facultad, plantel, centro universitario, UAP, instituto o dependencia, por categoría o por sexo, usa buscar_tablas y luego consultar_tabla (con «grupo», por ejemplo «Facultad», para traer solo sus espacios). Cada celda tiene un id (por ejemplo P02.f23.c3) que puedes usar en calcular, calcular_serie y graficar; para comparar espacios en una gráfica usa graficar con tipo comparar_anio (hasta 30 barras). Las celdas vacías de la tabla original se leen como 0. No sumes columnas de promedios. La «matrícula total» de la UAEMEX es la del sistema dependiente (serie «Matrícula» y sus niveles; 100,491 en 2025). El sistema incorporado (escuelas incorporadas, tabla A12 columnas «Incorporado») se reporta siempre por separado: nunca lo sumes al dependiente ni uses la columna «Total» de A12 como matrícula total. La matrícula de un espacio (facultad, centro universitario, UAP o instituto) cuando la pregunta no dice el nivel es la suma de licenciatura (A26) y posgrado (A40, posgrado por espacio; A39 si A40 no trae ese año); en los planteles es la de bachillerato (A15). Consulta ambas tablas, suma con calcular (para varios años, calcular_serie con operación suma sobre las celdas «Total» del espacio, y grafica esa serie) y da el desglose por nivel. Usa un solo nivel únicamente si la pregunta lo nombra (licenciatura, posgrado, maestría, doctorado o bachillerato). Si la pregunta nombra un nivel (bachillerato, licenciatura o posgrado), usa solo tablas y series de ese nivel; nunca respondas con las de otro. En la Agenda, posgrado se llama «estudios avanzados» y licenciatura «estudios profesionales». La Agenda no publica eficiencia terminal, abandono ni reprobación de posgrado: si los piden, di que no se encontró ese dato para posgrado y menciona para qué niveles sí existe. Cita la tabla usada (por ejemplo «tabla P02, Personal académico y administrativo 2025»). «PTC» y «profesor/a de tiempo completo» (o «personal académico de tiempo completo») son lo mismo. Por omisión los PTC de cada espacio salen de P03 sumando «Profesoras / es › Tiempo completo › Hombres» y «› Mujeres» (en total son 1,572 en 2025); C01 son solo los PTC registrados en la SEP, C02 los de perfil Prodep y C04 los del SNII: úsalas solo si la pregunta menciona SEP, Prodep, SNII o grado académico.

Respuesta final: en español, 2 a 5 frases, sin listas ni títulos. Copia las cifras tal como salieron de las herramientas, en formato mexicano (100,491 y 2.6%), con su unidad. Formato: empieza directamente con el dato que se pidió, en la primera frase y sin introducciones (por ejemplo «En 2025 la Facultad de Ingeniería tuvo 2,914 alumnos de licenciatura.»). Si el dato no existe en la Agenda Estadística, dilo en la primera frase («No encontré ese dato en la Agenda Estadística.») y después menciona, si lo hay, el dato más parecido que sí está. Termina con una frase aparte que empiece con «Fuente:» y diga de qué tabla o indicador salió el dato y, si cruzaste o calculaste, cómo (por ejemplo «Fuente: tabla A26, Matrícula de estudios profesionales 2025.» o «Fuente: cruce de las tablas A26 y P03; alumnos entre profesores de tiempo completo.»)."""


def llamadas_en_texto(contenido):
    """Algunos modelos escriben la llamada a herramienta como texto JSON; la recuperamos."""
    m = re.search(r"\{.*\}", contenido or "", re.S)
    if not m:
        return []
    try:
        j = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    lista = j if isinstance(j, list) else [j]
    out = []
    for c in lista:
        if isinstance(c, dict) and c.get("name") in ("buscar_indicadores", "obtener_valores", "calcular"):
            out.append({"function": {"name": c["name"], "arguments": c.get("arguments") or c.get("parameters") or {}}})
    return out


class SinHerramientas(Exception):
    pass


def preguntar_con_herramientas(pregunta, candidatos, desde, hasta, anio):
    ses = CALC.sesion()  # las series calculadas viven solo durante esta pregunta
    sugeridos = "\n".join(f"- {i}: {ses.nombre(i)} ({IND[i]['eje']})" for i in candidatos)
    pista = ""
    if anio:
        pista = f"\nLa pregunta menciona el año {anio}."
    elif desde != ANIO_MIN or hasta != ANIO_MAX:
        pista = f"\nLa pregunta se refiere al periodo {desde}-{hasta}."
    mensajes = [
        {"role": "system", "content": INSTRUCCIONES_HERR},
        {"role": "user", "content": f"Pregunta: {pregunta}{pista}\n\nIndicadores sugeridos (id: indicador):\n{sugeridos}"},
    ]
    opciones = {"temperature": 0.1, "num_ctx": 8192}
    pasos, ids_usados, numeros_herr, graficas = [], [], [], []
    inicio, texto = time.time(), ""

    def llamar(con_herramientas):
        cuerpo = {"model": MODELO, "messages": mensajes, "stream": False, "keep_alive": "30m", "options": opciones}
        if con_herramientas:
            cuerpo["tools"] = HERRAMIENTAS
        if re.search(r"qwen3|deepseek-r1|gpt-oss", MODELO):
            cuerpo["think"] = False
        try:
            return ollama("/api/chat", cuerpo).get("message", {})
        except ErrorIA as e:
            if "does not support tools" in str(e):
                raise SinHerramientas()
            raise

    with SEMAFORO:
        for _ in range(MAX_RONDAS):
            msg = llamar(True)
            llamadas = msg.get("tool_calls") or llamadas_en_texto(msg.get("content", ""))
            if not llamadas:
                texto = msg.get("content", "")
                break
            mensajes.append({"role": "assistant", "content": msg.get("content", ""), "tool_calls": llamadas})
            for ll in llamadas[:4]:
                fn = ll.get("function", {})
                nombre, args = fn.get("name", ""), fn.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                if nombre == "graficar" and len(graficas) >= 4:
                    res = {"error": "Ya hay 4 gráficas en esta respuesta; no se pueden agregar más."}
                else:
                    res = ses.ejecutar(nombre, args)
                if "grafica" in res:
                    graficas.append(res["grafica"])
                ids_usados += [i for i in ses.ids_en(args) if i not in ids_usados]
                if res.get("id") in ses.calculadas and res["id"] not in ids_usados:
                    ids_usados.append(res["id"])
                if "series" in res:
                    ids_usados += [s["id"] for s in res["series"] if s["id"] not in ids_usados]
                numeros_herr += numeros_en(res)
                pasos.append({"herramienta": nombre, "descripcion": res.get("descripcion") or res.get("error", ""),
                              "error": "error" in res})
                mensajes.append({"role": "tool", "content": json.dumps(res, ensure_ascii=False), "tool_name": nombre})
        else:
            mensajes.append({"role": "user", "content": "Ya no puedes usar más herramientas. Responde ahora con lo que obtuviste."})
            texto = llamar(False).get("content", "")

    texto = texto.strip()
    try:  # por si el modelo respondió en JSON
        j = json.loads(texto)
        if isinstance(j, dict) and isinstance(j.get("respuesta"), str):
            texto = j["respuesta"].strip()
    except json.JSONDecodeError:
        pass
    if not texto:
        raise ErrorIA("La IA devolvió una respuesta vacía. Intenta de nuevo.", 502)
    con_datos = [i for i in ids_usados if i in ses.ser]
    originales = [i for i in con_datos if i in SER]
    elegido = graficas[0]["ids"][0] if graficas else (originales[0] if originales else (candidatos[0] if candidatos else None))
    usadas = {i for g in graficas for i in g["ids"]} | set(con_datos)
    def con_dependencias(i, vistos):
        if i in ses.calculadas and i not in vistos:
            vistos.add(i)
            for j in ses.calculadas[i]["ids"]:
                con_dependencias(j, vistos)
        return vistos
    calc_enviar = set()
    for i in usadas:
        con_dependencias(i, calc_enviar)
    return {"respuesta": texto, "id": elegido, "modelo": MODELO, "modo": "herramientas", "pasos": pasos,
            "graficas": graficas,
            "series_calculadas": {i: ses.calculadas[i] for i in sorted(calc_enviar, key=lambda x: int(x[1:]))},
            "sin_verificar": sin_verificar(texto, (con_datos or candidatos[:3])[:8], pregunta, numeros_herr, ses.ser),
            "segundos": round(time.time() - inicio, 1)}


INSTRUCCIONES_GUIADO = """Eres el asistente estadístico de la Universidad Autónoma del Estado de México (UAEMEX).
Redacta la respuesta a la pregunta usando SOLO la lista HECHOS: ya están consultados en la Agenda Estadística y calculados por el sistema.
Reglas:
1. No agregues cifras que no estén en HECHOS y no hagas cuentas.
2. Copia las cifras tal como aparecen (formato 100,491 y 7.4%), con su unidad si la tienen.
3. Empieza directamente con el dato que se pidió, en la primera frase y sin introducciones. Termina con una frase aparte que empiece con «Fuente:» y diga de qué tabla o indicador salen los datos y, si HECHOS indica un cruce o un cálculo, cómo se obtuvo (por ejemplo «Fuente: tabla P02, Personal académico y administrativo 2025.»).
4. El PRIMER hecho es el que mejor responde la pregunta: empieza por él. Los demás son contexto; no mezcles niveles (licenciatura, posgrado, bachillerato) ni tablas distintas como si fueran lo mismo.
4b. Si hay muchas cifras, destaca las más importantes para la pregunta; no las enumeres todas.
5. Si HECHOS no responde la pregunta, dilo en la primera frase («No encontré ese dato en la Agenda Estadística.»); si responde solo una parte, di qué parte no se encontró.
5b. Si la pregunta nombra un espacio (facultad, plantel, centro, unidad) que HECHOS no menciona, di que no encontraste datos de ese espacio; nunca le atribuyas totales de toda la universidad ni cifras de otros espacios.
6. Si HECHOS dice que se muestra una gráfica o una tabla, menciona que está abajo; no copies toda la tabla en el texto.
6b. PTC significa profesoras y profesores de tiempo completo (nunca «personal técnico científico»). SNII es el Sistema Nacional de Investigadoras e Investigadores.
7. Responde en español, en 2 a 5 frases, sin listas, títulos ni negritas.
Responde solo con JSON: {"respuesta": "texto para el usuario"}"""


def preguntar_guiado(pregunta, desde, hasta, anio):
    ses = CALC.sesion()
    try:
        plan = guiado.planear(ses, pregunta)
    except Exception as e:  # una pregunta rara no debe tumbar la respuesta: se usa el otro modo
        print(f"Aviso: el modo guiado falló ({type(e).__name__}: {e}); se usa el modo con herramientas.", flush=True)
        plan = None
    if not plan:
        return None
    hechos = "\n".join(f"- {h}" for h in plan.hechos)
    cuerpo = {"model": MODELO, "stream": False, "keep_alive": "30m", "format": {"type": "object", "properties": {"respuesta": {"type": "string"}}, "required": ["respuesta"]},
              "options": {"temperature": 0.1, "num_ctx": 8192},
              "messages": [{"role": "system", "content": INSTRUCCIONES_GUIADO},
                           {"role": "user", "content": f"Pregunta: {pregunta}\n\nHECHOS:\n{hechos}"}]}
    if re.search(r"qwen3|deepseek-r1|gpt-oss", MODELO):
        cuerpo["think"] = False
    inicio = time.time()
    with SEMAFORO:
        contenido = ollama("/api/chat", cuerpo).get("message", {}).get("content", "")
    try:
        texto = str(json.loads(contenido).get("respuesta", "")).strip()
    except (json.JSONDecodeError, AttributeError):
        m = re.search(r"\{.*\}", contenido, re.S)
        texto = str(json.loads(m.group(0)).get("respuesta", "")).strip() if m else contenido.strip()
    if not texto:
        raise ErrorIA("La IA devolvió una respuesta vacía. Intenta de nuevo.", 502)
    calc_usadas = {i: ses.calculadas[i] for i in plan.ids + [x for g in plan.graficas for x in g["ids"]] if i in ses.calculadas}
    for s in list(calc_usadas.values()):
        for dep in s["ids"]:
            if dep in ses.calculadas:
                calc_usadas[dep] = ses.calculadas[dep]
    originales = [i for i in plan.ids if i in SER]
    elegido = plan.graficas[0]["ids"][0] if plan.graficas else (originales[0] if originales else (plan.ids[0] if plan.ids else None))
    extra = [v for h in plan.hechos for _, v in numeros(h)]
    return {"respuesta": texto, "id": elegido, "modelo": MODELO, "modo": "guiado", "pasos": plan.pasos,
            "graficas": plan.graficas, "tablas": plan.tablas, "series_calculadas": calc_usadas,
            "sin_verificar": sin_verificar(texto, [i for i in plan.ids if i in ses.ser][:8], pregunta, extra, ses.ser),
            "segundos": round(time.time() - inicio, 1)}


def responder(pregunta, candidatos, desde, hasta, anio):
    if not candidatos and MODO == "simple":
        raise ErrorIA("No encontré indicadores relacionados con la pregunta.", 400)
    if MODO == "guiado":
        r = preguntar_guiado(pregunta, desde, hasta, anio)
        if r:
            return r
        print("Aviso: la pregunta no encaja en el modo guiado; se usa el modo con herramientas.", flush=True)
    if MODO != "simple":
        try:
            return preguntar_con_herramientas(pregunta, candidatos, desde, hasta, anio)
        except SinHerramientas:
            print(f"Aviso: {MODELO} no admite herramientas; se usa el modo simple.", flush=True)
    return preguntar(pregunta, candidatos, desde, hasta, anio)


# ---------------------------------------------------------------- límites por visitante

_historial, _candado = {}, threading.Lock()


def permitido(ip):
    ahora = time.time()
    with _candado:
        h = [t for t in _historial.get(ip, []) if ahora - t < 60]
        ok = len(h) < MAX_POR_MINUTO
        if ok:
            h.append(ahora)
        _historial[ip] = h
        return ok


# ---------------------------------------------------------------- servidor web

class Manejador(BaseHTTPRequestHandler):
    server_version = "UniversidatosIA/1.0"

    def _json(self, codigo, obj):
        datos = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(datos)

    def do_GET(self):
        ruta = self.path.split("?", 1)[0]
        if ruta in ("/", "/index.html"):
            datos = (CARPETA / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(datos)))
            self.end_headers()
            self.wfile.write(datos)
        elif ruta == "/api/estado":
            self._json(200, estado())
        else:
            self._json(404, {"error": "No encontrado"})

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/api/preguntar":
            return self._json(404, {"error": "No encontrado"})
        if not permitido(self.client_address[0]):
            return self._json(429, {"error": "Demasiadas preguntas seguidas. Espera un minuto e intenta de nuevo."})
        largo = int(self.headers.get("Content-Length") or 0)
        if largo <= 0 or largo > 20_000:
            return self._json(400, {"error": "Solicitud inválida."})
        try:
            p = json.loads(self.rfile.read(largo))
            pregunta = str(p.get("pregunta", "")).strip()[:500]
            candidatos = [str(c) for c in p.get("candidatos", []) if str(c) in IND and str(c) in SER][:10]
            def anio(k):
                v = p.get(k)
                return int(v) if isinstance(v, (int, float)) and 1990 <= v <= 2100 else None
            desde, hasta, un_anio = anio("desde"), anio("hasta"), anio("anio")
        except Exception:
            return self._json(400, {"error": "Solicitud inválida."})
        if not pregunta:
            return self._json(400, {"error": "Escribe una pregunta."})
        desde = max(ANIO_MIN, desde or ANIO_MIN)
        hasta = min(ANIO_MAX, hasta or ANIO_MAX)
        if desde > hasta:
            desde, hasta = hasta, desde
        try:
            self._json(200, responder(pregunta, candidatos, desde, hasta, un_anio))
        except ErrorIA as e:
            self._json(e.codigo, {"error": str(e)})

    def log_message(self, formato, *args):
        print(f"[{time.strftime('%H:%M:%S')}] {self.client_address[0]} {formato % args}", flush=True)


def main():
    e = estado()
    print("Universidatos con IA (versión local con Ollama)")
    print(f"  Modelo: {MODELO} · Ollama: {OLLAMA} · Modo: {MODO}")
    print(f"  Estado: {e['mensaje']}")
    direccion = "localhost" if HOST in ("127.0.0.1", "localhost") else HOST
    print(f"  Abre en el navegador: http://{direccion}:{PUERTO}")
    if HOST == "0.0.0.0":
        print("  (Otras computadoras de la red pueden entrar con la IP de esta computadora)")
    print("  Para detenerlo presiona Ctrl+C\n", flush=True)
    servidor = ThreadingHTTPServer((HOST, PUERTO), Manejador)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")


if __name__ == "__main__":
    main()

"""Modo guiado: el código interpreta la pregunta y hace las consultas y cálculos.
El modelo de Ollama solo redacta la respuesta con los HECHOS ya calculados.

Casos que resuelve:
  1. Un espacio universitario concreto («datos de la Facultad de Ingeniería sobre personal»).
  2. Comparar espacios («¿qué facultad tiene más personal académico?», «PTC por centro universitario»,
     «personal de Medicina y Odontología»), incluido el porcentaje de mujeres u hombres.
  3. Un indicador de las series con año, periodo o crecimiento («matrícula licenciatura 2020»,
     «crecimiento de la matrícula desde 2015»).
Si la pregunta no encaja, planear() devuelve None y el servidor usa el modo con herramientas.
"""
import re

from buscador import analizar, norm

GRUPOS = [
    (r"\bfacultad(es)?\b", "facultad"),
    (r"\bplantel(es)?\b|\bprepas?\b|\bpreparatorias?\b|\bbachilleratos? de la uaem", "plantel"),
    (r"\bcentros? universitarios?\b", "centro universitario"),
    (r"\buaps?\b|\bunidad(es)? academicas? profesional(es)?\b", "unidad academica"),
    (r"\binstitutos?\b|\bcentros? de investigacion\b", "instituto"),
    (r"\bdependencias?\b|\badministracion central\b|\bsecretarias?\b", "dependencia"),
    (r"\bescuelas? incorporadas?\b|\bincorporadas?\b|\bparticulares\b", "incorporada"),
]
NO_ESPACIO = {"total", "facultad", "escuela", "externos", "sin adscripcion", "otros", "instituto", "institucion incorporada"}
COMPARAR = re.compile(r"\bpor (facultad|plantel|centro|uap|unidad|instituto|dependencia|espacio|escuela|institucion)"
                      r"|\b(cada|todas las|todos los|que|cual|cuales|en que) (facultad|plantel|centro|uap|unidad|dependencia|instituto|escuela|institucion)"
                      r"|\b(facultades|planteles|centros universitarios|dependencias|uaps|institutos|escuelas incorporadas)\b"
                      r"|\b(mas|menos|mayor|menor|ranking|compara|comparar|comparacion)\b")
GRAFICA = re.compile(r"\bgrafic|\bgrafiq|\bgrafique|\bbarras\b|\bchart\b|\bdiagrama\b")
PORCENTAJE = re.compile(r"porcentaje|%|proporcion|que parte|participacion")
CRECIMIENTO = re.compile(r"crecimiento|crecio|crecido|aument|disminu|cambio|cambiado|variacion|evolucion|tendencia|comportamiento")
PERSONAL = re.compile(r"personal|profesor|docente|academic|administrativ|trabajador|ptc|tiempo completo|asignatura|sindicaliz|confianza|plantilla")
PROGRAMA = re.compile(r"proed|proinv|estimulo|concurso|oposicion|juicio|promocion|capacit|curso|diplomad|carrera administrativa|evaluac|perfil de puesto")
DIVISION = re.compile(r"\bentre\b.*\b(ptc|profesor|docente|personal|alumn|matricula)|\bpor cada\b|\bdivid")


def fmt(v):
    if v is None:
        return "—"
    v = float(v)
    return f"{int(v):,}" if v.is_integer() else f"{v:,.2f}".rstrip("0").rstrip(".")


def raiz(w):
    return re.sub(r"(es|s)$", "", w) if len(w) > 5 else w


class Plan:
    def __init__(self, ses, pregunta):
        self.ses, self.pregunta = ses, pregunta
        self.hechos, self.pasos, self.graficas, self.ids, self.tablas = [], [], [], [], []

    def paso(self, texto, error=False):
        self.pasos.append({"herramienta": "guiado", "descripcion": texto, "error": error})

    def usa(self, *ids):
        for i in ids:
            if i and i not in self.ids:
                self.ids.append(i)

    def grafica(self, args):
        r = self.ses.ejecutar("graficar", args)
        if "grafica" in r:
            self.graficas.append(r["grafica"])
            self.paso(r["descripcion"])
            return True
        self.paso("No se pudo graficar: " + r.get("error", ""), True)
        return False


def indice_espacios(tab):
    """(nombre normalizado, nombre, grupo normalizado) de cada espacio que aparece en las tablas."""
    vistos = {}
    for T in tab.values():
        if T.get("tipo") == "lista":
            continue
        for f in T["filas"]:
            if len(f["ruta"]) == 2 and GRUPO_RX.match(norm(f["ruta"][0])):  # solo espacios dentro de un grupo real
                k = (norm(f["ruta"][1]), norm(f["ruta"][0]))
                if k[0] not in NO_ESPACIO and len(k[0]) >= 4:
                    vistos.setdefault(k, f["ruta"][1].strip())
    return sorted(((n, nombre, g) for (n, g), nombre in vistos.items()), key=lambda x: -len(x[0]))


def _edicion(a, b):
    """Distancia de edición (Levenshtein) entre dos palabras cortas."""
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _parecido(n, toks):
    """Distancia de la mejor coincidencia aproximada del nombre n en la pregunta (Tiaguistenco → Tianguistenco),
    o None si no hay. Solo nombres largos y a lo más 1 (o 2 si el nombre es largo) letras de diferencia."""
    partes = n.split()
    k = len(partes)
    if len(n) < 7:
        return None
    mejor = None
    for i in range(len(toks) - k + 1):
        w = " ".join(toks[i:i + k])
        if abs(len(w) - len(n)) <= 2 and w[0] == n[0]:
            d = _edicion(w, n)
            if d <= (1 if len(n) < 10 else 2) and (mejor is None or d < mejor):
                mejor = d
    return mejor


def detectar(q, espacios):
    grupos = [tok for rx, tok in GRUPOS if re.search(rx, q)]
    texto = " " + q + " "
    hallados = []
    for n, nombre, g in espacios:
        if re.search(rf"(?<![a-z0-9]){re.escape(n)}(?![a-z0-9])", texto):
            if grupos and not any(tok in g for tok in grupos):
                continue
            hallados.append((n, nombre, g))
    if not hallados:  # sin coincidencia exacta: tolerar una errata en nombres largos
        toks = re.findall(r"[a-z0-9]+", q)
        cand = [(d, (n, nombre, g)) for n, nombre, g in espacios
                if (d := _parecido(n, toks)) is not None and not (grupos and not any(tok in g for tok in grupos))]
        if cand:
            dmin = min(d for d, _ in cand)
            hallados = [e for d, e in cand if d == dmin]
    # quitar nombres contenidos en otro más largo ya encontrado («ciencias» dentro de «ciencias agricolas»)
    finales = []
    for h in hallados:
        if not any(h[0] != o[0] and re.search(rf"(?<![a-z0-9]){re.escape(h[0])}(?![a-z0-9])", o[0]) for o in hallados):
            finales.append(h)
    return grupos, finales


def filas_de(T, n_esp, g_norm):
    return [i for i, f in enumerate(T["filas"]) if len(f["ruta"]) == 2 and norm(f["ruta"][1]) == n_esp and norm(f["ruta"][0]) == g_norm]


def fila_grupo(T, g_norm):
    for i, f in enumerate(T["filas"]):
        if len(f["ruta"]) == 1 and norm(f["ruta"][0]) == g_norm:
            return i
    return None


ANIO_PEDIDO = None   # año que pide la pregunta (p. ej. «en 2024»); si no, el más reciente
CAMBIO_ANIOS = None  # (anterior, actual) cuando la pregunta compara años
CAMBIO_Q = re.compile(r"cambi|crec|aument|disminu|se redujo|redujeron|baj[oó]|subi[oó]|variaci|evoluci|ano anterior|ciclo anterior|"
                      r"respecto (al|a)l? (ano|ciclo)|con respecto|frente a 20\d\d|vs\.? ?20\d\d|contra 20\d\d")


def anio_de(T):
    if ANIO_PEDIDO and str(ANIO_PEDIDO) in T["datos"]:
        return str(ANIO_PEDIDO)
    return sorted(T["datos"])[-1]


def anio_previo(T, a):
    prev = [y for y in T["datos"] if int(y) < int(a)]
    if CAMBIO_ANIOS and str(CAMBIO_ANIOS[0]) in T["datos"]:
        return str(CAMBIO_ANIOS[0])
    return max(prev, key=int) if prev else None


def texto_cambio(T, a, f, c):
    """« En 2024: 1,224 (cambio −84, −6.9%).» cuando la pregunta compara años y hay dato del año anterior."""
    if not CAMBIO_ANIOS:
        return ""
    a0 = anio_previo(T, a)
    v0, v1 = (valor(T, a0, f, c) if a0 else None), valor(T, a, f, c)
    if v0 is None or v1 is None:
        return f" No hay dato de {a0 or 'un año anterior'} para comparar." if a0 or CAMBIO_ANIOS else ""
    d = v1 - v0
    pct = f", {'+' if d >= 0 else '−'}{fmt(round(abs(d) / v0 * 100, 1))}%" if v0 and c not in T.get("no_sumables", []) else ""
    return f" En {a0}: {fmt(v0)} (cambio {'+' if d >= 0 else '−'}{fmt(abs(d))}{pct})."


def valor(T, a, f, c):
    return T["datos"][a].get(str(f), {}).get(str(c))


def columnas_total(T):
    cols = T["columnas"]
    tot = [j for j, c in enumerate(cols) if c[-1] == "Total" or c == ["Total"]]
    sexo = [j for j, c in enumerate(cols) if len(c) == 2 and c[0] == "Total" and c[1] in ("Hombres", "Mujeres")]
    sel = list(dict.fromkeys(tot + sexo))
    return (sel or list(range(len(cols))))[:8]


def palabras(q):
    q = re.sub(r"\bptc\b", "profesores tiempo completo", q)
    q = re.sub(r"\b(alumnos?|estudiantes?)\b", r"\1 matricula", q)  # «alumnos» también es matrícula
    return {raiz(w) for w in q.split() if len(w) >= 3}


VACIAS_COL = {"por", "del", "las", "los", "una", "uno", "que", "con", "para", "cada", "cuanto", "cuanta",
              "cuantos", "cuantas", "hay", "tiene", "tienen", "total", "grafica", "graficar", "compara", "comparar"}


def elegir_columna(T, q):
    qw = {w for w in palabras(q) if w not in VACIAS_COL}
    if any(c == ["Total"] for c in T["columnas"]):  # con columna Total, las palabras del título no eligen columna («servicio social»)
        tit = norm(T.get("titulo", ""))
        qw = {w for w in qw if w not in tit}
    quiere_m, quiere_h = bool(re.search(r"\bmujer", q)), bool(re.search(r"\bhombre", q))
    quiere_pct = bool(re.search(r"porcentaje|%|proporcion", q)) and not (quiere_m or quiere_h)

    def puntos(j):
        c = T["columnas"][j]
        p = norm(" ".join(c))
        s = sum(1 for w in qw if w in p)
        if "mujeres" in p:
            s += 2 if quiere_m else -1
        elif "hombres" in p:
            s += 2 if quiere_h else -1
        if quiere_pct and ("%" in p or "porcentaje" in p or "indice" in p or "tasa" in p):
            s += 2
        if c == ["Total"]:
            s += 1
        elif c[-1] == "Total":
            s += 0.5
        return s - 0.1 * len(c)
    return max(range(len(T["columnas"])), key=lambda j: (puntos(j), -j))


# ------------------------------------------------------------------ rutas

ALUMNADO = re.compile(r"matricul|alumn|estudiant|egresad|titulad|aspirant|ingreso|eficiencia|abandono|reprobac|inscrit|discapacid")
POR_PROGRAMA = re.compile(r"por (programa|carrera|licenciatura|plan|maestria|doctorado|especialidad)|programas|carreras|licenciaturas|desglos")


def desglose_programas(plan, vistas, nombre, q):
    """Grafica los programas educativos (renglones hijos) del espacio en la primera tabla que los tenga."""
    ses = plan.ses
    for tid, f in vistas:
        T = ses.tab[tid]
        ruta = T["filas"][f]["ruta"]
        desc = [i for i, x in enumerate(T["filas"]) if len(x["ruta"]) > len(ruta) and x["ruta"][:len(ruta)] == ruta]
        rutas = [T["filas"][i]["ruta"] for i in desc]
        # los programas son las hojas (en posgrado van debajo de Maestría / Doctorado)
        hijos = [i for i in desc if not any(len(r) > len(T["filas"][i]["ruta"]) and r[:len(T["filas"][i]["ruta"])] == T["filas"][i]["ruta"] for r in rutas)]
        if len(hijos) < 2:
            continue
        a = anio_de(T)
        c = elegir_columna(T, q)
        col = " › ".join(T["columnas"][c])
        datos = [(i, valor(T, a, i, c)) for i in hijos]
        datos = sorted([(i, v) for i, v in datos if v is not None], key=lambda x: -x[1])
        if len(datos) < 2:
            continue
        ids = []
        for i, _ in datos[:30]:
            cid = f"{tid}.f{i}.c{c}"
            ses.asegurar_celda(cid)
            plan.usa(cid)
            ids.append(cid)
        tot = valor(T, a, f, c)
        plan.paso(f"Consultó los {len(datos)} programas de {nombre} en la tabla {tid}, columna «{col}»")
        plan.hechos.insert(0, f"Tabla {tid} «{T['titulos'][a]}», {nombre}, columna «{col}», por programa educativo de mayor a menor: "
                              + "; ".join(f"{T['filas'][i]['ruta'][-1].strip()} {fmt(v)}" for i, v in datos)
                              + (f". Total de {nombre}: {fmt(tot)}." if tot is not None else "."))
        if plan.grafica({"tipo": "comparar_anio", "ids": ids, "titulo": f"{nombre} por programa · {col} · {T['titulo']} {a}"}):
            plan.hechos.insert(1, f"Se muestra una gráfica de barras con cada programa educativo de {nombre} (tabla {tid}).")
        # tabla completa del desglose: hombres, mujeres y total de cada programa
        cols_t = [" › ".join(x) for x in T["columnas"]]
        extra = [cols_t.index(x) for x in ("Total › Hombres", "Total › Mujeres") if x in cols_t and cols_t.index(x) != c]
        enc = ["Programa educativo"] + [cols_t[j] for j in extra] + [col]
        filas_t = [{"nombre": T["filas"][i]["ruta"][-1].strip(), "textos": [fmt(valor(T, a, i, j)) for j in extra] + [fmt(v)]} for i, v in datos]
        if tot is not None:
            filas_t.append({"nombre": f"Total de {nombre}", "textos": [fmt(valor(T, a, f, j)) for j in extra] + [fmt(tot)]})
        plan.tablas.append({"titulo": f"{T['titulos'][a]} · {nombre} por programa educativo"[:160], "encabezados": enc, "filas": filas_t,
                            "fuente": f"Fuente: Agenda Estadística, tabla {tid}."})
        plan.hechos.insert(2, f"Se muestra abajo la tabla completa con los {len(datos)} programas de {nombre} (tabla {tid}).")
        return True
    return False


MATR_ESP_Q = re.compile(r"matricul|alumn|estudiant|inscrit")
MATR_ESP_NO = re.compile(r"egresad|titulad|ingreso|becad|beca|discapac|abandono|reprob|indigena|eficiencia|mujer|hombre|sexo|"
                         r"tutor|movilidad|servicio social|practicas|seguro|aspirant|por (grado|semestre|ano de avance)")
NUM_TXT = {"dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8}


def anios_matricula(q, disponibles):
    """Años que pide la pregunta: un rango, «los últimos N años», «desde 2020», una evolución o solo el más reciente."""
    disp = sorted(disponibles)
    aq = sorted({int(x) for x in re.findall(r"\b(20[12]\d)\b", q)})
    m = re.search(r"ultim[oa]s? (\d+|" + "|".join(NUM_TXT) + r") anos", q)
    if m:
        n = int(m.group(1)) if m.group(1).isdigit() else NUM_TXT[m.group(1)]
        return disp[-n:]
    if len(aq) >= 2:
        return [a for a in disp if aq[0] <= a <= aq[-1]]
    if aq and re.search(r"\b(desde|a partir de|de)\s+" + str(aq[0]), q) and not re.search(r"\ben\s+" + str(aq[0]), q):
        return [a for a in disp if a >= aq[0]]
    if aq:
        return [a for a in disp if a == aq[0]] or disp[-1:]
    if re.search(r"evoluci|historic|por ano|cada ano|anual|tendencia|crec|cambi|comportamiento|años", q):
        return disp
    return disp[-1:]


def matricula_espacio(plan, esp, q):
    """Matrícula de un espacio sin nivel en la pregunta: licenciatura (A26) + posgrado (A40, o A39 donde A40 no tiene el año)
    + bachillerato (A15), por año."""
    n, nombre, g = esp
    ses = plan.ses
    fuentes = [("A26", "Licenciatura"), ("A40", "Posgrado"), ("A39", "Posgrado"), ("A15", "Bachillerato")]
    por_nivel = {}   # nivel -> {anio: (valor, tid, id de celda)}
    grupo_txt = None
    for tid, nivel in fuentes:
        T = ses.tab.get(tid)
        if not T or T.get("tipo") == "lista":
            continue
        filas = filas_de(T, n, g)
        if not filas:  # «centro universitario uaem texcoco» en la pregunta; «Texcoco» dentro del grupo en las tablas de matrícula
            corto = re.sub(r"^(facultad de|escuela de|centro universitario( uaem)?|unidad academica profesional|plantel)\s+", "", n)
            filas = [i for i, x in enumerate(T["filas"]) if len(x["ruta"]) == 2 and norm(x["ruta"][1]) == corto
                     and norm(x["ruta"][0]).split()[:1] == g.split()[:1]]
        cols = [j for j, c in enumerate(T["columnas"]) if c == ["Total"]]
        if not filas or not cols:
            continue
        f, c = filas[0], cols[0]
        grupo_txt = grupo_txt or re.sub(r"\s*\*+$", "", T["filas"][f]["ruta"][0].strip())
        for a in T["datos"]:
            v = valor(T, a, f, c)
            if v is not None and int(a) not in por_nivel.setdefault(nivel, {}):
                por_nivel[nivel][int(a)] = (v, tid, f"{tid}.f{f}.c{c}")
    por_nivel = {k: v for k, v in por_nivel.items() if v}
    if not por_nivel:
        return False
    niveles = [k for k in ("Bachillerato", "Licenciatura", "Posgrado") if k in por_nivel]
    disponibles = set().union(*(set(d) for d in por_nivel.values()))
    anios = anios_matricula(q, disponibles)
    # solo años con dato en todos los niveles que tiene el espacio (si no, el total no sería comparable)
    anios = [a for a in anios if all(a in por_nivel[k] for k in niveles)] or anios
    if not anios:
        return False
    nombre = re.sub(r"^(Centro Universitario UAEM|Unidad Académica Profesional|Facultad de|Plantel)\s+", "", nombre, flags=re.I) if grupo_txt else nombre
    etiqueta = f"{nombre} ({grupo_txt})" if grupo_txt else nombre
    total = {a: sum(por_nivel[k][a][0] for k in niveles if a in por_nivel[k]) for a in anios}
    tablas_usadas = sorted({por_nivel[k][a][1] for k in niveles for a in anios if a in por_nivel[k]})
    for k in niveles:
        for a in anios:
            if a in por_nivel[k]:
                ses.asegurar_celda(por_nivel[k][a][2])
                plan.usa(por_nivel[k][a][2])
    desglose = lambda a: ", ".join(f"{k.lower()} {fmt(por_nivel[k][a][0])} (tabla {por_nivel[k][a][1]})" for k in niveles if a in por_nivel[k])
    plan.paso(f"Sumó la matrícula de {etiqueta} por nivel ({', '.join(k.lower() for k in niveles)}) en las tablas {', '.join(tablas_usadas)}")
    a1 = anios[-1]
    if len(anios) == 1:
        plan.hechos.append(f"Matrícula de {etiqueta} en {a1}: {fmt(total[a1])} alumnos en total ({desglose(a1)}).")
    else:
        a0 = anios[0]
        d = total[a1] - total[a0]
        pct = f", {'+' if d >= 0 else '−'}{fmt(round(abs(d) / total[a0] * 100, 1))}%" if total[a0] else ""
        plan.hechos.append(f"Matrícula total de {etiqueta} ({' + '.join(k.lower() for k in niveles)}) por año: "
                           + "; ".join(f"{a}: {fmt(total[a])}" for a in anios)
                           + f". Cambio de {a0} a {a1}: {'+' if d >= 0 else '−'}{fmt(abs(d))} alumnos{pct}.")
        plan.hechos.append(f"Desglose de {a1}: {desglose(a1)}. Desglose de {a0}: {desglose(a0)}.")
        sid = "SM" + str(len([k for k in ses.ser if str(k).startswith("SM")]) + 1)
        ses.ser[sid] = {a: float(total[a]) for a in anios}
        ses.ind[sid] = {"id": sid, "ruta": f"Matrícula total de {etiqueta}", "concepto": f"Matrícula total de {etiqueta}",
                        "eje": "Serie calculada", "archivo": "calc"}
        if plan.grafica({"tipo": "barras", "ids": [sid], "desde": a0, "hasta": a1, "titulo": f"Matrícula total de {etiqueta}, {a0}–{a1}"}):
            plan.hechos.append("Se muestra una gráfica de barras con la matrícula total de cada año y abajo la tabla por nivel.")
        plan.tablas.append({"titulo": f"Matrícula de {etiqueta} por nivel, {a0}–{a1}", "encabezados": ["Año"] + niveles + ["Total"],
                            "filas": [{"nombre": str(a), "textos": [fmt(por_nivel[k][a][0]) if a in por_nivel[k] else "—" for k in niveles] + [fmt(total[a])]} for a in anios],
                            "fuente": "Fuente: Agenda Estadística, tablas " + ", ".join(tablas_usadas) + "."})
    plan.hechos.append("Fuente: tablas " + ", ".join(f"{t} «{ses.tab[t]['titulo']}»" for t in tablas_usadas)
                       + (f". La matrícula del espacio suma {' y '.join(k.lower() for k in niveles)}." if len(niveles) > 1 else "."))
    return True


def ficha_espacio(plan, esp, q):
    n, nombre, g = esp
    ses = plan.ses
    rk_f = ses._rank_tablas(plan.pregunta)
    tope_f = rk_f[0]["pts"] if rk_f else 0
    # solo tablas relacionadas con la pregunta (no cualquier tabla que tenga a ese espacio)
    orden = primero_p03(ses, q, [x["id"] for x in rk_f if x["pts"] >= 0.35 * tope_f] if rk_f else sorted(ses.tab))
    nota_falta = None
    # solo cuentan las tablas que traen renglones por espacio (las de un solo centro, como el CeAC, no sirven aquí)
    tiene_esp = lambda T: T.get("tipo") != "lista" and any(len(f["ruta"]) == 2 and GRUPO_RX.match(norm(f["ruta"][0])) for f in T["filas"])
    rk_e = [x for x in rk_f if tiene_esp(ses.tab[x["id"]]) and aciertos_titulo(ses.tab[x["id"]], q) >= 0]
    if rk_e and rk_e[0]["pts"] >= 12 and not filas_de(ses.tab[rk_e[0]["id"]], n, g) \
            and not (re.search(r"\bptc\b", q) and not PTC_ESPECIFICO.search(q)) \
            and not (PERSONAL.search(q) and not PROGRAMA.search(q)):  # en preguntas de personal mandan P02, P03 y P04
        faltan = [x for x in rk_e[:2] if x["pts"] >= 0.75 * rk_e[0]["pts"] and not filas_de(ses.tab[x["id"]], n, g)]
        desc = "; ".join(f"{x['id']} «{ses.tab[x['id']]['titulos'][anio_de(ses.tab[x['id']])]}»" for x in faltan)
        nota_falta = (f"{'Las tablas más relacionadas' if len(faltan) > 1 else 'La tabla más relacionada'} con la pregunta ({desc}) "
                      f"no incluye{'n' if len(faltan) > 1 else ''} a {nombre}: no tiene registro ahí.")
        # solo otras tablas claramente relacionadas con el tema (sin temas parciales no pedidos)
        orden = [x["id"] for x in rk_e if x["pts"] >= 0.7 * rk_e[0]["pts"]]
    if not PROGRAMA.search(q) and PERSONAL.search(q):
        # pregunta sobre personal sin programa específico: primero las tablas base de personal (P02, P03, P04)
        base = [tid for tid in sorted(ses.tab) if norm(ses.tab[tid]["titulo"]).startswith("personal")
                and "incorporad" not in norm(ses.tab[tid]["titulo"]) and len(ses.tab[tid]["filas"]) > 20]
        def prioridad(tid):
            tit = norm(ses.tab[tid]["titulo"])
            if re.search(r"profesor|docente|academic|ptc|tiempo completo|asignatura", q) and tit == "personal academico":
                return 0
            if re.search(r"administrativ|sindicaliz|confianza", q) and tit == "personal administrativo":
                return 0
            return 1
        orden = sorted(base, key=lambda t: (prioridad(t), not t.startswith("P"), t)) + orden  # primero las de Personal (P…)
    alumnado = bool(ALUMNADO.search(q)) and not PERSONAL.search(q)
    vistas, cambio_principal = [], None
    for tid in dict.fromkeys(orden):
        T = ses.tab[tid]
        if T.get("tipo") == "lista" or (alumnado and tid.startswith("P")) or aciertos_titulo(T, q) < 0:
            continue  # listas, personal en preguntas de alumnos y temas parciales no pedidos
        filas = filas_de(T, n, g)
        if not filas:
            continue
        f = filas[0]
        a = anio_de(T)
        cols = columnas_total(T)
        partes = []
        for c in cols:
            v = valor(T, a, f, c)
            if v is None:
                continue
            cid = f"{tid}.f{f}.c{c}"
            ses.asegurar_celda(cid)
            plan.usa(cid)
            partes.append(f"{' › '.join(T['columnas'][c])} = {fmt(v)}")
        if not partes:
            continue
        hecho = f"Tabla {tid} «{T['titulos'][a]}», {nombre}: " + "; ".join(partes) + "."
        fg = fila_grupo(T, g)
        c_ult = next((j for j in cols if T["columnas"][j] == ["Total"]), None)
        if c_ult is None:
            c_ult = next((j for j in reversed(cols) if T["columnas"][j][-1] == "Total"), None)
        if fg is not None and c_ult is not None and c_ult not in T.get("no_sumables", []):
            v, vg = valor(T, a, f, c_ult), valor(T, a, fg, c_ult)
            if v is not None and vg:
                gid = f"{tid}.f{fg}.c{c_ult}"
                ses.asegurar_celda(gid)
                plan.usa(gid)
                hecho += (f" Representa el {fmt(round(v / vg * 100, 1))}% del total de «{T['filas'][fg]['ruta'][0]}» "
                          f"en esa columna ({fmt(v)} de {fmt(vg)}).")
        if c_ult is not None and CAMBIO_ANIOS:
            hecho += texto_cambio(T, a, f, c_ult)
            a0 = anio_previo(T, a)
            v0, v1 = (valor(T, a0, f, c_ult) if a0 else None), valor(T, a, f, c_ult)
            if not vistas and v0 is not None and v1 is not None:
                d = v1 - v0
                pct = f", {'+' if d >= 0 else '−'}{fmt(round(abs(d) / v0 * 100, 1))}%" if v0 and c_ult not in T.get("no_sumables", []) else ""
                cambio_principal = (f"Respuesta: {' › '.join(T['columnas'][c_ult])} de {nombre} en la tabla {tid} «{T['titulo']}»: "
                                    f"{fmt(v0)} en {a0} y {fmt(v1)} en {a} (cambio {'+' if d >= 0 else '−'}{fmt(abs(d))}{pct}).")
                otros = [(y, valor(T, y, f, c_ult)) for y in sorted(T["datos"], key=int)]
                otros = [(y, v) for y, v in otros if v is not None]
                if len(otros) > 2:
                    cambio_principal += " Por año: " + "; ".join(f"{y}: {fmt(v)}" for y, v in otros) + "."
        if not vistas:  # desglose completo de la tabla principal
            det = [f"{' › '.join(T['columnas'][c])} = {fmt(valor(T, a, f, c))}" for c in range(len(T["columnas"]))
                   if c not in cols and valor(T, a, f, c) is not None]
            if det:
                hecho += " Desglose: " + "; ".join(det) + "."
        plan.hechos.append(hecho)
        plan.paso(f"Consultó la tabla {tid} «{T['titulos'][a]}» para {nombre}")
        vistas.append((tid, f))
        if len(vistas) >= 6:
            break
    if cambio_principal:
        plan.hechos.insert(0, cambio_principal)
    if nota_falta:
        plan.hechos.insert(0, nota_falta)
        plan.paso(nota_falta)
        if not vistas:
            return True
    if not vistas:
        return False
    if re.search(r"\bptc\b", q):  # dato directo de PTC (P03 trae hombres y mujeres por separado)
        for tid, f in vistas:
            T = ses.tab[tid]
            cols = [" › ".join(c) for c in T["columnas"]]
            base = "Profesoras / es › Tiempo completo"
            if base + " › Hombres" in cols and base + " › Mujeres" in cols:
                a = anio_de(T)
                ch, cm = cols.index(base + " › Hombres"), cols.index(base + " › Mujeres")
                ids = [f"{tid}.f{f}.c{ch}", f"{tid}.f{f}.c{cm}"]
                r = ses.ejecutar("calcular_serie", {"operacion": "suma", "ids": ids, "nombre": f"PTC de {nombre}"})
                if "id" in r and r["valores"].get(a) is not None:
                    plan.usa(*ids, r["id"])
                    plan.hechos.insert(0, f"Profesoras y profesores de tiempo completo (PTC) de {nombre} según la tabla {tid} «{T['titulos'][a]}»: "
                                          f"{fmt(r['valores'][a])} ({fmt(valor(T, a, f, ch))} hombres y {fmt(valor(T, a, f, cm))} mujeres).")
                    if PORCENTAJE.search(q) or re.search(r"respecto|del total|de todo|parte del|representa", q):
                        # el porcentaje de PTC se calcula con PTC (no con el personal académico total del espacio)
                        ptc = lambda i: (valor(T, a, i, ch) or 0) + (valor(T, a, i, cm) or 0) if i is not None else None
                        f_tot = next((i for i, x in enumerate(T["filas"]) if len(x["ruta"]) == 1 and norm(x["ruta"][0]) == "total"), None)
                        f_gru = fila_grupo(T, g)
                        v = r["valores"][a]
                        partes = []
                        if f_tot is not None and ptc(f_tot):
                            partes.append(f"el {fmt(round(v / ptc(f_tot) * 100, 1))}% de los {fmt(ptc(f_tot))} PTC de la UAEMEX")
                        if f_gru is not None and ptc(f_gru) and f_gru != f_tot:
                            gtxt = T["filas"][f_gru]["ruta"][0].strip()
                            partes.append(f"el {fmt(round(v / ptc(f_gru) * 100, 1))}% de los {fmt(ptc(f_gru))} PTC del grupo «{gtxt}»")
                        if partes:
                            # las otras líneas traen porcentajes de otras columnas (personal académico total): se quitan para no confundir
                            plan.hechos[1:] = [re.sub(r" Representa el [^.]*\.(\d[^.]*\.)?", "", h) for h in plan.hechos[1:]]
                            plan.hechos.insert(0, f"Los {fmt(v)} PTC de {nombre} representan " + " y ".join(partes)
                                                  + f" en {a} (tabla {tid}, columnas «{base} › Hombres» y «› Mujeres»).")
                            if "Profesoras / es › Total" in cols and valor(T, a, f, cols.index("Profesoras / es › Total")):
                                pt = valor(T, a, f, cols.index("Profesoras / es › Total"))
                                plan.hechos.insert(1, f"Dentro de {nombre}, {fmt(v)} de sus {fmt(pt)} profesoras y profesores ({fmt(round(v / pt * 100, 1))}%) son de tiempo completo.")
                break
    if (POR_PROGRAMA.search(q) or (RANK_PROG.search(q) and EXTREMO.search(q))) and desglose_programas(plan, vistas, nombre, q):
        return True
    # gráfica: desglose del espacio en la tabla más relacionada
    tid, f = vistas[0]
    T = ses.tab[tid]
    a = anio_de(T)
    cols = [j for j, c in enumerate(T["columnas"]) if "Total" not in c and j not in T.get("no_sumables", [])][:12]
    if len(cols) < 2:
        cols = columnas_total(T)
    ids = [f"{tid}.f{f}.c{c}" for c in cols if valor(T, a, f, c) is not None]
    ids = [i for i in ids if ses.asegurar_celda(i) or i in ses.ser]
    if ids:
        unidad_base = max({ses.unidad(i) for i in ids}, key=lambda u: sum(1 for i in ids if ses.unidad(i) == u))
        ids = [i for i in ids if ses.unidad(i) == unidad_base]
    if len(ids) >= 2 and plan.grafica({"tipo": "comparar_anio", "ids": ids, "titulo": f"{nombre}: {T['titulo']} {a}"}):
        plan.hechos.append(f"Se muestra una gráfica con el desglose de {nombre} de la tabla {tid}.")
    return True


def aciertos_titulo(T, q):
    """Cuántas palabras de la pregunta (con equivalencias) aparecen en el título; resta las tablas de un tema parcial no pedido."""
    from calculos import EQUIV_T, SIN_T, SUBCONJ_T, VACIAS_T
    tit = norm(T.get("titulo", ""))
    ws = set()
    for w in q.split():
        if len(w) < 4 or w in VACIAS_T or w in ("menos", "mayor", "menor", "cual", "cuales", "tiene", "tienen", "espacio", "espacios"):
            continue
        w = SIN_T.get(w, w)
        w = w if " " in w else w[:7]
        ws.add(w)
        for v in EQUIV_T.get(w, []):
            ws.add(v)
    n = sum(1 for w in ws if w in tit)
    n -= 3 * sum(1 for t in SUBCONJ_T if t in tit and t not in q)
    return n


def comparar_espacios(plan, grupos, espacios_sel, q):
    ses = plan.ses
    pct_sexo = bool(PORCENTAJE.search(q)) and bool(re.search(r"\bmujer|\bhombre", q))
    rk = ses._rank_tablas(plan.pregunta)
    tope = rk[0]["pts"] if rk else 0
    # solo tablas cercanas a la mejor: si ninguna tiene el grupo pedido, mejor no inventar
    ranking = [x["id"] for x in rk if x["pts"] >= 0.4 * tope] if tope > 1 else sorted(ses.tab)
    ranking = primero_p03(ses, q, ranking)
    ranking = sorted(ranking, key=lambda t: -aciertos_titulo(ses.tab[t], q))  # primero las que coinciden en el título (orden estable)
    for tid in dict.fromkeys(ranking):
        T = ses.tab[tid]
        if T.get("tipo") == "lista":
            continue
        a = anio_de(T)
        if espacios_sel:
            filas = [i for e in espacios_sel for i in filas_de(T, e[0], e[2])]
            g_norm = None
        else:
            if grupos == ["*"]:  # «por espacio académico»: todos los espacios académicos (sin dependencias)
                g_norm = "*"
                filas = [i for i, f in enumerate(T["filas"]) if len(f["ruta"]) == 2 and GRUPO_RX.match(norm(f["ruta"][0]))
                         and not norm(f["ruta"][0]).startswith("dependencia")]
            else:
                g_norm = next((norm(f["ruta"][0]) for f in T["filas"] if len(f["ruta"]) == 1
                               and any(tok in norm(f["ruta"][0]) for tok in grupos)), None)
                if not g_norm:
                    continue
                filas = [i for i, f in enumerate(T["filas"]) if len(f["ruta"]) == 2 and norm(f["ruta"][0]) == g_norm]
        if len(filas) < 2 and not (espacios_sel and filas):
            continue
        c = elegir_columna(T, q)
        col = " › ".join(T["columnas"][c])
        datos = [(i, valor(T, a, i, c)) for i in filas]
        datos = [(i, v) for i, v in datos if v is not None]
        if not datos:
            continue
        etiqueta = lambda i: T["filas"][i]["ruta"][1].strip() + (f" ({T['filas'][i]['ruta'][0].strip()})" if (espacios_sel or g_norm == "*") and len({T['filas'][j]['ruta'][0] for j, _ in datos}) > 1 else "")
        plan.paso(f"Consultó la tabla {tid} «{T['titulos'][a]}», columna «{col}», {len(datos)} espacios")
        if pct_sexo:
            cm = c
            pref = T["columnas"][cm][:-1]
            ct = next((j for j, x in enumerate(T["columnas"]) if x == pref + ["Total"] or (pref == ["Total"] and x == ["Total"])), None)
            otro = {"Hombres": "Mujeres", "Mujeres": "Hombres"}.get(T["columnas"][cm][-1])
            co = next((j for j, x in enumerate(T["columnas"]) if otro and x == pref + [otro]), None)
            if T["columnas"][cm][-1] not in ("Hombres", "Mujeres") or (ct is None and co is None):
                pct_sexo = False
            else:
                ids, filas_pct = [], []
                for i, _ in datos:
                    num = f"{tid}.f{i}.c{cm}"
                    if ct is not None:
                        den = f"{tid}.f{i}.c{ct}"
                        if not valor(T, a, i, ct):
                            continue
                    else:  # la tabla no trae total: hombres + mujeres
                        if not ((valor(T, a, i, cm) or 0) + (valor(T, a, i, co) or 0)):
                            continue
                        rs = ses.ejecutar("calcular_serie", {"operacion": "suma", "ids": [num, f"{tid}.f{i}.c{co}"],
                                                             "nombre": f"{etiqueta(i)}: {' › '.join(pref)} (hombres + mujeres)"})
                        if "id" not in rs:
                            continue
                        den = rs["id"]
                        plan.usa(f"{tid}.f{i}.c{co}")
                    r = ses.ejecutar("calcular_serie", {"operacion": "proporcion", "id": num, "id2": den,
                                                        "nombre": f"{etiqueta(i)}: % {T['columnas'][cm][-1].lower()}"})
                    if "id" in r:
                        ids.append(r["id"])
                        plan.usa(num, den, r["id"])
                        filas_pct.append((etiqueta(i), r["valores"][a]))
                filas_pct.sort(key=lambda x: -x[1])
                plan.paso(f"Calculó el porcentaje de {T['columnas'][cm][-1].lower()} en {len(filas_pct)} espacios")
                plan.hechos.append(f"Tabla {tid} «{T['titulos'][a]}». Porcentaje de {T['columnas'][cm][-1].lower()} en «{' › '.join(pref)}», "
                                   f"de mayor a menor: " + "; ".join(f"{n} {fmt(v)}%" for n, v in filas_pct) + ".")
                if ids and plan.grafica({"tipo": "comparar_anio", "ids": ids[:30],
                                         "titulo": f"% de {T['columnas'][cm][-1].lower()} · {' › '.join(pref)} · {a}"}):
                    plan.hechos.append("Se muestra una gráfica con el porcentaje de cada espacio.")
                return True
        ult = T["columnas"][c][-1]
        if ult in ("Hombres", "Mujeres") and not re.search(r"\bmujer|\bhombre", q):
            pref = T["columnas"][c][:-1]
            ch = next((j for j, x in enumerate(T["columnas"]) if x == pref + ["Hombres"]), None)
            cm = next((j for j, x in enumerate(T["columnas"]) if x == pref + ["Mujeres"]), None)
            ct = next((j for j, x in enumerate(T["columnas"]) if x == pref + ["Total"]), None)
            if ct is not None:
                c, col = ct, " › ".join(T["columnas"][ct])
                datos = [(i, valor(T, a, i, c)) for i, _ in datos if valor(T, a, i, c) is not None]
            elif ch is not None and cm is not None:
                ids, filas_s = [], []
                for i, _ in datos:
                    r = ses.ejecutar("calcular_serie", {"operacion": "suma", "ids": [f"{tid}.f{i}.c{ch}", f"{tid}.f{i}.c{cm}"],
                                                        "nombre": f"{etiqueta(i)}: {' › '.join(pref)}"})
                    if "id" in r:
                        ids.append(r["id"])
                        plan.usa(f"{tid}.f{i}.c{ch}", f"{tid}.f{i}.c{cm}", r["id"])
                        filas_s.append((etiqueta(i), r["valores"][a]))
                filas_s.sort(key=lambda x: -x[1])
                plan.paso(f"Sumó hombres y mujeres de «{' › '.join(pref)}» en {len(filas_s)} espacios (la tabla no trae el total)")
                hecho = (f"Tabla {tid} «{T['titulos'][a]}», «{' › '.join(pref)}» (hombres + mujeres). Valores de mayor a menor: "
                         + "; ".join(f"{n} {fmt(v)}" for n, v in filas_s[:30]) + ".")
                if len(filas_s) > 1:
                    hecho += f" El mayor es {filas_s[0][0]} ({fmt(filas_s[0][1])}) y el menor es {filas_s[-1][0]} ({fmt(filas_s[-1][1])})."
                plan.hechos.append(hecho)
                if ids and plan.grafica({"tipo": "comparar_anio", "ids": ids[:30], "titulo": f"{' › '.join(pref)} · {T['titulo']} {a}"}):
                    plan.hechos.append("Se muestra una gráfica que compara los espacios.")
                return True
        menor = bool(re.search(r"\bmenos\b|\bmenor|\bminim|\bmas baj", q))
        orden = sorted(datos, key=lambda x: x[1] if menor else -x[1])
        ids = [f"{tid}.f{i}.c{c}" for i, _ in datos]
        for x in ids:
            ses.asegurar_celda(x)
        plan.usa(*ids)
        u = "%" if re.search(r"%|porcentaje", norm(col)) else ""
        hecho = (f"Tabla {tid} «{T['titulos'][a]}», columna «{col}». Valores de {'menor a mayor' if menor else 'mayor a menor'}: "
                 + "; ".join(f"{etiqueta(i)} {fmt(v)}{u}" for i, v in orden[:30]) + ".")
        if len(orden) > 1:
            alto, bajo = (orden[-1], orden[0]) if menor else (orden[0], orden[-1])
            empate = [etiqueta(i) for i, v in orden if v == bajo[1]] if menor else []
            hecho += f" El mayor es {etiqueta(alto[0])} ({fmt(alto[1])}{u}) y el menor es {etiqueta(bajo[0])} ({fmt(bajo[1])}{u})."
            if len(empate) > 1:
                hecho += f" Empatan con el valor más bajo ({fmt(bajo[1])}{u}): {', '.join(empate[:10])}."
        if u and sum(1 for _, v in orden if v == 100) >= 2:
            cien = [etiqueta(i) for i, v in orden if v == 100]
            hecho += f" {len(cien)} espacios tienen 100% ({', '.join(cien[:12])}{'…' if len(cien) > 12 else ''})."
        if g_norm and g_norm != "*":
            fg = fila_grupo(T, g_norm)
            vg = valor(T, a, fg, c) if fg is not None else None
            if vg and c not in T.get("no_sumables", []):
                gid = f"{tid}.f{fg}.c{c}"
                ses.asegurar_celda(gid)
                plan.usa(gid)
                hecho += f" Total del grupo «{T['filas'][fg]['ruta'][0].strip()}»: {fmt(vg)}."
        if CAMBIO_ANIOS and anio_previo(T, a):
            a0 = anio_previo(T, a)
            cambios = [(i, v, valor(T, a0, i, c)) for i, v in orden]
            cambios = [(i, v, v0, v - v0) for i, v, v0 in cambios if v0 is not None]
            if cambios:
                cambios.sort(key=lambda x: -x[3])
                hecho += (f" Cambio de {a0} a {a} (del que más subió al que más bajó): "
                          + "; ".join(f"{etiqueta(i)} {fmt(v0)} → {fmt(v)} ({'+' if dd >= 0 else '−'}{fmt(abs(dd))})" for i, v, v0, dd in cambios[:30]) + ".")
        plan.hechos.append(hecho)
        if plan.grafica({"tipo": "comparar_anio", "ids": ids[:30], "titulo": f"{col} · {T['titulo']} {a}"}):
            plan.hechos.append("Se muestra una gráfica que compara los espacios.")
        return True
    return False


def serie(plan, q):
    ses = plan.ses
    limpia = re.sub(r"\b(grafic\w*|grafiq\w*|haz|hazme|dame|muestra\w*|una|un|barras|lineas?|cual|cuales|fue|es|son|como|me|puedes|podrias)\b", " ", q)
    pq, res = ses.buscador.buscar(limpia, 3)
    if not res or res[0]["pts"] < 5:
        return False
    sid = res[0]["id"]
    # una palabra de la pregunta que nombra una tabla de 2025 y no aparece en el indicador (p. ej. «cobertura»): mejor la tabla
    from calculos import VACIAS_T
    ruta_s = norm(ses.nombre(sid))
    rk = ses._rank_tablas(plan.pregunta)
    if rk and not pq["desde"] and not pq["unico"]:
        tit = norm(ses.tab[rk[0]["id"]]["titulo"])
        if any(len(w) >= 5 and w not in VACIAS_T and w[:6] in tit and w[:6] not in ruta_s for w in q.split()):
            return False
    if not pq["unico"] and not pq["desde"] and (max(int(a) for a in ses.ser[sid]) < 2024 or not ses.ser[sid][max(ses.ser[sid], key=int)]):
        return False  # serie que dejó de reportarse (o último dato en 0): mejor las tablas de 2025
    nombre = ses.nombre(sid)
    anios = sorted(ses.ser[sid])
    d = max(anios[0], pq["desde"]) if pq["desde"] else None
    h = min(anios[-1], pq["hasta"]) if pq["hasta"] else None
    plan.usa(sid)
    plan.paso(f"Eligió el indicador «{nombre}»")
    if ses.unidad(sid):
        plan.hechos.append(f"Unidad del indicador «{nombre}»: {ses.unidad(sid)}.")
    def calc(args):
        r = ses.ejecutar("calcular", args)
        if "error" in r:
            plan.paso(r["error"], True)
            return None
        plan.paso(r["descripcion"])
        plan.hechos.append(r["descripcion"] + ".")
        return r
    if pq["unico"]:
        if calc({"operacion": "valor", "id": sid, "anio": pq["unico"]}) and pq["unico"] - 1 in ses.ser[sid]:
            calc({"operacion": "cambio", "id": sid, "desde": pq["unico"] - 1, "hasta": pq["unico"]})
    else:
        calc({"operacion": "valor", "id": sid, "anio": h or anios[-1]})
        dd, hh = d or anios[0], h or anios[-1]
        if dd < hh:
            calc({"operacion": "cambio", "id": sid, "desde": dd, "hasta": hh})
            if CRECIMIENTO.search(q):
                calc({"operacion": "crecimiento_anual_promedio", "id": sid, "desde": dd, "hasta": hh})
                calc({"operacion": "maximo", "id": sid, "desde": dd, "hasta": hh})
    if not plan.hechos:
        return False
    if GRAFICA.search(q) or CRECIMIENTO.search(q) or d or h:
        if plan.grafica({"tipo": "linea", "ids": [sid], "desde": d or anios[0], "hasta": h or anios[-1], "titulo": nombre}):
            plan.hechos.append("Se muestra una gráfica con la evolución del indicador.")
    alternativas = [ses.nombre(x["id"]) for x in res[1:3]]
    if alternativas:
        plan.hechos.append("Indicadores parecidos que también existen: " + "; ".join(alternativas) + ".")
    return True


NIVELES_ESP = re.compile(r"(licenciatura|bachillerato|posgrado|estudios (profesionales|avanzados)|maestria|doctorado|especialidad|tecnico superior)")
POR_SEDE = re.compile(r"por (espacio|sede|facultad|plantel|centro|unidad|escuela|dependencia)|en (cada|un|una) (espacio|sede|facultad|centro|unidad)|en un solo|en una sola|por separado")
RANK_PROG = re.compile(r"(programa|carrera|licenciatura|maestria|doctorado|especialidad)")
EXTREMO = re.compile(r"\bmejor|\bpeor|\bmas alt|\bmas baj|\bencabez|\blider|\bmayor|\bmenor|\bmas\b|\bmenos\b|\btop\b|ranking|\bprimer|\bcuales? (son )?los?\b.*\b(mas|mayor)|\bmax|\bmin")


def ranking_programas(plan, q):
    """¿Qué programa tiene más/menos …? Ordena todos los programas de la tabla más relacionada."""
    ses = plan.ses
    rk = ses._rank_tablas(plan.pregunta)
    tope = rk[0]["pts"] if rk else 0
    for x in rk:
        if x["pts"] < 0.5 * tope:
            break
        tid = x["id"]
        T = ses.tab[tid]
        if T.get("tipo") == "lista":
            continue
        F = T["filas"]
        rutas = [f["ruta"] for f in F]
        hojas = [i for i, f in enumerate(F) if len(f["ruta"]) >= 3
                 and not any(len(r) > len(f["ruta"]) and r[:len(f["ruta"])] == f["ruta"] for r in rutas)]
        if len(hojas) < 15:
            continue
        a = anio_de(T)
        c = elegir_columna(T, q)
        col = " › ".join(T["columnas"][c])
        datos = [(i, valor(T, a, i, c)) for i in hojas]
        datos = [(i, v) for i, v in datos if v is not None]
        if len(datos) < 15:
            continue
        es_prog = sum(1 for i, _ in datos if re.match(r"(licenciatura|maestria|doctorado|especialidad|tecnico|ingenier)", norm(F[i]["ruta"][-1])))
        if es_prog < 0.6 * len(datos):
            continue  # las hojas no son programas educativos (p. ej. modalidades de bachillerato)
        menor = bool(re.search(r"\bmenor|\bmenos\b|\bmin|\bmas baj", q))
        if re.search(r"\bmejor|\bpeor", q):  # «mejor» depende del indicador: en reprobación o abandono, mejor es más bajo
            al_reves = bool(re.search(r"reprobac|abandono|desercion|riesgo", norm(col)))
            menor = bool(re.search(r"\bpeor", q)) != al_reves
        indice = c in T.get("no_sumables", []) or bool(re.search(r"indice|eficiencia|porcentaje|%|tasa|promedio", norm(col)))
        datos.sort(key=lambda d: d[1], reverse=not menor)
        sede = lambda i: F[i]["ruta"][1].strip()
        prog = lambda i: re.sub(r"\s*\(\d+\)$", "", F[i]["ruta"][-1].strip())
        plan.paso(f"Ordenó los {len(datos)} programas de la tabla {tid} «{T['titulos'][a]}», columna «{col}»")
        por_sede = bool(POR_SEDE.search(q))
        top = datos[:15]
        for i, _ in top:
            plan.usa(f"{tid}.f{i}.c{c}")
        orden = "de menor a mayor" if menor else "de mayor a menor"
        h_sede = (f"Tabla {tid} «{T['titulos'][a]}», columna «{col}». Cada programa contado por separado en cada espacio académico (sin sumar sedes), {orden}: "
                           + "; ".join(f"{prog(i)} en {sede(i)} {fmt(v)}" for i, v in top) + ".")
        plan.hechos.append(h_sede)
        if indice and any(v > 100 for _, v in datos) and "eficiencia" in norm(col):
            plan.hechos.append("Nota: la eficiencia terminal global puede pasar de 100% porque divide a todas las personas egresadas del año "
                               "(incluidas las de generaciones anteriores) entre el nuevo ingreso de una sola generación; la de cohorte es la más comparable.")
        if indice:  # un índice o porcentaje no se suma entre sedes
            plan.hechos.append("Esta columna es un índice o porcentaje: cada programa se compara en su sede y no se suma entre sedes.")
            if plan.grafica({"tipo": "comparar_anio", "ids": [f"{tid}.f{i}.c{c}" for i, _ in top],
                             "titulo": f"Programas con {'menor' if menor else 'mayor'} {col.lower()} · {T['titulo']} {a}"}):
                plan.hechos.append("Se muestra una gráfica de barras con los programas.")
            return True
        # el mismo programa impartido en varias sedes, sumado
        grupos = {}
        for i, v in datos:
            grupos.setdefault(norm(prog(i)), []).append(i)
        sumas, ids_g = [], []
        for k, idx in grupos.items():
            ids = [f"{tid}.f{i}.c{c}" for i in idx]
            nombre = prog(idx[0])
            if len(ids) == 1:
                ses.asegurar_celda(ids[0])
                sumas.append((nombre, valor(T, a, idx[0], c), 1, ids[0]))
                continue
            r = ses.ejecutar("calcular_serie", {"operacion": "suma", "ids": ids, "nombre": f"{nombre} (todas las sedes)"})
            if "id" in r and r["valores"].get(a) is not None:
                plan.usa(*ids)
                sumas.append((nombre, r["valores"][a], len(ids), r["id"]))
        sumas.sort(key=lambda d: d[1], reverse=not menor)
        if any(n > 1 for _, _, n, _ in sumas):
            for _, _, _, i in sumas[:15]:
                plan.usa(i)
            plan.paso(f"Sumó cada programa entre las sedes donde se imparte ({len(sumas)} programas distintos)")
            h_suma = ("Mismo programa sumado en todas las sedes donde se imparte, " + orden + ": "
                      + "; ".join(f"{n} {fmt(v)} ({k} sede{'s' if k > 1 else ''})" for n, v, k, _ in sumas[:12]) + ".")
            if por_sede:  # se preguntó por espacio académico: primero el conteo por sede, la suma solo como contexto
                plan.hechos.append("Contexto adicional (no es lo que se preguntó): " + h_suma)
            else:
                plan.hechos.insert(len(plan.hechos) - 1, h_suma)
        if por_sede or not any(n > 1 for _, _, n, _ in sumas):
            ids_graf, tit = [f"{tid}.f{i}.c{c}" for i, _ in top], f"Programas con {'menor' if menor else 'mayor'} {col.lower()} por espacio académico · {T['titulo']} {a}"
        else:
            ids_graf, tit = [i for _, _, _, i in sumas[:15]], f"Programas con {'menor' if menor else 'mayor'} {col.lower()} (todas las sedes) · {T['titulo']} {a}"
        if plan.grafica({"tipo": "comparar_anio", "ids": ids_graf, "titulo": tit}):
            plan.hechos.append("Se muestra una gráfica de barras con los programas.")
        return True
    return False


RELACION = re.compile(r"relacion|proporcion|\bpor cada\b|\bcontra\b|\bentre\b|\bpor (ptc|profesor|docente)|alumnos? por|estudiantes? por|ratio|razon|porcentaje|cuantos de sus|que parte")
DOCENTE = re.compile(r"\bptc\b|tiempo completo|profesor|docente|maestr[oa]s?\b|personal academico")
ALUMNOS_Q = re.compile(r"matricul|alumn|estudiant")
TABLAS_MATRICULA = [("A26", "licenciatura"), ("A40", "posgrado"), ("A15", "bachillerato")]  # A40: posgrado por espacio (trae 2022–2025; A39 por programa no trae 2022)

# conceptos que se pueden cruzar por espacio: de qué tablas y columnas salen (se suman si son varias)
CONCEPTOS = {
    "snii": dict(rx=r"\bsnii?\b|sistema nacional", tablas=[("C04", ["Total"])], uno="PTC en el SNII", varios="PTC en el SNII"),
    "prodep": dict(rx=r"prodep|perfil", tablas=[("C02", ["Total"])], uno="PTC con perfil Prodep", varios="PTC con perfil Prodep"),
    "doctorado": dict(rx=r"doctorado|con doctor", tablas=[("C01", ["Doctorado › Total"])], uno="PTC con doctorado", varios="PTC con doctorado"),
    "investigador": dict(rx=r"investigador", tablas=[("C03", ["Total"])], uno="PTC investigador", varios="PTC investigadores"),
    "matricula": dict(rx=r"matricul|alumn|estudiant", tablas=[(t, ["Total"]) for t, _ in TABLAS_MATRICULA], uno="alumno", varios="alumnos"),
    "ptc": dict(rx=r"\bptc\b|tiempo completo", tablas=[("P03", ["Profesoras / es › Tiempo completo › Hombres", "Profesoras / es › Tiempo completo › Mujeres"])],
                uno="PTC", varios="PTC"),
    "profesor": dict(rx=r"profesor|docente|maestr", tablas=[("P03", ["Profesoras / es › Total"])], uno="profesor", varios="profesores"),
}


def conceptos_en(q):
    hall = [k for k, c in CONCEPTOS.items() if re.search(c["rx"], q)]
    if "snii" in hall and "investigador" in hall:
        hall.remove("investigador")  # «Sistema Nacional de Investigadores»
    if "ptc" in hall and "profesor" in hall:
        hall.remove("profesor")
    if "doctorado" in hall and "snii" in hall:
        hall.remove("doctorado")
    return hall


def valores_concepto(ses, k):
    """{(grupo, espacio): (lista de ids de celda, valor)} sumando las tablas y columnas del concepto."""
    clave = lambda r: (norm(r[0]).split()[0], norm(r[1]))
    out = {}
    for tid, cols in CONCEPTOS[k]["tablas"]:
        T = ses.tab.get(tid)
        if not T or T.get("tipo") == "lista":
            continue
        nombres = [" › ".join(c) for c in T["columnas"]]
        js = [nombres.index(c) for c in cols if c in nombres]
        if not js:
            continue
        a = anio_de(T)
        for i, f in enumerate(T["filas"]):
            r = f["ruta"]
            if len(r) != 2 or r[0].startswith("~"):
                continue
            vals = [valor(T, a, i, j) for j in js]
            if all(v is None for v in vals):
                continue
            ids, v0, _, _ = out.get(clave(r), ([], 0, None, None))
            g = re.sub(r"\s*\*+$", "", r[0].strip())
            out[clave(r)] = (ids + [f"{tid}.f{i}.c{j}" for j in js if valor(T, a, i, j) is not None],
                             v0 + sum(v or 0 for v in vals), f"{r[1].strip()} ({g})", norm(g))
    return out


TABLA_Q = re.compile(r"\btabla\b|\blista(do)?\b|\bcuadro\b|\bconcentrado\b|\bdesglose\b|\brelacion de\b")


def tabla_espacios(plan, q):
    """Tabla con una columna por concepto (PTC, SNII, Prodep, matrícula…) en cada espacio académico."""
    ses = plan.ses
    hall = conceptos_en(q)
    if not 1 <= len(hall) <= 4:
        return False
    hall.sort(key=lambda k: re.search(CONCEPTOS[k]["rx"], q).start())
    vals = {k: valores_concepto(ses, k) for k in hall}
    grupos_q = [tok for rx, tok in GRUPOS if re.search(rx, q)]
    claves = []
    for k in hall:
        for c, v in vals[k].items():
            if c not in claves:
                claves.append(c)
    base = vals.get("ptc") or vals.get("profesor") or vals[hall[0]]
    filas, columnas_ids = [], [[] for _ in hall]
    for c in claves:
        info = next((vals[k][c] for k in ("ptc", "profesor") if k in vals and c in vals[k]), None) or next(vals[k][c] for k in hall if c in vals[k])
        g_full = info[3]
        if grupos_q and not any(tok in g_full for tok in grupos_q):
            continue
        if not grupos_q and g_full.startswith("dependencia"):
            continue
        ids_fila = []
        for n, k in enumerate(hall):
            if c not in vals[k]:
                ids_fila.append(None)
                continue
            ids = vals[k][c][0]
            for x in ids:
                ses.asegurar_celda(x)
            if len(ids) == 1:
                ids_fila.append(ids[0])
            else:
                r = ses.ejecutar("calcular_serie", {"operacion": "suma", "ids": ids, "nombre": f"{info[2]}: {CONCEPTOS[k]['varios']}"})
                ids_fila.append(r.get("id"))
            plan.usa(*ids)
        if all(x is None for x in ids_fila):
            continue
        filas.append({"nombre": info[2], "ids": ids_fila})
    if len(filas) < 2:
        return False
    cap = lambda t: t[0].upper() + t[1:]
    encabezados = ["Espacio académico"] + [cap(CONCEPTOS[k]["varios"]) for k in hall]
    # columna de porcentaje cuando un concepto es parte de los PTC (o de los profesores)
    pct = None
    if len(hall) == 2 and hall[0] in ("ptc", "profesor") and hall[1] not in ("matricula", "ptc", "profesor"):
        pct = (1, 0)
    elif len(hall) == 2 and hall[1] in ("ptc", "profesor") and hall[0] not in ("matricula", "ptc", "profesor"):
        pct = (0, 1)
    razon = None
    if len(hall) == 2 and "matricula" in hall and any(k in hall for k in ("ptc", "profesor")):
        razon = (hall.index("matricula"), 1 - hall.index("matricula"))
    if pct or razon:
        op, (i_n, i_d) = ("proporcion", pct) if pct else ("razon", razon)
        encabezados.append(f"% de {CONCEPTOS[hall[i_d]]['varios']} que son {CONCEPTOS[hall[i_n]]['varios']}" if pct
                           else f"Alumnos por {CONCEPTOS[hall[i_d]]['uno']}")
        for f in filas:
            a_, b_ = f["ids"][i_n], f["ids"][i_d]
            ok = a_ and b_ and any(ses.ser.get(b_, {}).values())
            r = ses.ejecutar("calcular_serie", {"operacion": op, "id": a_, "id2": b_, "nombre": f"{f['nombre']}: {encabezados[-1]}"}) if ok else {}
            f["ids"].append(r.get("id") if r.get("valores") else None)
    # totales de la tabla
    totales = []
    for n in range(len(hall)):
        ids = [f["ids"][n] for f in filas if f["ids"][n]]
        r = ses.ejecutar("calcular_serie", {"operacion": "suma", "ids": ids, "nombre": f"Suma de la tabla: {CONCEPTOS[hall[n]]['varios']}"}) if len(ids) > 1 else {}
        totales.append(r.get("id"))
    if pct or razon:
        r = ses.ejecutar("calcular_serie", {"operacion": op, "id": totales[i_n], "id2": totales[i_d], "nombre": f"Suma de la tabla: {encabezados[-1]}"}) \
            if totales[i_n] and totales[i_d] else {}
        totales.append(r.get("id"))
    for f in filas:
        plan.usa(*[x for x in f["ids"] if x])
    plan.usa(*[x for x in totales if x])
    fuentes = sorted({t for k in hall for t, _ in CONCEPTOS[k]["tablas"]})
    titulo = " y ".join(CONCEPTOS[k]["varios"] for k in hall) + " por espacio académico"
    plan.tablas.append({"titulo": titulo[0].upper() + titulo[1:], "encabezados": encabezados, "filas": filas, "totales": totales,
                        "fuente": f"Fuente: Agenda Estadística 2025, tablas {', '.join(fuentes)}. PTC = profesoras y profesores de tiempo completo (P03, hombres + mujeres)."})
    plan.paso(f"Armó una tabla con {len(filas)} espacios y {len(encabezados) - 1} columnas (tablas {', '.join(fuentes)})")
    def v(i):
        return ses.ser.get(i, {}) if i else {}
    ult = lambda i: (lambda s_: s_[max(s_)] if s_ else None)(v(i))
    tot_txt = "; ".join(f"{encabezados[n + 1]} {fmt(round(ult(t), 2))}{'%' if pct and n == len(hall) else ''}" for n, t in enumerate(totales) if t and ult(t) is not None)
    plan.hechos.append(f"Se muestra abajo una tabla con {len(filas)} espacios académicos y las columnas: {', '.join(encabezados[1:])} "
                       f"(tablas {', '.join(fuentes)}). Suma de los espacios de la tabla: {tot_txt}.")
    if pct:
        orden = sorted([f for f in filas if f["ids"][-1] and ult(f["ids"][-1]) is not None and ult(f["ids"][-1]) <= 100
                        and "instituto" not in norm(f["nombre"])], key=lambda f: -ult(f["ids"][-1]))
        plan.hechos.append(f"Espacios académicos con mayor {encabezados[-1]} (sin institutos de investigación): "
                           + "; ".join(f"{f['nombre']} {fmt(round(ult(f['ids'][-1]), 2))}%" for f in orden[:5]) + ".")
        if any(f["ids"][-1] and (ult(f["ids"][-1]) or 0) > 100 for f in filas):
            plan.hechos.append("Algunos institutos pasan de 100% porque las dos tablas cuentan a las personas de forma distinta (adscripción o lugar de pago).")
    # grupos que no aparecen en alguna de las tablas
    for n, k in enumerate(hall):
        grupo_de = lambda f: re.sub(r".*\((.*)\)$", r"\1", f["nombre"])
        cuenta = {}
        for f in filas:
            tot_g, falt_g = cuenta.get(grupo_de(f), (0, 0))
            cuenta[grupo_de(f)] = (tot_g + 1, falt_g + (f["ids"][n] is None))
        partes = [(f"todos los espacios de «{g}»" if fa == tg else f"{fa} de {tg} espacios de «{g}»") for g, (tg, fa) in cuenta.items() if fa]
        if partes:
            plan.hechos.append(f"La tabla de {CONCEPTOS[k]['varios']} ({', '.join(t for t, _ in CONCEPTOS[k]['tablas'])}) no trae dato para "
                               + "; ".join(partes) + ". En esas filas la celda queda vacía.")
    plan.hechos.append("PTC significa profesoras y profesores de tiempo completo.")
    return True


def relacion_espacios(plan, q):
    """Cruza dos conceptos por espacio académico: proporción (SNII ÷ PTC, Prodep ÷ PTC…) o razón (alumnos ÷ PTC)."""
    ses = plan.ses
    hall = conceptos_en(q)
    if len(hall) != 2:
        return False
    if "matricula" in hall:  # alumnos por profesor: menos es mejor
        num, den, modo = "matricula", [h for h in hall if h != "matricula"][0], "razon"
    elif "ptc" in hall or "profesor" in hall:  # parte de los PTC: más es mejor
        den = "ptc" if "ptc" in hall else "profesor"
        num, modo = [h for h in hall if h != den][0], "proporcion"
    else:
        return False
    vn, vd = valores_concepto(ses, num), valores_concepto(ses, den)
    grupos_q = [tok for rx, tok in GRUPOS if re.search(rx, q)]
    filas, sin_den, excluidos = [], [], set()
    for k, (ids_n, v_n, _, g_full) in vn.items():
        if k not in vd:
            continue
        nombre = vd[k][2]  # el nombre como aparece en la tabla base (sin asteriscos de nota)
        if grupos_q and not any(tok in g_full or tok in vd[k][3] for tok in grupos_q):
            continue
        if not grupos_q and k[0] == "instituto":
            excluidos.add(nombre.split("(")[-1].rstrip(")"))
            continue
        if k[0] == "dependencia":
            continue
        ids_d, v_d = vd[k][0], vd[k][1]
        if not v_d:
            if v_n:
                sin_den.append(nombre)
            continue
        if modo == "razon" and not v_n:
            continue
        ser = []
        for ids, etq in ((ids_n, CONCEPTOS[num]["varios"]), (ids_d, CONCEPTOS[den]["varios"])):
            for x in ids:
                ses.asegurar_celda(x)
            if len(ids) == 1:
                ser.append(ids[0])
            else:
                r = ses.ejecutar("calcular_serie", {"operacion": "suma", "ids": ids, "nombre": f"{nombre}: {etq}"})
                if "id" not in r:
                    break
                ser.append(r["id"])
        if len(ser) != 2:
            continue
        nom_r = (f"{nombre}: {CONCEPTOS[num]['varios']} por {CONCEPTOS[den]['uno']}" if modo == "razon"
                 else f"{nombre}: % de {CONCEPTOS[den]['varios']} que son {CONCEPTOS[num]['varios']}")
        r = ses.ejecutar("calcular_serie", {"operacion": modo, "id": ser[0], "id2": ser[1], "nombre": nom_r})
        if "id" not in r or not r["valores"]:
            continue
        v = r["valores"][max(r["valores"])]
        filas.append((nombre, v, v_n, v_d, r["id"], ids_n + ids_d + ser))
    if len(filas) < 3:
        return False
    peor = bool(re.search(r"\bpeor|\bmenor|\bmas bajo", q))
    alto_mejor = modo == "proporcion"
    filas.sort(key=lambda x: x[1], reverse=(alto_mejor != peor))
    for x in filas[:15]:
        plan.usa(x[4], *x[5])
    en, ed = CONCEPTOS[num], CONCEPTOS[den]
    fuente_n = ", ".join(t for t, _ in en["tablas"])
    fuente_d = ", ".join(t for t, _ in ed["tablas"])
    plan.paso(f"Cruzó {en['varios']} (tabla {fuente_n}) con {ed['varios']} (tabla {fuente_d}) en {len(filas)} espacios")
    if modo == "razon":
        plan.paso(f"Calculó {en['varios']} por {ed['uno']} en cada espacio")
        defin = (f"{en['varios'].capitalize()} por {ed['uno']} en cada espacio académico = {en['varios']} (tablas {fuente_n}) ÷ {ed['varios']} (tabla {fuente_d}). "
                 "Un número menor indica una mejor relación.")
        fmt_f = lambda n, v, a_, b_: f"{n} {fmt(round(v, 2))} ({fmt(a_)} {en['varios']}, {fmt(b_)} {ed['varios'] if b_ != 1 else ed['uno']})"
    else:
        plan.paso(f"Calculó el porcentaje de {ed['varios']} que son {en['varios']} en cada espacio")
        defin = (f"Porcentaje de {ed['varios']} que son {en['varios']} en cada espacio académico = {en['varios']} (tabla {fuente_n}) ÷ "
                 f"{ed['varios']} (tabla {fuente_d}) × 100. Un porcentaje mayor indica una mejor relación.")
        fmt_f = lambda n, v, a_, b_: f"{n} {fmt(round(v, 2))}% ({fmt(a_)} de {fmt(b_)})"
    lado = "peor relación primero" if peor else "mejor relación primero"
    plan.hechos.append(defin + f" Ordenado con la {lado}: " + "; ".join(fmt_f(n, v, a_, b_) for n, v, a_, b_, _, _ in filas[:12]) + ".")
    plan.hechos.append(f"En el otro extremo ({'mejor' if peor else 'peor'} relación): "
                       + "; ".join(fmt_f(n, v, a_, b_) for n, v, a_, b_, _, _ in filas[-5:][::-1]) + ".")
    if modo == "proporcion" and any(v > 100 for _, v, _, _, _, _ in filas):
        plan.hechos.append("Algunos espacios pasan de 100% porque las dos tablas cuentan a las personas de forma distinta (por ejemplo, adscripción o lugar de pago).")
    if excluidos:
        plan.hechos.append("No se incluyen los institutos y centros de investigación (se pueden pedir aparte).")
    if sin_den:
        plan.hechos.append(f"Espacios sin {ed['varios']} registrados (no se pueden calcular): " + "; ".join(sin_den[:8]) + ".")
    if modo == "razon":
        plan.hechos.append("Los espacios con muy pocos alumnos (por ejemplo, solo posgrado) tienden a salir con relaciones muy bajas.")
    titulo = (f"{en['varios'].capitalize()} por {ed['uno']}" if modo == "razon" else f"% de {ed['varios']} que son {en['varios']}")
    if plan.grafica({"tipo": "comparar_anio", "ids": [x[4] for x in filas[:20]], "titulo": f"{titulo} · {'peor' if peor else 'mejor'} relación"}):
        plan.hechos.append("Se muestra una gráfica de barras con los espacios.")
    return True


GRUPO_RX = re.compile(r"^(escuela|facultad|plantel|centro|unidad|instituto|dependencia)")
_VISTAS = {}


def vista_bloques(tab):
    """Tablas con bloques (p. ej. «PTC» y «No PTC», cada uno con sus facultades): el planificador ve solo el primer
    bloque como una tabla normal de grupo › espacio. Los índices de fila no cambian, así que los ids de celda siguen valiendo."""
    if id(tab) in _VISTAS:
        return _VISTAS[id(tab)]
    out = {}
    for tid, T in tab.items():
        F = T.get("filas") or []
        bloques = {}
        for f in F:
            r = f["ruta"]
            if len(r) >= 3 and GRUPO_RX.match(norm(r[1])) and not GRUPO_RX.match(norm(r[0])):  # un grupo (Instituto…) no es bloque
                bloques.setdefault(r[0], set()).add(norm(r[1]))
        if T.get("tipo") != "lista" and bloques:
            todos = [g for gs in bloques.values() for g in gs]
            juntar = len(todos) == len(set(todos))  # cada bloque con grupos distintos (niveles educativos): se juntan
            primero = next(iter(bloques))
            nf = []
            for f in F:
                r = f["ruta"]
                if r[0] in bloques and len(r) > 1 and (juntar or r[0] == primero):
                    nf.append({**f, "ruta": r[1:]})
                elif len(r) == 1 and r[0] in bloques:
                    nf.append({**f, "ruta": ["~" + r[0]]})
                else:
                    nf.append({**f, "ruta": ["~"] * 4 + r if r[0] in bloques else r})  # otros bloques: fuera de las rutas por espacio
            sufijo = "" if juntar else f" ({primero})"
            out[tid] = {**T, "filas": nf, "titulo": f"{T['titulo']}{sufijo}",
                        "titulos": {a: f"{t}{sufijo}" for a, t in T.get("titulos", {}).items()}}
        else:
            out[tid] = T
    _VISTAS[id(tab)] = out
    return out


PTC_RX = re.compile(r"\b(profesor(a|es|as)?|profesoras? / es|docentes?|maestr[oa]s?|personal academico|academicos?)\s+(de\s+)?tiempo\s+completo\b")
PTC_ESPECIFICO = re.compile(r"\bsep\b|prodep|perfil|\bsnii?\b|sistema nacional|doctorado|maestria|especialidad|grado|investigador|licencia|registrad")


def canon_ptc(texto):
    """«profesores de tiempo completo», «personal académico de tiempo completo»… → «PTC»."""
    return PTC_RX.sub("PTC", norm(texto))


def primero_p03(ses, q, ids):
    """En preguntas sobre PTC sin un rasgo específico (SEP, Prodep, SNII, grado…), la tabla base es P03."""
    if re.search(r"\bptc\b", q) and not PTC_ESPECIFICO.search(q) and "P03" in ses.tab:
        return ["P03"] + [i for i in ids if i != "P03"]
    return ids


SNP_Q = re.compile(r"\bsnp\b|sistema nacional de posgrado|reconocid|conahcyt|secihti|pnpc|padron")
_VAC_PROG = set("de la el en los las del y e para con a al por su sus un una".split())
_NIV_PROG = {"especialidad": "especialidad", "especializacion": "especialidad", "maestria": "maestria", "doctorado": "doctorado"}
_NIV_TXT = {"especialidad": "Especialidad", "maestria": "Maestría", "doctorado": "Doctorado"}


def _toks_prog(s):
    s = re.sub(r"\(.*?\)", " ", norm(s))
    s = re.sub(r"^(especialidad|especializacion|maestria|doctorado|licenciatura)\s+((en|de)\s+)?", "", s)
    return {w for w in re.split(r"[^a-z0-9]+", s) if w and w not in _VAC_PROG}


def _nivel_prog(s):
    m = re.match(r"(especialidad|especializacion|maestria|doctorado)", norm(s))
    return _NIV_PROG.get(m.group(1)) if m else None


def emparejar_programas(lista_rows, T):
    """Empareja programas de una lista (nivel, nombre) con los renglones de programa de una tabla de matrícula.
    Devuelve [(nivel, nombre, [índices de fila], aproximado)]."""
    hojas = [(i, f["ruta"]) for i, f in enumerate(T["filas"]) if _nivel_prog(f["ruta"][-1])]
    out = []
    for nv, nom in lista_rows:
        tq = _toks_prog(nom)
        cands = []
        for i, r in hojas:
            if _nivel_prog(r[-1]) != nv:
                continue
            tr = _toks_prog(r[-1])
            if not tq or not tr:
                continue
            inter = len(tq & tr)
            sc = max(inter / len(tq | tr), 0.95 * inter / min(len(tq), len(tr)) if min(len(tq), len(tr)) >= 2 else 0)
            cands.append((sc, i, r))
        cands.sort(key=lambda x: -x[0])
        aprox = False
        sel = [c for c in cands if c[0] >= 0.75]
        if not sel:  # respaldo: el nombre de la tabla de matrícula está completo dentro del de la lista
            sub = [c for c in cands if _toks_prog(c[2][-1]) <= tq]
            nombres = {norm(c[2][-1]) for c in sub}
            if len(nombres) == 1:
                sel, aprox = sub, True
        if sel:
            mejor = sel[0][0]
            nombre_ok = norm(sel[0][2][-1])
            idx = [c[1] for c in sel if (aprox or c[0] >= mejor - 0.05) and norm(c[2][-1]) == nombre_ok]
            out.append((nv, nom, idx, aprox))
        else:
            out.append((nv, nom, [], False))
    return out


def matricula_lista_programas(plan, q):
    """«¿Cuántos alumnos tiene cada programa del SNP?»: cruza la lista A08 con la matrícula por programa de A39."""
    ses = plan.ses
    if "A08" not in ses.tab or "A39" not in ses.tab:
        return False
    L, T = ses.tab["A08"], ses.tab["A39"]
    a = sorted(L["renglones"])[-1]
    rows = [(_NIV_PROG.get(norm(r[0]), norm(r[0])), r[1]) for r in L["renglones"][a]
            if len(r) > 1 and r[1] and not re.fullmatch(r"\d+", str(r[1]).strip())]
    pares = emparejar_programas(rows, T)
    at = anio_de(T)
    ct = next((j for j, c in enumerate(T["columnas"]) if c == ["Total"]), None)
    if ct is None:
        return False
    filas, sin, aproxs, ids_tot = [], [], [], []
    for nv, nom, idx, aprox in pares:
        if not idx:
            sin.append(f"{_NIV_TXT.get(nv, nv)} en {nom}")
            continue
        ids = [f"A39.f{i}.c{ct}" for i in idx if valor(T, at, i, ct) is not None]
        for x in ids:
            ses.asegurar_celda(x)
        if not ids:
            sin.append(f"{_NIV_TXT.get(nv, nv)} en {nom}")
            continue
        sid = ids[0] if len(ids) == 1 else ses.ejecutar("calcular_serie", {"operacion": "suma", "ids": ids, "nombre": f"{_NIV_TXT.get(nv, nv)} en {nom}: matrícula"}).get("id")
        plan.usa(*ids, sid)
        ids_tot.append(sid)
        sedes = ", ".join(dict.fromkeys(T["filas"][i]["ruta"][1].strip() for i in idx))
        nombre_a39 = T["filas"][idx[0]]["ruta"][-1].strip()
        filas.append({"nombre": f"{_NIV_TXT.get(nv, nv)} en {nom}", "ids": [sid, {"texto": sedes}, {"texto": nombre_a39 + (" (aproximado)" if aprox else "")}],
                      "_v": sum(valor(T, at, i, ct) or 0 for i in idx)})
        if aprox:
            aproxs.append(f"{_NIV_TXT.get(nv, nv)} en {nom} → «{nombre_a39}»")
    if len(filas) < 3:
        return False
    filas.sort(key=lambda f: -f["_v"])
    tot = ses.ejecutar("calcular_serie", {"operacion": "suma", "ids": ids_tot, "nombre": "Matrícula de los programas del SNP"}).get("id") if len(ids_tot) > 1 else None
    plan.usa(tot)
    plan.tablas.append({"titulo": "Matrícula de los programas de estudios avanzados en el Sistema Nacional de Posgrados",
                        "encabezados": ["Programa (lista A08)", f"Matrícula {T['titulos'][at][-9:] if re.search(r'\d{4}-\d{4}$', T['titulos'][at]) else at}",
                                        "Espacio(s)", "Nombre en la tabla A39"],
                        "filas": [{"nombre": f["nombre"], "ids": f["ids"]} for f in filas], "totales": [tot, None, None],
                        "fuente": "Fuente: Agenda Estadística 2025, tabla A08 (programas en el SNP) cruzada por nombre y nivel con la tabla A39 (matrícula por programa)."})
    plan.paso(f"Cruzó por nombre y nivel los {len(rows)} programas de la lista A08 con la matrícula por programa de A39: {len(filas)} emparejados")
    ult = lambda i: (lambda s_: s_[max(s_)] if s_ else None)(ses.ser.get(i, {})) if i else None
    plan.hechos.append(f"Se muestra abajo una tabla con la matrícula de {len(filas)} de los {len(rows)} programas del Sistema Nacional de Posgrados "
                       f"(lista A08 cruzada con la matrícula por programa de la tabla A39). Suma de su matrícula: {fmt(ult(tot))} alumnos.")
    plan.hechos.append("Programas con más alumnos: " + "; ".join(f"{f['nombre']} {fmt(f['_v'])} ({f['ids'][1]['texto']})" for f in filas[:6]) + ".")
    plan.hechos.append("Programas con menos alumnos: " + "; ".join(f"{f['nombre']} {fmt(f['_v'])}" for f in filas[-4:][::-1]) + ".")
    if aproxs:
        plan.hechos.append("Emparejamiento aproximado (el nombre en A39 es más corto): " + "; ".join(aproxs) + ".")
    if sin:
        plan.hechos.append("No se encontraron en la tabla de matrícula: " + "; ".join(sin) + ".")
    plan.hechos.append("Cuando un programa se imparte en varios espacios, su matrícula es la suma de todos ellos.")
    return True


def programas_snp_por_espacio(plan, q):
    """Programas del SNP agrupados por espacio académico (cruce A08 × A39): un renglón por espacio y programa."""
    ses = plan.ses
    if "A08" not in ses.tab or "A39" not in ses.tab:
        return False
    L, T = ses.tab["A08"], ses.tab["A39"]
    a = sorted(L["renglones"])[-1]
    rows = [(_NIV_PROG.get(norm(r[0]), norm(r[0])), r[1]) for r in L["renglones"][a]
            if len(r) > 1 and r[1] and not re.fullmatch(r"\d+", str(r[1]).strip())]
    pares = emparejar_programas(rows, T)
    at = anio_de(T)
    ct = next((j for j, c in enumerate(T["columnas"]) if c == ["Total"]), None)
    _, espacios = detectar(q, indice_espacios({k: v for k, v in ses.tab.items() if v.get("tipo") != "lista"}))
    grupos_q = [tok for rx, tok in GRUPOS if re.search(rx, q)]
    orden_g = {g: k for k, g in enumerate(dict.fromkeys(f["ruta"][0] for f in T["filas"]))}
    reng, sin, aproxs = [], [], []
    for nv, nom, idx, aprox in pares:
        if not idx:
            sin.append(f"{_NIV_TXT.get(nv, nv)} en {nom}")
            continue
        antes = len(reng)
        for i in idx:
            r = T["filas"][i]["ruta"]
            if espacios and not any(e[0] == norm(r[1]) for e in espacios):
                continue
            if grupos_q and not any(tok in norm(r[0]) for tok in grupos_q):
                continue
            cid = f"A39.f{i}.c{ct}" if ct is not None and valor(T, at, i, ct) is not None else None
            if cid:
                ses.asegurar_celda(cid)
                plan.usa(cid)
            reng.append({"esp": r[1].strip(), "grupo": r[0].strip(), "prog": f"{_NIV_TXT.get(nv, nv)} en {nom}" + (" (aproximado)" if aprox else ""),
                         "id": cid, "v": valor(T, at, i, ct) or 0})
        if aprox and len(reng) > antes:
            aproxs.append(f"{_NIV_TXT.get(nv, nv)} en {nom}")
    if not reng:
        return False
    reng.sort(key=lambda x: (orden_g.get(x["grupo"], 99), norm(x["esp"]), x["prog"]))
    cuenta = {}
    for x in reng:
        k = f"{x['esp']} ({x['grupo']})"
        cuenta[k] = cuenta.get(k, 0) + 1
    plan.tablas.append({"titulo": "Programas del Sistema Nacional de Posgrados por espacio académico",
                        "encabezados": ["Espacio académico", "Programa en el SNP (lista A08)", "Matrícula (A39)"],
                        "filas": [{"nombre": f"{x['esp']} ({x['grupo']})", "ids": [{"texto": x["prog"]}, x["id"]]} for x in reng],
                        "fuente": "Fuente: Agenda Estadística 2025, lista A08 (programas en el SNP) cruzada por nombre y nivel con la tabla A39, que dice en qué espacio se imparte cada programa."})
    plan.paso(f"Cruzó los programas de A08 con A39 para saber en qué espacio se imparte cada uno: {len(reng)} renglones en {len(cuenta)} espacios")
    filtro = f" de {', '.join(e[1] for e in espacios)}" if espacios else ""
    plan.hechos.append(f"Se muestra abajo una tabla con los programas del Sistema Nacional de Posgrados{filtro} por espacio académico: "
                       f"{len(reng)} renglones (espacio y programa) en {len(cuenta)} espacio{'s' if len(cuenta) != 1 else ''}. Un programa intrainstitucional aparece en cada espacio donde se imparte.")
    plan.hechos.append("Programas en el SNP por espacio: " + "; ".join(f"{k} {v}" for k, v in sorted(cuenta.items(), key=lambda x: -x[1])[:25]) + ".")
    if espacios or len(cuenta) <= 3:
        plan.hechos.append("Programas: " + "; ".join(f"{x['prog']} ({x['esp']})" for x in reng[:30]) + ".")
    if aproxs:
        plan.hechos.append("Emparejamiento aproximado (en A39 el nombre es más corto): " + "; ".join(aproxs) + ".")
    if sin:
        plan.hechos.append("No se encontraron en la tabla A39: " + "; ".join(sin) + ".")
    return True


DONDE_PROG = re.compile(r"(en )?(cuant|cual|que|donde)\w*\s.*\b(espacios?|sedes?|facultad\w*|centros?|lugar\w*|unidad\w*)\b|donde se (ofrece|imparte|da|estudia)|se (ofrece|imparte)n?\b")
_NIVEL_Q = [(r"\blicenciatura|\bcarrera", "licenciatura"), (r"\bmaestria", "maestria"), (r"\bdoctorado", "doctorado"), (r"\bespecialidad", "especialidad")]


def termino_programa(q):
    """Extrae el nombre buscado: «el programa de estudios de Derecho» → «derecho»."""
    m = re.search(r"(?:programa(?:s)?(?: educativo)?(?: de estudios?)?|licenciatura|carrera|maestria|doctorado|especialidad)\s+(?:en\s+|de\s+)?(.+?)(?:\?|$|\s+(?:en cuant|en que|en cual|se ofrece|se imparte|donde|por espacio))", q)
    if not m:  # «¿dónde se imparte ingeniería en computación?»
        m = re.search(r"se (?:imparte|ofrece|estudia|da)n?\s+(?:la |el |los |las )?(.+?)(?:\?|$|\s+(?:en cuant|en que|en cual|por espacio))", q)
    if not m:
        return None
    t = re.sub(r"\b(el|la|los|las|de|del|en|y|que|se|ofrece|imparte|cuantos|cuales|espacios?|academicos?|uaemex|universidad)\b", " ", m.group(1))
    t = re.sub(r"\s+", " ", t).strip(" ?.,")
    return t or None


def donde_se_imparte(plan, q):
    """¿En cuántos y cuáles espacios se ofrece el programa X? Busca el programa en la matrícula por programa (A26 y A39)."""
    ses = plan.ses
    term = termino_programa(q)
    if not term:
        return False
    raiz5 = lambda ts: {w[:5] for w in ts if w not in ("licenciatura",)}
    tq = raiz5(_toks_prog(term))
    if not tq:
        return False
    nivel_q = next((n for rx, n in _NIVEL_Q if re.search(rx, q)), None)
    fuentes = [t for t, nv in (("A26", "licenciatura"), ("A39", None)) if t in ses.tab and (nivel_q is None or (nivel_q == "licenciatura") == (t == "A26"))]
    progs, nombres_p = {}, {}  # nombre limpio → {espacio: (ids, valor)}
    for tid in fuentes:
        T = ses.tab[tid]
        at = anio_de(T)
        ct = next((j for j, c in enumerate(T["columnas"]) if c == ["Total"]), None)
        rutas = [f["ruta"] for f in T["filas"]]
        for i, r in enumerate(rutas):
            if len(r) < 3 or any(len(x) > len(r) and x[:len(r)] == r for x in rutas):
                continue
            nombre = re.sub(r"\s*\(?\d+\)?$|\*+$", "", r[-1].strip()).strip()
            if nivel_q and nivel_q != "licenciatura" and _nivel_prog(nombre) != nivel_q:
                continue
            tr = raiz5(_toks_prog(nombre))
            if not tq <= tr:
                continue
            esp = f"{r[1].strip()} ({r[0].strip()})"
            # variantes del mismo programa («Licenciatura de…» / «en…», «… 2»): misma clave
            clave_p = ((_nivel_prog(nombre) or "licenciatura"), frozenset(tr), "distancia" in norm(nombre))
            nombre = nombres_p.setdefault(clave_p, nombre)
            d = progs.setdefault(nombre, {})
            ids, v = d.get(esp, ([], 0))
            if ct is not None and valor(T, at, i, ct) is not None:
                ids = ids + [f"{tid}.f{i}.c{ct}"]
                v += valor(T, at, i, ct)
            d[esp] = (ids, v)
    if not progs:
        return False
    grupos_q = [tok for rx, tok in GRUPOS if re.search(rx, q)]
    if grupos_q:  # «¿en cuántas facultades…?»: solo ese grupo
        total_todos = {n: len(d) for n, d in progs.items()}
        progs = {n: {e: v for e, v in d.items() if any(tok in norm(e) for tok in grupos_q)} for n, d in progs.items()}
        progs = {n: d for n, d in progs.items() if d}
        if not progs:
            return False
    exactos = {n: d for n, d in progs.items() if raiz5(_toks_prog(n)) == tq}
    principal = exactos or progs
    otros = {n: d for n, d in progs.items() if n not in principal}
    filas = []
    for nombre, d in sorted(principal.items(), key=lambda x: -len(x[1])):
        for esp, (ids, v) in sorted(d.items(), key=lambda x: -x[1][1]):
            for x in ids:
                ses.asegurar_celda(x)
            sid = ids[0] if len(ids) == 1 else (ses.ejecutar("calcular_serie", {"operacion": "suma", "ids": ids, "nombre": f"{nombre} en {esp}"}).get("id") if ids else None)
            plan.usa(*ids, sid)
            filas.append({"nombre": esp, "ids": [{"texto": nombre}, sid]})
    plan.tablas.append({"titulo": f"Espacios donde se ofrece: {', '.join(principal)}"[:140], "encabezados": ["Espacio académico", "Programa", "Matrícula"],
                        "filas": filas, "fuente": "Fuente: Agenda Estadística 2025, matrícula por espacio y programa educativo (tablas A26 y A39)."})
    plan.paso(f"Buscó «{term}» en la matrícula por programa (tablas {', '.join(fuentes)}): {sum(len(d) for d in principal.values())} renglones")
    orden_p = sorted(principal.items(), key=lambda x: (-len(x[1]), -sum(v for _, v in x[1].values())))
    if len(orden_p) > 6:
        plan.hechos.append(f"Hay {len(orden_p)} programas con «{term}» en el nombre; se describen los 6 que se ofrecen en más espacios y todos aparecen en la tabla.")
    for nombre, d in orden_p[:6]:
        plan.hechos.append(f"{nombre} se ofrece en {len(d)} espacio{'s' if len(d) != 1 else ''} académico{'s' if len(d) != 1 else ''}: "
                           + "; ".join(f"{e} ({fmt(v)} alumnos)" for e, (ids, v) in sorted(d.items(), key=lambda x: -x[1][1])) + ".")
    if otros:
        plan.hechos.append("Otros programas relacionados con «" + term + "»: " + "; ".join(f"{n} ({len(d)} espacio{'s' if len(d) != 1 else ''})" for n, d in sorted(otros.items(), key=lambda x: -len(x[1]))[:10]) + ".")
    if grupos_q:
        plan.hechos.append("Solo se cuentan los espacios del grupo pedido; en todos los espacios académicos: "
                           + "; ".join(f"{n} {total_todos[n]}" for n in principal) + ".")
    plan.hechos.append("Se muestra abajo una tabla con cada espacio y su matrícula. Cuenta solo los espacios con matrícula registrada en la Agenda 2025.")
    return True


def lista_tabla(plan, q, tid):
    """Tablas de texto (programas en el SNP, cuerpos académicos, redes…): se muestra la lista y se dan conteos al modelo."""
    ses = plan.ses
    T = ses.tab[tid]
    a = sorted(T["renglones"])[-1]
    enc, rs = T["encabezados"][a], T["renglones"][a]
    if not rs:
        return False
    es_num = lambda x: bool(re.fullmatch(r"\d+([.,]\d+)?", str(x).strip()))
    # renglones de subtotal (p. ej. «Especialidad | 11» en una columna de nombres): se usan como conteo, no se listan
    llenos1 = [r[1] for r in rs if len(r) > 1 and str(r[1]).strip()]
    col1_texto = bool(llenos1) and sum(1 for x in llenos1 if not es_num(x)) > len(llenos1) / 2
    subt = [r for r in rs if col1_texto and len(r) > 1 and es_num(r[1])]
    filas = [r for r in rs if r not in subt and any(str(x).strip() for x in r)]
    def tipo_col(j):
        vals = [str(r[j]).strip() for r in filas if len(r) > j and str(r[j]).strip()]
        return vals, sum(1 for v in vals if es_num(v))
    # filtro por espacio mencionado en la pregunta (p. ej. «de la Facultad de Química»)
    _, espacios = detectar(q, indice_espacios({k: v for k, v in ses.tab.items() if v.get("tipo") != "lista"}))
    espacios = [e for e in espacios if e[0] not in norm(T["titulo"])]  # «Lenguas» en «Centros de Enseñanza de Lenguas» no es la facultad
    if espacios:
        nombres = [e[0] for e in espacios]
        f2 = [r for r in filas if any(n in norm(str(r[0])) for n in nombres)] \
            or [r for r in filas if any(n in norm(" ".join(map(str, r))) for n in nombres)]
        if f2:
            filas = f2
            plan.paso(f"Filtró la lista por {', '.join(e[1] for e in espacios)}")
        else:
            plan.hechos.append(f"La tabla {tid} «{T['titulos'][a]}» no trae renglones de {', '.join(e[1] for e in espacios)}; "
                               "por eso se muestra la lista completa.")
    if not filas:
        return False
    plan.paso(f"Consultó la lista {tid} «{T['titulos'][a]}»: {len(filas)} renglones")
    plan.tablas.append({"titulo": T["titulos"][a], "encabezados": enc,
                        "filas": [{"nombre": str(r[0]), "textos": [str(x) for x in r[1:]]} for r in filas[:300]],
                        "fuente": (T.get("fuente", {}) or {}).get(a, "") or f"Fuente: Agenda Estadística, tabla {tid}."})
    plan.hechos.append(f"Se muestra abajo la lista completa de la tabla {tid} «{T['titulos'][a]}» con {len(filas)} renglones "
                       f"(columnas: {', '.join(enc)}).")
    if subt and not espacios:
        plan.hechos.append("Conteo que trae la tabla: " + "; ".join(f"{r[0]} {r[1]}" for r in subt) + ".")
    else:  # conteo por una columna de categorías (espacio, DES, nivel, tipo, área…)
        cands = []
        for j in range(len(enc)):
            vals, nnum = tipo_col(j)
            for seg in (-1, 0):  # último o primer tramo de la ruta (p. ej. «Consolidados › Facultad › Ingeniería»)
                dist = {v.split(" › ")[seg] for v in vals}
                if vals and nnum < len(vals) / 2 and 1 < len(dist) <= 40 and len(dist) < len(vals):
                    pref = 0 if re.search(r"espacio|des\b|nivel|tipo|area|alcance|pais|sector", norm(enc[j])) else 1
                    cands.append((pref, seg != 0, j, seg))
                    break
        if cands:
            _, _, j, seg = min(cands)
            cuenta = {}
            for r in filas:
                k = str(r[j]).split(" › ")[seg].strip() if len(r) > j else ""
                if k:
                    cuenta[k] = cuenta.get(k, 0) + 1
            plan.hechos.append(f"Renglones por «{enc[j]}»: " + "; ".join(f"{k} {v}" for k, v in sorted(cuenta.items(), key=lambda x: -x[1])[:20]) + ".")
    # columna de nombres para los ejemplos: la de más textos distintos
    mejor = max(range(len(enc)), key=lambda j: (lambda v, nn: len(set(v)) if nn < len(v) / 2 else -1)(*tipo_col(j)))
    ejemplos = [str(r[mejor]) for r in filas if len(r) > mejor and str(r[mejor]).strip()][:8]
    if ejemplos:
        plan.hechos.append(f"Algunos ejemplos de «{enc[mejor]}»: " + "; ".join(ejemplos) + ".")
    return True


FICHA_PREFIJO = re.compile(r"^(facultad de|escuela de|centro universitario uaem|unidad academica profesional|plantel)\s+", re.I)


def ficha_de(ses, q):
    """Ficha por espacio cuyo nombre aparece en la pregunta (el más largo; plantel o centro según lo que se diga)."""
    from calculos import PIDE_FICHA  # noqa: F401
    cands = []
    for tid, T in ses.tab.items():
        if T.get("seccion") != "Fichas por espacio":
            continue
        t = norm(T["titulo"])
        nombre = FICHA_PREFIJO.sub("", re.sub(r'"', "", t)).replace(" de la escuela preparatoria", "").strip()
        variantes = {t, nombre, re.sub(r"^(dr|lic|mtro|sor)\.?\s+", "", nombre)}
        hit = max((len(v) for v in variantes if len(v) >= 4 and re.search(rf"\b{re.escape(v)}\b", q)), default=0)
        if not hit:
            continue
        # «Texcoco», «Nezahualcóyotl»: plantel o centro universitario según la pregunta
        es_plantel = tid.startswith("B")
        if re.search(r"plantel|preparatoria|prepa\b|bachillerato", q):
            hit += 100 if es_plantel else -100
        elif re.search(r"centro universitario|\bcu\b|\buap\b|unidad academica", q):
            hit += -100 if es_plantel else 100
        cands.append((hit, tid))
    return max(cands)[1] if cands else None


def ficha_resumen(plan, q, tid):
    """Ficha de un espacio: año de fundación y los totales de cada sección; la ficha completa se muestra abajo."""
    T = plan.ses.tab[tid]
    a = sorted(T["renglones"])[-1]
    rs = T["renglones"][a]
    if not rs:
        return False
    por_sec = {}
    for sec, conc, val in rs:
        if conc.count(" › ") >= 2:  # detalle por programa: va en la tabla, no en el resumen
            continue
        por_sec.setdefault(sec, []).append(f"{conc} = {val}")
    plan.hechos.append(f"Ficha {tid} «{T['titulos'][a]}» (resumen por sección; la ficha completa se muestra abajo).")
    if re.search(r"fund", q):
        anio = next((v for s_, c, v in rs if c == "Año de fundación"), None)
        if anio:
            plan.hechos.insert(0, f"Año de fundación de {T['titulo']}: {anio} (ficha {tid}).")
    for sec, xs in por_sec.items():
        plan.hechos.append(f"{sec}: " + "; ".join(xs[:40]) + ".")
    plan.tablas.append({"titulo": T["titulos"][a], "encabezados": T["encabezados"][a],
                        "filas": [{"nombre": r[0], "textos": [str(x) for x in r[1:]]} for r in rs],
                        "fuente": (T.get("fuente", {}) or {}).get(a, "") or f"Fuente: Agenda Estadística, ficha {tid}."})
    plan.paso(f"Consultó la ficha {tid} «{T['titulos'][a]}»")
    return True


TIPO_FICHA = {"O": "Organismo académico", "U": "Centro universitario UAEM", "V": "Unidad académica profesional",
              "N": "Instituto o centro de investigación", "B": "Plantel de la Escuela Preparatoria"}


def dato_fichas(plan, q, concepto):
    """Un mismo dato (p. ej. año de fundación) en todas las fichas por espacio: tabla completa y extremos."""
    ses = plan.ses
    cq = [w for w in norm(concepto).split() if len(w) >= 3 and w not in ("del", "las", "los")]
    filas = []
    tipos = {k for k, rx in (("O", r"facultad|escuela|organismo"), ("B", r"plantel|preparatoria|prepa\b|bachillerato"),
                              ("U", r"centros? universitario"), ("V", r"unidad(es)? academica|\buap\b"),
                              ("N", r"instituto|centros? de (investigacion|estudios)")) if re.search(rx, q)}
    for tid, T in ses.tab.items():
        if T.get("seccion") != "Fichas por espacio" or (tipos and tid[0] not in tipos):
            continue
        a = sorted(T["renglones"])[-1]
        for sec, conc, val in T["renglones"][a]:
            if all(w in norm(sec + " " + conc) for w in cq):
                filas.append((tid, T["titulo"], TIPO_FICHA.get(tid[0], ""), val))
                break
    if not filas:
        return False
    anio = lambda v: int(m.group(0)) if (m := re.search(r"(18|19|20)\d{2}", str(v))) else 9999
    if all(anio(v) < 9999 for *_, v in filas):
        filas.sort(key=lambda x: (anio(x[3]), x[1]))
        viejos = [f for f in filas if anio(f[3]) == anio(filas[0][3])]
        nuevos = [f for f in filas if anio(f[3]) == anio(filas[-1][3])]
        if re.search(r"mas (recient|nuev|joven)", q):
            viejos, nuevos = nuevos, viejos
            plan.hechos.append(f"Respuesta: el más reciente es {', '.join(f[1] for f in viejos)} ({viejos[0][3]}).")
        elif re.search(r"mas (antigu|viej)", q):
            plan.hechos.append(f"Respuesta: el más antiguo es {', '.join(f[1] for f in viejos)} ({viejos[0][3]}).")
        if re.search(r"mas (recient|nuev|joven)", q):
            viejos, nuevos = nuevos, viejos
        plan.hechos.append(f"{concepto} de {len(filas)} espacios (fichas por espacio, se muestran todos abajo, del más antiguo al más reciente). "
                           f"El más antiguo: {', '.join(f[1] for f in viejos)} ({viejos[0][3]}). "
                           f"El más reciente: {', '.join(f[1] for f in nuevos)} ({nuevos[0][3]}).")
        por_tipo = {}
        for f in filas:
            por_tipo.setdefault(f[2], []).append(f"{f[1]} {f[3]}")
        for t, xs in por_tipo.items():
            plan.hechos.append(f"{t}: " + "; ".join(xs) + ".")
        if any(re.search(r"[*/]", str(f[3])) for f in filas):
            plan.hechos.append("Algunos espacios traen dos años (p. ej. «1986 / 2008*»): la ficha explica el cambio en sus notas.")
    else:
        plan.hechos.append(f"{concepto} en {len(filas)} espacios (fichas por espacio): " + "; ".join(f"{f[1]} {f[3]}" for f in filas) + ".")
    plan.tablas.append({"titulo": f"{concepto} por espacio universitario", "encabezados": ["Espacio", "Tipo de espacio", concepto],
                        "filas": [{"nombre": f[1], "textos": [f[2], str(f[3])]} for f in filas],
                        "fuente": "Fuente: Agenda Estadística 2025, fichas por espacio (O, U, V, N y B)."})
    plan.paso(f"Reunió «{concepto}» de {len(filas)} fichas por espacio")
    return True


POR_ESPACIOS_Q = re.compile(r"\b(cada|por|todos los|todas las|los|las)\s+(espacios?|facultad(es)?|plantel(es)?|centros?|unidad(es)?|uap|escuelas?|sedes?|organismos?)|"
                            r"\b(espacios|facultades|planteles|centros universitarios|unidades academicas)\b")


def cambio_espacios(plan, q, grupos):
    """Cambio de un indicador entre dos años en cada espacio: gráfica de cambio y tabla completa."""
    ses = plan.ses
    hall = conceptos_en(q)
    fuentes = []  # (tid, [columnas])
    if hall:
        fuentes = [(t, cols) for t, cols in CONCEPTOS[hall[0]]["tablas"]]
        nombre_ind = CONCEPTOS[hall[0]]["varios"]
    else:
        con_esp = lambda T: any(len(f["ruta"]) == 2 and GRUPO_RX.match(norm(f["ruta"][0])) for f in T["filas"])
        rk = [x for x in ses._rank_tablas(plan.pregunta) if ses.tab[x["id"]].get("tipo") != "lista" and con_esp(ses.tab[x["id"]])]
        if not rk:
            return False
        T = ses.tab[rk[0]["id"]]
        c = elegir_columna(T, q)
        fuentes = [(T["id"], [" › ".join(T["columnas"][c])])]
        col_txt = " › ".join(T["columnas"][c])
        nombre_ind = T["titulo"] if col_txt == "Total" else f"{col_txt} ({T['titulo']})"
    anios = sorted({a for t, _ in fuentes if t in ses.tab for a in ses.tab[t]["datos"]}, key=int)
    a1 = str(CAMBIO_ANIOS[1]) if CAMBIO_ANIOS and CAMBIO_ANIOS[1] and str(CAMBIO_ANIOS[1]) in anios else anios[-1]
    previos = [a for a in anios if int(a) < int(a1)]
    a0 = str(CAMBIO_ANIOS[0]) if CAMBIO_ANIOS and CAMBIO_ANIOS[0] and str(CAMBIO_ANIOS[0]) in previos else (previos[-1] if previos else None)
    if not a0:
        return False
    esp = {}  # (grupo, espacio) -> {"ids": [...], "nombre": ...}
    for tid, cols in fuentes:
        T = ses.tab.get(tid)
        if not T or T.get("tipo") == "lista":
            continue
        nombres = [" › ".join(c) for c in T["columnas"]]
        js = [nombres.index(c) for c in cols if c in nombres]
        for i, f in enumerate(T["filas"]):
            r = f["ruta"]
            if len(r) != 2 or not GRUPO_RX.match(norm(r[0])):
                continue
            g = re.sub(r"\s*\*+$", "", r[0].strip())
            if grupos and not any(tok in norm(g) for tok in grupos):
                continue
            k = (norm(g).split()[0], norm(r[1]))
            d = esp.setdefault(k, {"ids": [], "nombre": f"{r[1].strip()} ({g})"})
            for j in js:
                cid = f"{tid}.f{i}.c{j}"
                if ses.asegurar_celda(cid):
                    d["ids"].append(cid)
    # un espacio que cambió de grupo (p. ej. Tianguistenco: UAP en 2024, centro universitario en 2025) se une por su nombre
    def anios_con(d):
        return {a for a in (a0, a1) if any(ses.ser[i].get(int(a)) is not None for i in d["ids"])}
    for k in list(esp):
        if k not in esp:
            continue
        otro = next((k2 for k2 in esp if k2 != k and k2[1] == k[1] and anios_con(esp[k]) == {a1} and anios_con(esp[k2]) == {a0}), None)
        if otro:
            g0 = esp[otro]["nombre"].split("(")[-1].rstrip(")")
            esp[k]["ids"] += esp[otro]["ids"]
            esp[k]["nombre"] = esp[k]["nombre"][:-1] + f"; en {a0}: {g0})"
            del esp[otro]
    filas = []
    for k, d in esp.items():
        por_anio = {}
        for a in (a0, a1):
            vs = [ses.ser[i].get(int(a)) for i in d["ids"]]
            if any(v is not None for v in vs):
                por_anio[a] = sum(v or 0 for v in vs)
        if a0 in por_anio and a1 in por_anio:
            filas.append((d, por_anio[a0], por_anio[a1]))
    sin = [d["nombre"] for k, d in esp.items() if d not in [x[0] for x in filas] and d["ids"]]
    if len(filas) < 2:
        return False
    filas.sort(key=lambda x: -(x[2] - x[1]))
    ids_graf = []
    for d, v0, v1 in filas:
        if True:  # serie propia con el nombre completo del espacio; un año sin posgrado suma 0 ahí, no se pierde el año
            vals = {}
            for y in {y for i in d["ids"] for y in ses.ser[i]}:
                vs = [ses.ser[i].get(y) for i in d["ids"]]
                if any(v is not None for v in vs):
                    vals[y] = round(sum(v or 0 for v in vs), 4)
            ses.n_series += 1
            sid = f"S{ses.n_series}"
            ses.ser[sid] = vals
            ses.ind[sid] = {"id": sid, "ruta": d["nombre"], "concepto": d["nombre"], "eje": "Serie calculada", "archivo": "calc", "fila_excel": "",
                            "derivada": {"op": "suma", "ids": d["ids"], "formula": " + ".join(d["ids"])}}
            ses.calculadas[sid] = {"nombre": d["nombre"], "op": "suma", "ids": d["ids"], "formula": " + ".join(d["ids"]),
                                   "valores": {str(y): v for y, v in vals.items()}}
        ses.ind.setdefault(sid, {})["ruta"] = d["nombre"]
        if sid in ses.calculadas:
            ses.calculadas[sid]["nombre"] = d["nombre"]
        ids_graf.append(sid)
        plan.usa(sid, *d["ids"])
    t0, t1 = sum(x[1] for x in filas), sum(x[2] for x in filas)
    sube = [x for x in filas if x[2] > x[1]]
    baja = [x for x in filas if x[2] < x[1]]
    sg = lambda v: ("+" if v >= 0 else "−") + fmt(abs(v))
    pct = lambda v0, v1: f" ({'+' if v1 >= v0 else '−'}{fmt(round(abs(v1 - v0) / v0 * 100, 1))}%)" if v0 else ""
    fuentes_txt = " + ".join(t for t, _ in fuentes)
    plan.hechos.append(f"Respuesta: cambio de {nombre_ind} de {a0} a {a1} en {len(filas)} espacios (tablas {fuentes_txt}). "
                       f"Suma de esos espacios: {fmt(t0)} → {fmt(t1)} ({sg(t1 - t0)}{pct(t0, t1)}). "
                       f"Subieron {len(sube)}, bajaron {len(baja)} y {len(filas) - len(sube) - len(baja)} no cambiaron.")
    if sin:
        plan.hechos.append(f"Sin dato en {a0} o en {a1} (no se comparan): " + "; ".join(sin[:15]) + ".")
    if sube:
        plan.hechos.append("Mayores aumentos: " + "; ".join(f"{d['nombre']} {fmt(v0)} → {fmt(v1)} ({sg(v1 - v0)})" for d, v0, v1 in sube[:6]) + ".")
    if baja:
        plan.hechos.append("Mayores disminuciones: " + "; ".join(f"{d['nombre']} {fmt(v0)} → {fmt(v1)} ({sg(v1 - v0)})" for d, v0, v1 in sorted(baja, key=lambda x: x[2] - x[1])[:6]) + ".")
    if plan.grafica({"tipo": "cambio_anios", "ids": ids_graf[:80], "desde": int(a0), "hasta": int(a1),
                     "titulo": f"Cambio de {nombre_ind} por espacio, {a0}–{a1}"[:120]}):
        plan.hechos.append(f"Se muestra una gráfica con el cambio de cada espacio de {a0} a {a1} (del que más subió al que más bajó) y abajo la tabla completa.")
    plan.tablas.append({"titulo": f"Cambio de {nombre_ind} por espacio, {a0}–{a1}"[:140], "encabezados": ["Espacio", a0, a1, "Cambio", "%"],
                        "filas": [{"nombre": d["nombre"], "textos": [fmt(v0), fmt(v1), sg(v1 - v0), pct(v0, v1).strip(" ()")]} for d, v0, v1 in filas],
                        "fuente": f"Fuente: Agenda Estadística {a0} y {a1}, tablas {fuentes_txt}."})
    plan.paso(f"Comparó {nombre_ind} de {a0} y {a1} en {len(filas)} espacios")
    return True



MATR_NIVEL_NO = re.compile(r"\b(por|cada|en cada) (espacio|facultad|plantel|centro|unidad|instituto|programa|municipio|sexo|modalidad|sistema)|"
                           r"facultad|plantel|preparatoria|centro universitario|\buap\b|programa|hombres|mujeres|sexo|egresad|titulad|"
                           r"ingreso|primer ano|discapacid|indigena|becad|movilidad|cele|cilc|incorporad|ptc|profesor|docente")


def matricula_incorporada(ses, a0, a1):
    """(dependiente, incorporada, total) de la tabla A12 para los dos años, o None."""
    T = (ses.tab or {}).get("A12")
    if not T or T.get("tipo") != "numerica":
        return None
    try:
        jd, ji, jt = (str(T["columnas"].index(c)) for c in (["Sistema", "Dependiente", "Total"], ["Sistema", "Incorporado", "Total"], ["Total"]))
    except ValueError:
        return None
    out = []
    for a in (a0, a1):
        d = T["datos"].get(str(a), {})
        filas = [i for i in d if T["filas"][int(i)]["ruta"] == ["Total"]]
        if not filas:
            return None
        r = d[filas[-1]]
        if jd not in r or jt not in r:
            return None
        out.append((r[jd], r.get(ji, 0), r[jt]))
    return out


def matricula_niveles(plan, q, a0, a1):
    """«Relación / comparación de la matrícula 2024 y 2025»: total y por nivel en los dos años, con el cambio."""
    ses = plan.ses
    rutas = [("Matrícula", "Total"), ("Matrícula > Bachillerato", "Bachillerato"),
             ("Matrícula > Estudios profesionales", "Estudios profesionales"),
             ("Matrícula > Matricula de estudios avanzados", "Estudios avanzados")]
    por_ruta = {}
    for i in ses.ind.values():  # la primera serie con esa ruta (la de la Agenda histórica, His01)
        por_ruta.setdefault(i["ruta"], i["id"])
    filas = []
    for ruta, nombre in rutas:
        sid = por_ruta.get(ruta)
        v0, v1 = (ses.ser.get(sid, {}).get(a) for a in (a0, a1)) if sid else (None, None)
        if v0 is not None and v1 is not None:
            filas.append((sid, nombre, v0, v1))
    if len(filas) < 2 or filas[0][1] != "Total":
        return False
    sg = lambda v: ("+" if v >= 0 else "−") + fmt(abs(v))
    pct = lambda v0, v1: f"{'+' if v1 >= v0 else '−'}{fmt(round(abs(v1 - v0) / v0 * 100, 1))}%" if v0 else ""
    _, tot, t0, t1 = filas[0]
    plan.hechos.append(f"Respuesta: la matrícula total de la UAEMEX (sistema dependiente) pasó de {fmt(t0)} en {a0} a {fmt(t1)} en {a1} "
                       f"({sg(t1 - t0)}, {pct(t0, t1)}).")
    plan.hechos.append("Por nivel (sistema dependiente): " + "; ".join(
        f"{n} {fmt(v0)} → {fmt(v1)} ({sg(v1 - v0)}, {pct(v0, v1)}; {fmt(round(v1 / t1 * 100, 1))}% del total en {a1})" for _, n, v0, v1 in filas[1:]) + ".")
    if plan.grafica({"tipo": "cambio_anios", "ids": [f[0] for f in filas], "desde": a0, "hasta": a1,
                     "titulo": f"Matrícula por nivel, {a0} y {a1}"}):
        plan.hechos.append(f"Se muestra una gráfica con la matrícula de {a0} y {a1} en cada nivel y la diferencia, y abajo la tabla.")
    plan.tablas.append({"titulo": f"Matrícula por nivel, {a0} y {a1}", "encabezados": ["Nivel", str(a0), str(a1), "Cambio", "%"],
                        "filas": [{"nombre": n, "textos": [fmt(v0), fmt(v1), sg(v1 - v0), pct(v0, v1)]} for _, n, v0, v1 in filas],
                        "fuente": "Fuente: Agenda Estadística, series históricas de matrícula (dependiente)."})
    inc = matricula_incorporada(ses, a0, a1)
    if inc:  # el sistema incorporado va aparte: no se suma al dependiente
        (_, i0, _), (_, i1, _) = inc
        plan.hechos.append(f"Aparte, el sistema incorporado (escuelas incorporadas, que no se suman a la cifra anterior) tuvo {fmt(i0)} en {a0} "
                           f"y {fmt(i1)} en {a1} ({sg(i1 - i0)}, {pct(i0, i1)}) (tabla A12).")
    plan.paso(f"Comparó la matrícula total y por nivel de {a0} y {a1}")
    return True

# niveles educativos: una tabla o serie de otro nivel no responde la pregunta (eficiencia terminal de posgrado ≠ la de bachillerato)
NIVELES_RX = {"bachillerato": r"bachillerato|preparatoria", "licenciatura": r"licenciatura|estudios profesionales|\bprofesional(es)?\b",
              "posgrado": r"posgrado|estudios avanzados|maestria|doctorado|especialidad"}
NIVEL_TXT = {"bachillerato": "bachillerato", "licenciatura": "licenciatura (estudios profesionales)", "posgrado": "posgrado (estudios avanzados)"}


def niveles_de(texto):
    t = norm(texto)
    return {k for k, rx in NIVELES_RX.items() if re.search(rx, t)}


class _BuscadorNivel:
    """Envuelve el buscador de series para quitar las de otro nivel (y los indicadores padre que se dividen por nivel)."""
    def __init__(self, base, ses, nq):
        self.base, self.ses, self.nq = base, ses, nq

    def compatible(self, sid):
        r = norm(self.ses.nombre(sid))
        nv = niveles_de(r)
        if nv:
            return bool(nv & self.nq)
        rutas = [norm(i["ruta"]) for i in self.ses.ind.values() if isinstance(i, dict) and i.get("ruta")]
        return not any(x.startswith(r + " > ") and niveles_de(x) for x in rutas)

    def buscar(self, texto, maximo=8):
        q, res = self.base.buscar(texto, maximo * 3)
        return q, [x for x in res if self.compatible(x["id"])][:maximo]

    def __getattr__(self, k):
        return getattr(self.base, k)


def limitar_nivel(ses, pregunta, q):
    """Si la pregunta nombra un nivel, quita las tablas y series de otros niveles. Devuelve un Plan de «no encontrado» cuando
    lo que mejor coincide existe solo para otros niveles (p. ej. eficiencia terminal de posgrado), o None."""
    nq = niveles_de(q)
    if not nq or not ses.tab:
        return None
    rank0, busc0 = ses._rank_tablas, ses.buscador
    def nivel_ok(tid):
        nv = niveles_de(ses.tab[tid]["titulo"])
        return not nv or bool(nv & nq)
    def con_sinon(texto):  # la Agenda dice «estudios avanzados» y «estudios profesionales»; «posgrado» solo aparece en el SNP (A08)
        t = re.sub(r"\bposgrados?\b", "estudios avanzados", norm(texto))
        return t + (" estudios profesionales" if "licenciatura" in nq and "estudios profesionales" not in t else "")
    ses._rank_tablas = lambda texto: [x for x in rank0(con_sinon(texto)) if nivel_ok(x["id"])]
    ses.buscador = _BuscadorNivel(busc0, ses, nq)
    # para decidir si el dato existe en el nivel pedido se compara sin las palabras del nivel (si no, «posgrado» basta para coincidir)
    tema = re.sub("|".join(NIVELES_RX.values()) + r"|\b(de|del|en|el|la|los|las)\b", " ", norm(pregunta))
    if len(tema.split()) == 0:
        return None
    todos = rank0(tema)
    if not todos:
        return None
    tope = todos[0]["pts"]
    fuera = [x for x in todos if x["pts"] >= 0.8 * tope and not nivel_ok(x["id"])]
    dentro = [x for x in todos if nivel_ok(x["id"]) and niveles_de(ses.tab[x["id"]]["titulo"])]  # del nivel pedido, no genéricas
    _, s_todas = busc0.buscar(tema, 8)
    _, s_ok = ses.buscador.buscar(pregunta, 8)
    s_ok = [x for x in s_ok if niveles_de(ses.nombre(x["id"])) & nq]  # una serie del nivel pedido
    s_tope = s_todas[0]["pts"] if s_todas else 0
    hay_serie = bool(s_ok) and s_ok[0]["pts"] >= 0.8 * s_tope and s_ok[0]["pts"] >= 5
    hay_tabla = bool(dentro) and dentro[0]["pts"] >= 0.6 * tope
    if not fuera or hay_serie or hay_tabla:
        return None
    plan = Plan(ses, pregunta)
    otros = sorted({n for x in fuera for n in niveles_de(ses.tab[x["id"]]["titulo"])} - nq)
    pedido = " y ".join(NIVEL_TXT[n] for n in sorted(nq))
    tablas_txt = "; ".join(f"tabla {x['id']} «{ses.tab[x['id']]['titulo']}»" for x in fuera[:3])
    plan.paso(f"Buscó el dato para {pedido}: las tablas que coinciden son de otro nivel ({', '.join(x['id'] for x in fuera[:3])})")
    plan.hechos.append(f"No encontré ese dato para {pedido} en la Agenda Estadística; la Agenda lo publica para "
                       f"{' y '.join(NIVEL_TXT[n] for n in otros)} ({tablas_txt}).")
    if dentro and dentro[0]["pts"] >= 0.3 * tope:
        T = ses.tab[dentro[0]["id"]]
        plan.hechos.append(f"Lo más cercano para {pedido} es la tabla {T['id']} «{T['titulo']}».")
    return plan


def planear(ses, pregunta):
    """Devuelve un Plan con hechos, pasos y gráficas, o None si la pregunta no encaja en el modo guiado."""
    pregunta = canon_ptc(pregunta)  # una sola forma de decir PTC
    q = norm(pregunta)
    global ANIO_PEDIDO, CAMBIO_ANIOS
    anios_q = sorted({int(x) for x in re.findall(r"\b(20[12]\d)\b", q) if 2018 <= int(x) <= 2026})
    ANIO_PEDIDO = anios_q[-1] if anios_q else None
    CAMBIO_ANIOS = (anios_q[0], anios_q[-1]) if len(anios_q) >= 2 else ((None, ANIO_PEDIDO) if CAMBIO_Q.search(q) else None)
    if ALUMNOS_Q.search(q) and not MATR_NIVEL_NO.search(q) and (len(anios_q) >= 2 or re.search(r"relacion|compar|\bvs\b|frente a|por nivel|niveles|matricula total|total de (la )?matricula|total de (alumnos|estudiantes)", q)):
        _, esp_mn = detectar(q, indice_espacios({k: v for k, v in ses.tab.items() if v.get("tipo") != "lista"})) if ses.tab else (None, [])
        if not [e for e in esp_mn if not NIVELES_ESP.match(e[0])]:
            a1 = anios_q[-1] if anios_q else max(a for a in ses.ser.get("His01-46", {2025: 0}))
            a0 = anios_q[0] if len(anios_q) >= 2 else a1 - 1
            plan = Plan(ses, pregunta)
            if matricula_niveles(plan, q, a0, a1):
                return plan
    if ses.tab:
        ses.tab = vista_bloques(ses.tab)
        plan_nivel = limitar_nivel(ses, pregunta, q)
        if plan_nivel:
            return plan_nivel
        if ANIO_PEDIDO:  # etiquetas de columna del año pedido (p. ej. «Personas egresadas global 2023-2024»)
            ses.tab = {k: ({**T, "columnas": [T["columnas_anio"][str(ANIO_PEDIDO)].get(str(j), c) for j, c in enumerate(T["columnas"])]}
                           if str(ANIO_PEDIDO) in T.get("columnas_anio", {}) else T) for k, T in ses.tab.items()}
        if not SNP_Q.search(q) and DONDE_PROG.search(q) and re.search(r"programa|licenciatura|carrera|maestria|doctorado|especialidad|se (imparte|ofrece|estudia)", q):
            plan = Plan(ses, pregunta)
            if donde_se_imparte(plan, q):
                return plan
        if SNP_Q.search(q) and re.search(r"programa|posgrado", q):
            _, esp_q = detectar(q, indice_espacios({k: v for k, v in ses.tab.items() if v.get("tipo") != "lista"}))
            esp_q = [e for e in esp_q if not NIVELES_ESP.match(e[0])]
            if esp_q or re.search(r"\b(por|cada|en cada) (espacio|facultad|plantel|centro|unidad|instituto|sede|dependencia)|\bdonde\b|\bque (espacio|facultad|centro)", q):
                plan = Plan(ses, pregunta)
                if programas_snp_por_espacio(plan, q):
                    return plan
        if SNP_Q.search(q) and re.search(r"alumn|matricul|estudiant|inscrit", q) and re.search(r"programa|cada|cuales|lista|tabla", q):
            plan = Plan(ses, pregunta)
            if matricula_lista_programas(plan, q):
                return plan
        from calculos import PIDE_FICHA
        if re.search(r"(espacio|facultad|escuela|plantel|preparatoria|centro|unidad|uap|instituto)s?\b.*\bmas (antigu|recient|viej|nuev|joven)|\bmas (antigu|recient|viej|nuev|joven)\w*\b.*(espacio|facultad|escuela|plantel|prepa|centro|unidad|uap|instituto)", q):
            plan = Plan(ses, pregunta)
            if dato_fichas(plan, q, "Año de fundación"):
                return plan
        if re.search(r"fundaci|fundad|se fundo", q) and (re.search(r"\b(cada|todos|todas|por|lista|tabla|cuales|que espacios?|mas antigu|mas recient|primer)\b|espacios", q) or not ficha_de(ses, q)):
            plan = Plan(ses, pregunta)
            if dato_fichas(plan, q, "Año de fundación"):
                return plan
        if PIDE_FICHA.search(q):
            tf = ficha_de(ses, q)
            if tf:
                plan = Plan(ses, pregunta)
                if ficha_resumen(plan, q, tf):
                    return plan
        rk0 = ses._rank_tablas(pregunta)
        if rk0 and ses.tab[rk0[0]["id"]].get("tipo") == "lista" and ses.tab[rk0[0]["id"]].get("seccion") != "Fichas por espacio" \
                and not ALUMNOS_Q.search(q):
            plan = Plan(ses, pregunta)
            if lista_tabla(plan, q, rk0[0]["id"]):
                return plan
            return None  # lista de texto que no se pudo mostrar: mejor el modo con herramientas
    por_espacio = re.search(r"espacio|facultad|plantel|centro|unidad|uap|escuela|sede|\bcual|\bque (espacio|facultad|plantel)|mejor|peor|mayor|menor", q)
    if CAMBIO_ANIOS and ses.tab and POR_ESPACIOS_Q.search(q):
        g_q, e_q = detectar(q, indice_espacios(ses.tab))
        e_q = [e for e in e_q if not NIVELES_ESP.match(e[0])]
        if len(e_q) <= 1 and not (len(e_q) == 1 and not re.search(r"cada|todos|todas|por ", q)):
            plan = Plan(ses, pregunta)
            if cambio_espacios(plan, q, g_q):
                return plan
    if TABLA_Q.search(q) and por_espacio and conceptos_en(q):
        plan = Plan(ses, pregunta)
        if tabla_espacios(plan, q):
            return plan
    if RELACION.search(q) and por_espacio and len(conceptos_en(q)) == 2:
        plan = Plan(ses, pregunta)
        if relacion_espacios(plan, q):
            return plan
    if DIVISION.search(q):
        return None  # divisiones entre indicadores: mejor el modo con herramientas
    plan = Plan(ses, pregunta)
    if ses.tab:
        grupos, espacios = detectar(q, indice_espacios(ses.tab))
        espacios = [e for e in espacios if not NIVELES_ESP.match(e[0])]  # «licenciatura» es nivel, no un espacio
        # un mismo espacio puede aparecer en varios grupos o bloques (Tianguistenco: centro universitario, antes UAP);
        # si todos tienen el mismo nombre es UN espacio, no una comparación
        if len(espacios) >= 2 and len({e[1] for e in espacios}) == 1:
            espacios = sorted(espacios, key=lambda e: 0 if any(e[2].startswith(g) for g in grupos) else 1)[:1]
        if not grupos and not espacios and re.search(r"\b(por|cada|en cada) espacios?\b", q):
            grupos = ["*"]
        if not espacios and RANK_PROG.search(q) and EXTREMO.search(q) and ranking_programas(plan, q):
            return plan
        plan = Plan(ses, pregunta)
        # «¿qué espacio / facultad tiene menos (o más) X?»
        extremo_esp = not espacios and EXTREMO.search(q) and re.search(
            r"\b(que|cual|cuales|quien)\b[^?]*\b(espacios?|facultad(es)?|planteles?|centros?|unidad(es)?|escuelas?|institutos?|uap)\b", q)
        if extremo_esp:
            if comparar_espacios(plan, grupos or ["*"], [], q):
                return plan
            plan = Plan(ses, pregunta)
        if len(espacios) >= 2 or (grupos and COMPARAR.search(q) and not espacios):
            if comparar_espacios(plan, grupos, espacios if len(espacios) >= 2 else [], q):
                return plan
        elif len(espacios) == 1:
            if MATR_ESP_Q.search(q) and not NIVELES_ESP.search(q) and not MATR_ESP_NO.search(q) and not POR_PROGRAMA.search(q) \
                    and not PERSONAL.search(q) and matricula_espacio(plan, espacios[0], q):
                return plan
            plan = Plan(ses, pregunta)
            if ficha_espacio(plan, espacios[0], q):
                return plan
    plan = Plan(ses, pregunta)
    if RANK_PROG.search(q) and EXTREMO.search(q) and ranking_programas(plan, q):
        return plan
    plan = Plan(ses, pregunta)
    if serie(plan, q):
        return plan
    plan = Plan(ses, pregunta)
    if resumen_tabla(plan, q):
        return plan
    return None


def resumen_tabla(plan, q):
    """Último recurso: total de la tabla más relacionada y los espacios con más."""
    ses = plan.ses
    rk = ses._rank_tablas(plan.pregunta)
    if not rk or rk[0]["pts"] < 4:
        return False
    tid = rk[0]["id"]
    T = ses.tab[tid]
    if T.get("tipo") == "lista":
        return False
    a = anio_de(T)
    c = elegir_columna(T, q)
    col = " › ".join(T["columnas"][c])
    F = T["filas"]
    ft = next((i for i, f in enumerate(F) if norm(f["ruta"][0]) == "total" and len(f["ruta"]) == 1), None)
    if ft is not None and valor(T, a, ft, c) is not None:
        ses.asegurar_celda(f"{tid}.f{ft}.c{c}")
        plan.usa(f"{tid}.f{ft}.c{c}")
        tot = [f"{' › '.join(T['columnas'][j])} = {fmt(valor(T, a, ft, j))}" for j in columnas_total(T) if valor(T, a, ft, j) is not None]
        for j in columnas_total(T):
            if valor(T, a, ft, j) is not None:
                ses.asegurar_celda(f"{tid}.f{ft}.c{j}")
                plan.usa(f"{tid}.f{ft}.c{j}")
        plan.hechos.append(f"Tabla {tid} «{T['titulos'][a]}», total: " + "; ".join(tot) + ".")
    # renglones que nombran lo que se pregunta (p. ej. «Sesiones del Consejo Universitario», «Seguidores › Facebook»): van primero
    from calculos import VACIAS_T
    verbos = {"tuvo", "tiene", "tienen", "tuvieron", "hubo", "fueron", "cuanto", "cuantos", "cuantas", "cuanta", "existen", "hay", "son", "fue", "tenemos", "dime"}
    pq = [w[:6] for w in norm(q).split() if len(w) >= 4 and w not in VACIAS_T and w not in verbos and not w.isdigit()]
    pt = norm(T["titulo"])
    pq_f = [w for w in pq if w not in pt] or pq  # lo que el título ya dice no distingue renglones
    if pq_f:
        cuenta = {i: sum(1 for w in pq_f if w in norm(" ".join(f["ruta"]))) for i, f in enumerate(F) if norm(f["ruta"][0]) != "total"}
        mejor = max(cuenta.values(), default=0)
        if mejor >= min(2, len(pq_f)):
            pos = 0
            for i in [i for i, n in cuenta.items() if n == mejor][:4]:
                vals = [(j, valor(T, a, i, j)) for j in range(len(T["columnas"]))]
                vals = [(j, v) for j, v in vals if v is not None]
                if not vals:
                    continue
                for j, _ in vals:
                    ses.asegurar_celda(f"{tid}.f{i}.c{j}")
                    plan.usa(f"{tid}.f{i}.c{j}")
                pos += 1
                plan.hechos.insert(pos - 1, f"Tabla {tid} «{T['titulos'][a]}», «{' › '.join(x.strip() for x in F[i]['ruta'])}»: "
                                   + "; ".join(f"{' › '.join(T['columnas'][j])} = {fmt(v)}" for j, v in vals) + ".")
    hojas = [(i, valor(T, a, i, c)) for i, f in enumerate(F) if len(f["ruta"]) == 2 and not f["ruta"][0].startswith("~")]
    if not any(GRUPO_RX.match(norm(F[i]["ruta"][0])) for i, _ in hojas):  # tabla sin espacios (sectores, tipos…): sus renglones principales
        hojas = [(i, valor(T, a, i, c)) for i, f in enumerate(F) if len(f["ruta"]) == 1 and norm(f["ruta"][0]) != "total" and not f["ruta"][0].startswith("~")]
    hojas = sorted([(i, v) for i, v in hojas if v], key=lambda x: -x[1])
    if hojas:
        top = hojas[:12]
        for i, _ in top:
            plan.usa(f"{tid}.f{i}.c{c}")
        etq = lambda i: f"{F[i]['ruta'][1].strip()} ({F[i]['ruta'][0].strip()})" if len(F[i]["ruta"]) == 2 else F[i]["ruta"][0].strip()
        plan.hechos.append(f"Renglones con más «{col}» en la tabla {tid}: " + "; ".join(f"{etq(i)} {fmt(v)}" for i, v in top) + ".")
        if len(top) >= 2 and plan.grafica({"tipo": "comparar_anio", "ids": [f"{tid}.f{i}.c{c}" for i, _ in top], "titulo": f"{col} · {T['titulo']} {a}"}):
            plan.hechos.append("Se muestra una gráfica de barras con " + ("los espacios." if len(F[top[0][0]]["ruta"]) == 2 else "los renglones de la tabla."))
    if not plan.hechos:
        return False
    plan.paso(f"Resumió la tabla {tid} «{T['titulos'][a]}»")
    return True

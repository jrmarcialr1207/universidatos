"""Lee tablas anuales de la Agenda Estadística UAEMEX (secciones Personal y Docencia/Académica) y las une en un JSON.

Uso: python tablas_a_json.py salida.json carpeta_anio1 [carpeta_anio2 ...]
Cada carpeta debe llamarse con el año (p. ej. 2025/) y contener Personal01.xlsx ... PersonalNN.xlsx.

Diseño:
- Una tabla = un número de cuadro dentro de la sección (Personal 03 = «Personal académico»).
- Filas y columnas se identifican por su ruta (p. ej. «Facultad › Ingeniería» y
  «Profesoras / es › Tiempo completo › Hombres»), así la misma celda se une entre años.
- Las celdas vacías dentro de una fila con datos se toman como 0 (así se leen en la Agenda).
"""
import json
import re
import sys
import unicodedata
from pathlib import Path

import openpyxl

SECCIONES = {"Personal": "P", "Acad": "A", "Ciencia": "C", "Ext": "E", "IdentiyCul": "D", "Ges": "G", "Interna": "I", "Pres": "R", "Cob": "M", "OA": "O", "CU": "U", "UAP": "V", "ICI": "N", "PEP": "B",
             "Doc": "A", "Inv": "C", "Int": "I", "Dif": "D", "Per": "P",
             "DOC": "A", "INV": "C", "COOP": "I", "DIFCUL": "D", "EXT": "E", "PER": "P", "GES": "G", "IyC": "N", "Coo": "I", "Pep": "B"}  # nombres de archivo de Agendas anteriores
NOMBRE_SECCION = {"Personal": "Personal", "Acad": "Docencia", "Ciencia": "Ciencia", "Ext": "Extensión", "IdentiyCul": "Difusión", "Ges": "Gestión", "Interna": "Internacionalización", "Pres": "Presencia", "Cob": "Cobertura", "OA": "Fichas por espacio", "CU": "Fichas por espacio", "UAP": "Fichas por espacio", "ICI": "Fichas por espacio", "PEP": "Fichas por espacio",
                  "Doc": "Docencia", "Inv": "Ciencia", "Int": "Internacionalización", "Dif": "Difusión", "Per": "Personal",
                  "DOC": "Docencia", "INV": "Ciencia", "COOP": "Internacionalización", "DIFCUL": "Difusión", "EXT": "Extensión",
                  "PER": "Personal", "GES": "Gestión", "IyC": "Fichas por espacio",
                  "Coo": "Internacionalización", "Pep": "Fichas por espacio"}
SEXO = {"H": "Hombres", "M": "Mujeres", "T": "Total"}


def limpia(t):
    t = re.sub(r"\s+", " ", str(t)).strip()
    return t


def clave(t):
    t = unicodedata.normalize("NFD", t)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"[^a-z0-9%]+", " ", t).strip()


def etiqueta_columna(t):
    t = limpia(t)
    t = re.sub(r"\s+\d$", "", t)          # número de nota al pie: «Participaciones 1»
    t = t.rstrip("*").strip()
    return SEXO.get(t, t)


def valor_combinado(ws, r, c, mapa):
    v = ws.cell(r, c).value
    if v is None and (r, c) in mapa:
        v = ws.cell(*mapa[(r, c)]).value
    return v


def es_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


GRUPO_ESP = re.compile(r"^(facultad(es)?|escuelas?|plantel(es)? de la escuela preparatoria|centros? universitarios?( uaem)?|"
                       r"unidad(es)? academicas? profesional(es)?|instituto|institutos?( y centros?)? de investigacion|"
                       r"instituto y centro de investigacion|dependencias? de administracion central|total)$")
NUM_TXT = re.compile(r"^-?\d+(\.\d+)?$")
NA_TXT = re.compile(r"^(n\.?\s?a\.?|n/a|n\.?\s?d\.?|s/d|-+|–|—|#(ref|div/0|n/a|value|name|null|num)!?)$", re.I)
NOTA = re.compile(r"^(fuente|nota|notas)\b|^\d+\s+\S|^\*|^[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ0-9\-]{1,14}:\s", re.I)
NO_SUMA = re.compile(r"promedio|puntaje|porcentaje|porcentual|%|indice|índice|eficiencia|tasa|por alumn|por tutor|por computadora|por cada", re.I)


def texto_celda(v):
    if v is None:
        return ""
    if es_num(v):
        return str(int(v)) if float(v).is_integer() else str(round(v, 4))
    return limpia(str(v).replace("\xa0", " "))


def numero_de(v):
    """Número si la celda es numérica (o texto con sólo un número); None si no."""
    if es_num(v):
        return float(v)
    s = texto_celda(v)
    if s and re.match(r"^-?\d{1,3}([ ,]\d{3})+(\.\d+)?$", s):  # «10 775» o «10,775»
        s = re.sub(r"[ ,]", "", s)
    return float(s) if s and NUM_TXT.match(s) else None


def lee_tabla(path):
    numero = int(re.search(r"(\d+)$", path.stem).group(1))
    wb = openpyxl.load_workbook(path, data_only=True)  # valores ya calculados, no fórmulas
    # algunos archivos traen primero una hoja sobrante de otra tabla: se elige la que empieza con el número
    # si ninguna hoja empieza con el número, la hoja activa (en Agendas anteriores la primera suele ser una sobrante)
    ws = next((h for h in wb.worksheets if re.match(rf"^\s*{numero}(\D|$)", h.title)), wb.active or wb.worksheets[0])
    mapa = {}
    for m in ws.merged_cells.ranges:
        for r in range(m.min_row, m.max_row + 1):
            for c in range(m.min_col, m.max_col + 1):
                if (r, c) != (m.min_row, m.min_col):
                    mapa[(r, c)] = (m.min_row, m.min_col)

    # número del cuadro: en los primeros renglones (un «1» de índice dentro de la tabla, más abajo, no cuenta)
    fila_num = next((r for r in range(1, 8) if str(ws.cell(r, 1).value or "").strip() in (str(numero), f"{numero}.0")
                     and all(not texto_celda(ws.cell(r, c).value) for c in range(2, 8))), None)  # solo el número en su renglón
    if fila_num is not None:
        fila_tit = fila_num + 1
        while fila_tit < fila_num + 4 and not texto_celda(ws.cell(fila_tit, 1).value):  # renglón vacío entre número y título
            fila_tit += 1
    else:  # sin número de cuadro: el título es el primer texto que no es instrucción interna
        fila_tit = next(r for r in range(1, 12) if isinstance(ws.cell(r, 1).value, str) and ws.cell(r, 1).value.strip()
                        and not re.match(r"(actualizar|incluir notas|base de datos|verificar|total\s*[<=>]|\d+\s+\d+\s+\w+_ae\b|direcci[oó]n de )", ws.cell(r, 1).value.strip(), re.I))
    titulo = limpia(ws.cell(fila_tit, 1).value)

    vacia = lambda v: v is None or not texto_celda(v)
    # encabezados: primera fila con contenido tras el título y las siguientes con A vacía y sin números
    r = fila_tit + 1
    while mapa.get((r, 1), (0, 0))[0] == fila_tit:  # título combinado en varios renglones
        r += 1
    # (una celda combinada que viene de renglones de arriba, p. ej. una nota al margen, no cuenta como contenido)
    # si el título está combinado, solo cuentan las columnas bajo el título (a la derecha suele haber bloques de validación)
    m_tit = next((m for m in ws.merged_cells.ranges if m.min_row == fila_tit and m.min_col == 1 and m.max_col > 2), None)
    ancho_busca = m_tit.max_col if m_tit else min(ws.max_column, 60)
    while r <= ws.max_row and all(vacia(valor_combinado(ws, r, c, mapa)) or mapa.get((r, c), (r, 0))[0] < r
                                  for c in range(1, ancho_busca + 1)):
        r += 1
    # subtítulo: renglón siguiente con texto solo en A, seguido de otro renglón con varias columnas (el encabezado)
    if r == fila_tit + 1 and isinstance(ws.cell(r, 1).value, str) and all(vacia(ws.cell(r, c).value) for c in range(2, min(ws.max_column, 60) + 1)):
        r2 = r + 1
        while r2 <= ws.max_row and all(vacia(ws.cell(r2, c).value) for c in range(1, min(ws.max_column, 60) + 1)):
            r2 += 1
        if r2 <= ws.max_row and sum(1 for c in range(2, min(ws.max_column, 60) + 1) if not vacia(valor_combinado(ws, r2, c, mapa))) >= 1 \
                and not NOTA.match(texto_celda(ws.cell(r, 1).value)):
            sub = limpia(ws.cell(r, 1).value)
            titulo = f"{titulo} {sub}" if sub.startswith("(") else f"{titulo}: {sub}"
            r = r2
    filas_enc = [r]
    # límite de la tabla: hasta 3 columnas vacías seguidas en la primera fila de encabezado
    # (algunas hojas traen a la derecha un bloque aparte con números que no es parte de la tabla)
    limite, vacias_seg = 1, 0
    for c in range(2, min(ws.max_column, 60) + 1):
        if vacia(valor_combinado(ws, r, c, mapa)):
            vacias_seg += 1
            if vacias_seg >= 3:
                break
        else:
            limite, vacias_seg = c, 0
    if limite == 1:
        limite = min(ws.max_column, 60)
    r += 1
    while r <= ws.max_row:
        fila = [ws.cell(r, c).value for c in range(1, limite + 1)]
        if all(vacia(v) for v in fila):
            r += 1
            continue
        if vacia(fila[0]) and not any(es_num(v) for v in fila[1:]) and len(filas_enc) < 4:
            filas_enc.append(r)
            r += 1
            continue
        break
    fila_dat = r
    # ancho: encabezados contiguos desde B
    ancho = 1
    for c in range(2, limite + 1):
        if any(not vacia(valor_combinado(ws, rr, c, mapa)) for rr in filas_enc):
            ancho = c
        else:
            break

    # filas de datos hasta las notas
    datos_r = []
    rr = fila_dat
    while rr <= ws.max_row:
        fila = [ws.cell(rr, c).value for c in range(1, ancho + 1)]
        if all(vacia(v) for v in fila):
            rr += 1
            continue
        a = texto_celda(fila[0])
        solo_a = all(vacia(v) for v in fila[1:])
        if solo_a and (NOTA.match(a) or len(a) > 45):
            # un encabezado de grupo largo (p. ej. «Dirección de …») va seguido de un renglón con datos
            sig = rr + 1
            while sig <= ws.max_row and all(vacia(ws.cell(sig, c).value) for c in range(1, ancho + 1)):
                sig += 1
            grupo = (not NOTA.match(a) and len(a) <= 130 and not a.endswith(".") and sig <= ws.max_row and sig - rr == 1
                     and sum(1 for c in range(2, ancho + 1) if not vacia(ws.cell(sig, c).value)) >= 2)
            if not grupo:
                break
        datos_r.append(rr)
        rr += 1
        if re.match(r"^total$", a, re.I) and int(ws.cell(rr - 1, 1).alignment.indent or 0) == 0:
            break  # el renglón «Total» cierra la tabla; lo que sigue suele ser otra tabla auxiliar
    fin_datos = rr

    def etiquetas_col(c):
        ruta = []
        for h in filas_enc:
            v = valor_combinado(ws, h, c, mapa)
            if vacia(v):
                continue
            e = etiqueta_columna(texto_celda(v))
            if not ruta or ruta[-1] != e:
                ruta.append(e)
        return ruta

    # tipo de cada columna
    n_num, n_txt = {}, {}
    for c in range(1, ancho + 1):
        n_num[c] = sum(1 for r in datos_r if numero_de(ws.cell(r, c).value) is not None)
        n_txt[c] = sum(1 for r in datos_r if not vacia(ws.cell(r, c).value) and numero_de(ws.cell(r, c).value) is None
                       and not NA_TXT.match(texto_celda(ws.cell(r, c).value)))  # «NA», «ND», «-», «#REF!» no hacen texto la columna
    a_indice = n_num[1] > n_txt[1] and ancho >= 2 and n_txt.get(2, 0) > n_num.get(2, 0)  # columna «No.» con B como nombre
    col_etq = 2 if a_indice else 1
    texto_cols = [c for c in range(col_etq + 1, ancho + 1) if n_txt[c] > n_num[c] and n_txt[c] >= 1]
    num_cols = [c for c in range(col_etq + 1, ancho + 1) if n_num[c] >= 1 and n_num[c] >= n_txt[c]]
    lider = []
    for c in range(col_etq + 1, ancho + 1):
        if c in texto_cols:
            lider.append(c)
        else:
            break
    otros_txt = [c for c in texto_cols if c not in lider]
    a_vacia = sum(1 for r in datos_r if vacia(ws.cell(r, col_etq).value) and not (a_indice and not vacia(ws.cell(r, 1).value)))
    # A como grupo: la columna A trae el grupo solo en su primer renglón (p. ej. la DES) y B el nombre en todos
    b_llena = bool(lider) and datos_r and sum(1 for r in datos_r if not vacia(ws.cell(r, lider[0]).value)) >= 0.8 * len(datos_r)
    a_grupo = bool(num_cols) and not otros_txt and not a_indice and len(lider) == 1 and b_llena and datos_r and a_vacia / len(datos_r) > 0.3
    # columnas numéricas que solo son años o fechas (año de creación, de inauguración…): la tabla es una lista
    solo_anios = bool(num_cols) and all(re.search(r"\baño de\b|\bfecha\b", " ".join(etiquetas_col(c)), re.I) for c in num_cols)
    es_lista = not num_cols or solo_anios or otros_txt or (datos_r and a_vacia / len(datos_r) > 0.3 and not a_grupo)

    notas, fuente = [], ""
    for r2 in range(fin_datos, ws.max_row + 1):
        v = ws.cell(r2, 1).value
        if vacia(v):
            continue
        tx = texto_celda(v)
        if tx.lower().startswith("fuente"):
            fuente = tx
            break
        notas.append(tx)
    base = {"numero": numero, "titulo": titulo, "notas": notas, "fuente": fuente, "hoja": ws.title}

    # bloques: renglón sin sangría que no es grupo y al que le sigue un grupo (p. ej. «PTC» y «No PTC», cada uno con sus facultades)
    desplaza = {}
    filas_a = [r for r in datos_r if not vacia(ws.cell(r, col_etq).value)]
    es_grupo = lambda r: bool(GRUPO_ESP.match(clave(texto_celda(ws.cell(r, col_etq).value))))
    es_total = lambda r: clave(texto_celda(ws.cell(r, col_etq).value)) == "total"
    bloques = {r for k, r in enumerate(filas_a[:-1]) if int(ws.cell(r, col_etq).alignment.indent or 0) == 0
               and not es_grupo(r) and es_grupo(filas_a[k + 1]) and not es_total(filas_a[k + 1])}
    nombres_grupo = [clave(texto_celda(ws.cell(r, col_etq).value)) for r in filas_a if es_grupo(r) and not es_total(r)]
    def sangria(r):
        v = ws.cell(r, col_etq).value
        return int(ws.cell(r, col_etq).alignment.indent or 0) + ((len(v) - len(v.lstrip(" "))) // 2 if isinstance(v, str) else 0)
    # también hay bloque si el propio Excel sangra los grupos que le siguen (p. ej. «Bachillerato» › «Plantel…» › planteles)
    bloques_sangria = {r for k, r in enumerate(filas_a[:-1]) if r in bloques and sangria(filas_a[k + 1]) >= 1}
    por_sangria = len(nombres_grupo) == len(set(nombres_grupo))
    if por_sangria:
        bloques = bloques_sangria  # sin grupos repetidos, solo cuentan los bloques con grupos sangrados
    if bloques:
        dentro = False
        for r in filas_a:
            if r in bloques:
                dentro = True
            elif es_total(r):
                dentro = False
            elif dentro:
                k = clave(texto_celda(ws.cell(r, col_etq).value))
                if por_sangria and es_grupo(r) and k.startswith("dependencia") and sangria(r) == 0:
                    dentro = False  # las dependencias no pertenecen a un nivel educativo
                elif por_sangria and not es_grupo(r) and sangria(r) == 0:
                    dentro = False  # renglón principal que no es grupo (p. ej. «Otros espacios»)
                else:
                    desplaza[r] = 1

    # modo «según sangría»: el Excel sangra los grupos (Bachillerato › Plantel › planteles); se respeta su jerarquía
    modo_sangria = (any(es_grupo(r) and sangria(r) >= 1 for r in filas_a)
                    and any(not es_grupo(r) and not es_total(r) and sangria(r) == 0 and sangria(filas_a[k + 1]) >= 1
                            for k, r in enumerate(filas_a[:-1])))
    nivel_sangria = {}
    if modo_sangria:
        dentro = False
        for r in filas_a:
            k = clave(texto_celda(ws.cell(r, col_etq).value))
            if es_total(r):
                nivel_sangria[r], dentro = 0, False
            elif es_grupo(r) and sangria(r) == 0:
                # grupo sin sangría dentro de un bloque (p. ej. una UAP bajo «Estudios profesionales»); las dependencias quedan afuera
                nivel_sangria[r] = 1 if dentro and not k.startswith("dependencia") else 0
            else:
                v = ws.cell(r, col_etq).value
                solo_espacios = isinstance(v, str) and len(v) - len(v.lstrip(" ")) >= 2 and not (ws.cell(r, col_etq).alignment.indent or 0)
                previo = next((x for x in reversed(list(nivel_sangria)) if not es_grupo(x)), None)
                if es_grupo(r):  # un grupo queda justo debajo del renglón (no grupo) que lo contiene
                    padre = next((x for x in reversed(list(nivel_sangria)) if not es_grupo(x) and nivel_sangria[x] < sangria(r)), None)
                    nivel_sangria[r] = nivel_sangria[padre] + 1 if padre is not None else sangria(r)
                elif solo_espacios and previo is not None and nivel_sangria[previo] > 0 and not es_grupo(filas_a[filas_a.index(r) - 1]):
                    nivel_sangria[r] = nivel_sangria[previo]  # sangría hecha con espacios: hermano del renglón anterior
                else:
                    nivel_sangria[r] = sangria(r)
                if sangria(r) == 0:
                    dentro = True

    def nivel_de(r):
        if modo_sangria:
            return nivel_sangria.get(r, sangria(r))
        return nivel_base(r) + desplaza.get(r, 0)

    # si todos los renglones (salvo el total) traen la misma sangría mínima, esa sangría no indica jerarquía
    sangria_min = min((int(ws.cell(r, col_etq).alignment.indent or 0) for r in filas_a if not es_total(r)), default=0)

    def nivel_base(r):
        v = ws.cell(r, col_etq).value
        if GRUPO_ESP.match(clave(texto_celda(v))):
            return 0  # los nombres de grupo (Facultad, Plantel, Centro universitario…) siempre son grupo principal
        n = int(ws.cell(r, col_etq).alignment.indent or 0) - sangria_min
        if isinstance(v, str) and len(v) - len(v.lstrip(" ")) >= 2:
            n += max(1, (len(v) - len(v.lstrip(" "))) // 3)  # sangrado con espacios (solo o además de la sangría de formato)
        if a_indice:
            n = 1 if not vacia(ws.cell(r, 1).value) and numero_de(ws.cell(r, 1).value) is not None else 0
        return n

    if es_lista:
        cols = [c for c in range(1, ancho + 1) if n_num[c] + n_txt[c] > 0]
        enc = [" › ".join(etiquetas_col(c)) or f"Columna {openpyxl.utils.get_column_letter(c)}" for c in cols]
        # columnas tipo categoría (pocos valores distintos, mayoría vacías): se rellenan hacia abajo
        rellenar = set()
        for c in (cols[1:] if not path.stem.startswith("Pres") else []):  # en los directorios, vacío es vacío
            vals = [texto_celda(ws.cell(r, c).value) for r in datos_r]
            llenos = [v for v in vals if v]
            if llenos and len(set(llenos)) <= 3 and len(llenos) <= len(vals) / 2:
                rellenar.add(c)
        renglones, pila, previo = [], [], {}
        for r in datos_r:
            fila = []
            for c in cols:
                # celdas combinadas (un domicilio para varios renglones): solo en los directorios de Presencia
                v = texto_celda(valor_combinado(ws, r, c, mapa) if c != cols[0] and path.stem.startswith("Pres") else ws.cell(r, c).value)
                if c == cols[0]:
                    if v:
                        n = nivel_de(r)
                        while pila and pila[-1][0] >= n:
                            pila.pop()
                        pila.append((n, v))
                    v = " › ".join(x[1] for x in pila)
                elif not v and c in rellenar:
                    v = previo.get(c, "")
                if v:
                    previo[c] = v
                fila.append(v)
            renglones.append(fila)
        return {**base, "tipo": "lista", "encabezados": enc, "renglones": renglones, "filas_excel": datos_r}

    columnas, idx_cols = [], []
    for c in num_cols:
        ruta = etiquetas_col(c)
        if not ruta:
            continue
        if len(ruta) == 1 and ruta[0] in ("Hombres", "Mujeres"):
            ruta = ["Total", ruta[0]]
        columnas.append(ruta)
        idx_cols.append(c)

    filas, datos, vacias_m, filas_excel = [], [], [], []
    pila, vistos, ultimo = [], {}, None
    grupo_act = None
    for r in datos_r:
        a = texto_celda(ws.cell(r, col_etq).value)
        extra = [texto_celda(ws.cell(r, c).value) for c in lider]
        extra = [e for e in extra if e]
        if a_grupo:
            if a:
                grupo_act = a
            if extra:
                ruta = ([grupo_act] if grupo_act else []) + [" · ".join(extra)]
            elif a:
                ruta = [a]
            else:
                continue
        elif not a and ultimo:
            # renglón de continuación (mismo espacio, otra modalidad o biblioteca): hermano del renglón anterior
            nivel, etq_previa = ultimo
            etiqueta = " · ".join([etq_previa] + extra) if extra else etq_previa
            while pila and pila[-1][0] >= nivel:
                pila.pop()
            ruta = [p[1] for p in pila] + [etiqueta]
            pila.append((nivel, etiqueta))
        elif not a:
            continue
        else:
            nivel = nivel_de(r)
            etiqueta = " · ".join([a] + extra)  # columnas de texto junto al nombre: parte de la etiqueta
            while pila and pila[-1][0] >= nivel:
                pila.pop()
            ruta = [p[1] for p in pila] + [etiqueta]
            pila.append((nivel, etiqueta))
            ultimo = (nivel, a)
        k = clave(" > ".join(ruta))
        if k in vistos:  # etiqueta repetida: se distingue en lugar de encimarla
            vistos[k] += 1
            ruta = ruta[:-1] + [f"{ruta[-1]} ({vistos[k]})"]
        else:
            vistos[k] = 1
        vals = [ws.cell(r, c).value for c in idx_cols]
        hay = any(numero_de(v) is not None for v in vals)
        filas.append({"ruta": ruta, "nivel": len(ruta) - 1})
        datos.append([numero_de(v) if numero_de(v) is not None else (0.0 if hay and vacia(v) else None) for v in vals])
        vacias_m.append([vacia(v) for v in vals])
        filas_excel.append(r)
    # en filas que agrupan a otras, una celda vacía es «sin dato», no 0
    con_hijos = [any(len(g["ruta"]) > len(f["ruta"]) and g["ruta"][:len(f["ruta"])] == f["ruta"] for g in filas[i + 1:])
                 for i, f in enumerate(filas)]
    for i in range(len(filas)):
        if con_hijos[i]:
            datos[i] = [None if vacias_m[i][j] else v for j, v in enumerate(datos[i])]
    # columna que viene vacía en todos los renglones de detalle: ahí tampoco es 0 (solo se reporta en los grupos)
    hojas = [i for i in range(len(filas)) if not con_hijos[i] and len(filas[i]["ruta"]) > 1]  # el renglón «Total» no cuenta
    for j in range(len(idx_cols)):
        otros = [i for i in range(len(filas)) if i not in hojas]
        if hojas and all(vacias_m[i][j] for i in hojas) and any(con_hijos) and any(datos[i][j] for i in otros):
            for i in hojas:
                datos[i][j] = None
    return {**base, "tipo": "numerica", "columnas": columnas, "filas": filas, "datos": datos, "filas_excel": filas_excel,
            "columnas_excel": [openpyxl.utils.get_column_letter(c) for c in idx_cols]}


# ---------------------------------------------------------------------------------------------
# Lectores especiales: fichas por espacio (OA, CU, UAP, ICI, PEP), Presencia 1 y Cobertura
# ---------------------------------------------------------------------------------------------
SECC_FICHA = re.compile(r"^(alumnado|investigaci|internacionali|difusi|extensi|personal|infraestructura|vinculaci|docencia|identidad|gesti)", re.I)
MARCAS = {"ü": "Sí", "sí": "Sí", "si": "Sí", "no": "No", "na": "NA", "n/a": "NA"}
FIN_FICHA = re.compile(r"^(nota|notas|fuente)\b|^\*|^[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ0-9\-]{1,14}:\s", re.I)


def _hoja(path):
    numero = int(re.search(r"(\d+)$", path.stem).group(1))
    wb = openpyxl.load_workbook(path, data_only=True)
    # si ninguna hoja empieza con el número, la hoja activa (en Agendas anteriores la primera suele ser una sobrante)
    ws = next((h for h in wb.worksheets if re.match(rf"^\s*{numero}(\D|$)", h.title)), wb.active or wb.worksheets[0])
    return numero, ws


def _celda_valor(v):
    """Texto del valor si la celda es un dato (número o marca Sí/No); None si es una etiqueta."""
    if v is None:
        return None
    n = numero_de(v)
    if n is not None:
        return str(int(n)) if float(n).is_integer() else str(round(n, 4))
    t = texto_celda(v)
    return MARCAS.get(t.lower()) if t else None


def lee_ficha(path):
    """Ficha de un espacio (tablero libre): se convierte en renglones «sección | concepto | valor»."""
    numero, ws = _hoja(path)
    ancho = min(ws.max_column, 40)
    fila_tit = next(r for r in range(1, 10) if isinstance(ws.cell(r, 1).value, str) and texto_celda(ws.cell(r, 1).value))
    titulo = limpia(ws.cell(fila_tit, 1).value)
    renglones, filas_excel, notas, fuente = [], [], [], ""
    seccion, enc, enc_bloque, bloque_col, pila = "General", {}, "", {}, []

    def agrega(concepto, valor, r):
        renglones.append([seccion, concepto, valor]); filas_excel.append(r)

    r = fila_tit + 1
    while r <= ws.max_row:
        celdas = {c: ws.cell(r, c).value for c in range(1, ancho + 1) if texto_celda(ws.cell(r, c).value)}
        r += 1
        if not celdas:
            continue
        rr = r - 1
        a = texto_celda(celdas.get(1)) if 1 in celdas else ""
        if a and FIN_FICHA.match(a) and len(celdas) == 1:
            # notas y fuente al final
            for r2 in range(rr, ws.max_row + 1):
                tx = texto_celda(ws.cell(r2, 1).value)
                if not tx:
                    continue
                if tx.lower().startswith("fuente"):
                    fuente = tx
                    break
                notas.append(tx)
            break
        valores = {c: _celda_valor(v) for c, v in celdas.items()}
        textos = {c: re.sub(r"(?<=[a-záéíóúñ])\d$", "", limpia(texto_celda(v))) for c, v in celdas.items() if valores[c] is None}  # «Bibliotecas1»: nota al pie
        datos = {c: x for c, x in valores.items() if x is not None}
        # año de fundación (y otros pares sueltos «etiqueta | valor de texto» en la cabecera)
        if any(re.match(r"año de fundaci", t, re.I) for t in textos.values()):
            cs = sorted(celdas)
            for i, c in enumerate(cs):
                if re.match(r"año de fundaci", texto_celda(celdas[c]), re.I) and i + 1 < len(cs):
                    renglones.append(["General", "Año de fundación", limpia(texto_celda(celdas[cs[i + 1]])) or ""]); filas_excel.append(rr)
            continue
        # sección
        if len(celdas) == 1 and a and SECC_FICHA.match(a) and int(ws.cell(rr, 1).alignment.indent or 0) == 0 and not datos:
            seccion, enc, enc_bloque, bloque_col, pila = a, {}, "", {}, []
            continue
        # encabezado: varios textos y ningún dato
        if not datos and len(textos) >= 2:
            cs = sorted(textos)
            # la etiqueta de la izquierda nombra el bloque si el renglón siguiente no trae dato debajo de ella
            sig = {c: _celda_valor(ws.cell(rr + 1, c).value) for c in cs}
            if sig.get(cs[0]) is None and cs[0] <= 2 and len(cs) >= 2 and not seccion.lower().startswith("infraestructura"):
                enc_bloque, enc = textos[cs[0]], {c: textos[c] for c in cs[1:]}
            else:
                enc_bloque, enc = "", {c: textos[c] for c in cs}
            pila = []
            continue
        if not datos:
            # renglón con un solo texto (p. ej. un programa sin datos o un nivel): solo actualiza la jerarquía
            if a and enc:
                niv = int(ws.cell(rr, 1).alignment.indent or 0)
                while pila and pila[-1][0] >= niv:
                    pila.pop()
                pila.append((niv, a))
            continue
        etiquetas_fila = [c for c in textos if c <= 2]
        otros_textos = [c for c in textos if c > 2]
        if enc and not otros_textos:
            # renglón de datos bajo un encabezado: la etiqueta del renglón (si hay) va con su jerarquía
            if etiquetas_fila:
                etq = textos[min(etiquetas_fila)]
                niv = int(ws.cell(rr, 1).alignment.indent or 0)
                while pila and pila[-1][0] >= niv:
                    pila.pop()
                ruta = [p[1] for p in pila] + [etq]
                pila.append((niv, etq))
            elif pila:
                ruta = [p[1] for p in pila]  # renglón sin nombre: pertenece al último nivel (p. ej. «Especialidad»)
            else:
                ruta = [enc_bloque] if enc_bloque else []
            for c, x in sorted(datos.items()):
                col = enc.get(c) or next((enc[k] for k in sorted(enc, reverse=True) if k < c and k + 2 >= c), None)
                if col is None:
                    col = "Valor"
                agrega(" › ".join(ruta + [col]), x, rr)
            if not etiquetas_fila:
                enc, enc_bloque = {}, ""  # encabezado de un solo renglón de datos: ya se usó
            continue
        # pares «etiqueta valor» en el mismo renglón
        enc = {}
        etiqueta_de = {}
        for c in sorted(datos):
            izq = [k for k in textos if k < c]
            if izq:
                etiqueta_de[c] = max(izq)
        usados = set(etiqueta_de.values())
        for c, x in sorted(datos.items()):
            l1 = etiqueta_de.get(c)
            if l1 is None:
                agrega("Valor", x, rr)
                continue
            libres = [k for k in textos if k < l1 and k not in usados]
            if libres:
                bloque_col[l1] = textos[max(libres)]
            bloque = bloque_col.get(l1, "")
            if not libres and not any(k < l1 for k in textos):
                bloque = bloque_col.get(l1, "")
            agrega(" › ".join(([bloque] if bloque and bloque != textos[l1] else []) + [textos[l1]]), x, rr)
        # los textos sin dato al final del renglón (p. ej. «Auditorios» vacío) se dejan
    enc_cols = ["Sección", "Concepto", "Valor"]
    base = {"numero": numero, "titulo": titulo, "notas": notas, "fuente": fuente, "hoja": ws.title}
    return {**base, "tipo": "lista", "encabezados": enc_cols, "renglones": renglones, "filas_excel": filas_excel}


def lee_presencia_municipios(path):
    """Presencia 1: lista de municipios › espacios que continúa de la columna A a la C."""
    numero, ws = _hoja(path)
    secuencia = []
    for col in (1, 3):
        for r in range(1, ws.max_row + 1):
            v = texto_celda(ws.cell(r, col).value)
            if not v or v.lower().startswith("fuente"):
                continue
            secuencia.append((int(ws.cell(r, col).alignment.indent or 0), limpia(v), r))
    fuente = next((texto_celda(ws.cell(r, 1).value) for r in range(1, ws.max_row + 1)
                   if texto_celda(ws.cell(r, 1).value).lower().startswith("fuente")), "")
    pila, renglones, filas_excel = [], [], []
    minimo = min(n for n, _, _ in secuencia)
    for n, v, r in secuencia:
        while pila and pila[-1][0] >= n:
            pila.pop()
        pila.append((n, v))
        if n > minimo:  # solo los espacios (los municipios son el grupo)
            renglones.append([pila[0][1], " › ".join(x[1] for x in pila[1:])])
            filas_excel.append(r)
    base = {"numero": numero, "titulo": "Presencia de la UAEMEX por municipio 2025", "notas": [], "fuente": fuente, "hoja": ws.title}
    return {**base, "tipo": "lista", "encabezados": ["Municipio", "Espacio universitario"], "renglones": renglones, "filas_excel": filas_excel}


def lee_cobertura(path):
    """Cobertura: bloques por nivel en las columnas G (concepto), H (personas) e I (porcentaje)."""
    numero, ws = _hoja(path)
    filas, datos, filas_excel, nivel = [], [], [], None
    for r in range(1, ws.max_row + 1):
        g, h, i = ws.cell(r, 7).value, ws.cell(r, 8).value, ws.cell(r, 9).value
        tg = limpia(texto_celda(g)) if g is not None else ""
        if not tg:
            continue
        if numero_de(h) is None:
            nivel = tg
            filas.append({"ruta": [nivel], "nivel": 0}); datos.append([None, None]); filas_excel.append(r)
            continue
        concepto = re.sub(r"^\**\s*\d?\s*", "", tg).strip()
        filas.append({"ruta": [nivel, concepto], "nivel": 1})
        datos.append([numero_de(h), numero_de(i)])
        filas_excel.append(r)
    notas, fuente = [], ""
    for r in range(1, ws.max_row + 1):
        tx = texto_celda(ws.cell(r, 1).value)
        if tx.lower().startswith("fuente") or re.match(r"^\d(,| y)", tx):
            fuente = (fuente + " " + tx).strip()
        elif tx:
            notas.append(tx)
    notas.append("Porcentaje: en la matrícula estatal y nacional es la tasa de cobertura (matrícula entre población del grupo de edad); "
                 "en la matrícula UAEMEX es su participación en la matrícula estatal del nivel.")
    base = {"numero": numero, "titulo": "Cobertura de la matrícula por nivel educativo 2025", "notas": notas, "fuente": fuente, "hoja": ws.title}
    return {**base, "tipo": "numerica", "columnas": [["Personas"], ["Porcentaje"]], "filas": filas, "datos": datos,
            "filas_excel": filas_excel, "columnas_excel": ["H", "I"]}


def clave_anios(t):
    """Clave para unir renglones y columnas entre años: sin ciclos ni años y sin formas incluyentes («Profesoras / es» = «Profesores»)."""
    t = re.sub(r"\b(19|20)\d{2}(\s*[-–/]\s*(19|20)?\d{2,4})?\b", " ", str(t))
    t = re.sub(r"\s*/\s*(os|as|es|a|o)\b", "", t, flags=re.I)
    t = re.sub(r"(?<=[a-záéíóúñ)])\s?\d$", "", t.strip())  # nota al pie al final («… Civil 2»)
    return " ".join(re.sub(r"(as|os|es|a|o|s)$", "", w) for w in clave(t).split())


LECTORES = {"OA": lee_ficha, "CU": lee_ficha, "UAP": lee_ficha, "ICI": lee_ficha, "IyC": lee_ficha, "PEP": lee_ficha, "Pep": lee_ficha, "Cob": lee_cobertura}


def no_sumables(T, anio):
    """Columnas que no se suman: por nombre (promedios, índices…) o porque los subtotales se comportan como promedio."""
    mat, filas = T["datos"][anio], T["filas"]
    out = set(i for i, c in enumerate(T["columnas"]) if NO_SUMA.search(" ".join(c)))
    hijos = {i: [j for j, g in enumerate(filas) if g["ruta"][:-1] == f["ruta"]] for i, f in enumerate(filas)}
    for c in range(len(T["columnas"])):
        suma = prom = 0
        for i, hs in hijos.items():
            p = mat.get(str(i), {}).get(str(c))
            vs = [mat[str(j)][str(c)] for j in hs if str(c) in mat.get(str(j), {})]
            if p is None or len(vs) < 2:
                continue
            if abs(sum(vs) - p) < 0.01:
                suma += 1
            elif min(vs) - 0.01 <= p <= max(vs) + 0.01:
                prom += 1
        if prom > suma:
            out.add(c)
    return sorted(out)


def titulo_sin_anio(t):
    t = re.sub(r"(?<![:\d])\b((a|en|al|de)\s+)?(19|20)\d{2}(\s*-\s*(19|20)\d{2})?\b", "", t)
    t = re.sub(r"\s+,", ",", re.sub(r"\s+", " ", t)).strip(" ,")
    return t


def main(salida, carpetas):
    tablas = {}
    # el año más reciente primero: sus títulos y etiquetas son los que se muestran
    carpetas = sorted(carpetas, key=lambda c: -int(re.search(r"(19|20)\d{2}", Path(c).name).group(0)))
    eq_path = Path(carpetas[0]).parent / "equivalencias.json"  # archivo de un año anterior -> id de la tabla actual
    equivalencias = json.loads(eq_path.read_text(encoding="utf-8")) if eq_path.exists() else {}
    ocupados = {v for e in equivalencias.values() for v in e.values()}  # ids asignados en cualquier año
    aparte = {}
    for carpeta in carpetas:
        carpeta = Path(carpeta)
        anio = int(re.search(r"(19|20)\d{2}", carpeta.name).group(0))
        eq = equivalencias.get(str(anio), {})
        for f in sorted(carpeta.glob("*.xlsx")):
            m = re.match(r"([A-Za-z]+)(\d+)$", f.stem)
            if not m or m.group(1) not in SECCIONES:
                continue
            try:
                lector = lee_presencia_municipios if f.stem == "Pres01" else LECTORES.get(m.group(1), lee_tabla)
                t = lector(f)
            except Exception as e:
                print(f"{anio} {f.stem}: NO SE PUDO LEER ({type(e).__name__}: {e})")
                continue
            tid = eq.get(f.stem) or f"{SECCIONES[m.group(1)]}{t['numero']:02d}"
            if tid in tablas and tablas[tid]["tipo"] != t["tipo"]:
                # la misma tabla con el otro tipo en varios años anteriores comparte un id aparte
                nuevo = aparte.get(tid)
                if nuevo is None or (nuevo in tablas and tablas[nuevo]["tipo"] != t["tipo"]):
                    nuevo = next(f"{tid[0]}{n}" for n in range(81, 100) if f"{tid[0]}{n}" not in tablas and f"{tid[0]}{n}" not in ocupados)
                    aparte[tid] = nuevo
                    ocupados.add(nuevo)
                print(f"{anio} {f.stem}: es {t['tipo']} y {tid} es {tablas[tid]['tipo']}; se guarda aparte como {nuevo}")
                tid = nuevo
            if t["tipo"] == "lista":
                T = tablas.setdefault(tid, {"id": tid, "tipo": "lista", "seccion": NOMBRE_SECCION.get(m.group(1), m.group(1)),
                                            "numero": t["numero"], "archivo": f.stem, "titulo": titulo_sin_anio(t["titulo"]),
                                            "titulos": {}, "encabezados": {}, "renglones": {}, "notas": {}, "fuente": {}, "excel": {}})
                T["titulos"][str(anio)] = t["titulo"]
                T.setdefault("archivos", {})[str(anio)] = f.stem
                T["encabezados"][str(anio)] = t["encabezados"]
                T["renglones"][str(anio)] = t["renglones"]
                T["notas"][str(anio)] = t["notas"]
                T["fuente"][str(anio)] = t["fuente"]
                T["excel"][str(anio)] = {"filas": t["filas_excel"]}
                print(f"{anio} {tid} {t['titulo'][:60]:60s} LISTA renglones={len(t['renglones']):3d} columnas={len(t['encabezados']):2d}")
                continue
            if not t["filas"] or not t["columnas"]:
                print(f"{anio} {f.stem}: sin filas o columnas numéricas")
                continue
            T = tablas.setdefault(tid, {"id": tid, "tipo": "numerica", "seccion": NOMBRE_SECCION.get(m.group(1), m.group(1)), "numero": t["numero"], "archivo": f.stem,
                                        "titulo": titulo_sin_anio(t["titulo"]), "titulos": {}, "filas": [], "columnas": [],
                                        "datos": {}, "notas": {}, "fuente": {}, "excel": {}})
            T["titulos"][str(anio)] = t["titulo"]
            T.setdefault("archivos", {})[str(anio)] = f.stem
            # unir filas y columnas por su ruta (sin años ni formas incluyentes); dentro de un mismo año nunca se juntan dos
            def une(items, existentes, texto):
                k_ex = {}
                for i, x in enumerate(existentes):
                    k_ex.setdefault(clave_anios(texto(x)), []).append(i)
                usados, mapa_ = set(), []
                for x in items:
                    k = clave_anios(texto(x))
                    # misma etiqueta sin años: se empareja por orden (p. ej. «Matrícula ciclo anterior» y «ciclo actual»)
                    i = next((j for j in k_ex.get(k, []) if j not in usados), None)
                    if i is None:
                        i = len(existentes); existentes.append(x)
                        k_ex.setdefault(k, []).append(i)
                    usados.add(i); mapa_.append(i)
                return mapa_
            mf = une(t["filas"], T["filas"], lambda x: " > ".join(x["ruta"]))
            mc = une(t["columnas"], T["columnas"], lambda x: " > ".join(x))
            # etiquetas propias de este año cuando difieren de las del año más reciente (p. ej. «egresadas 2023-2024»)
            difs = {str(j): x for j, x in zip(mc, t["columnas"]) if T["columnas"][j] != x}
            if difs:
                T.setdefault("columnas_anio", {})[str(anio)] = difs
            mat = {}
            for i, fila in enumerate(t["datos"]):
                for j, v in enumerate(fila):
                    if v is not None:
                        mat.setdefault(str(mf[i]), {})[str(mc[j])] = int(v) if float(v).is_integer() else round(v, 4)
            T["datos"][str(anio)] = mat
            T["notas"][str(anio)] = t["notas"]
            T["fuente"][str(anio)] = t["fuente"]
            T["excel"][str(anio)] = {"filas": {str(mf[i]): r for i, r in enumerate(t["filas_excel"])},
                                     "columnas": {str(mc[j]): c for j, c in enumerate(t["columnas_excel"])}}
            if str(anio) == max(T["datos"], key=int):
                T["no_sumables"] = no_sumables(T, str(anio))
            print(f"{anio} {tid} {t['titulo'][:60]:60s} filas={len(t['filas']):3d} columnas={len(t['columnas']):2d}")
    orden = "ACIDEGPMRONUVB"  # orden de la Agenda: Docencia, Ciencia, Internacionalización, Difusión, Extensión, Gestión, Personal…
    tablas = dict(sorted(tablas.items(), key=lambda kv: (orden.index(kv[0][0]) if kv[0][0] in orden else 99, kv[0])))
    Path(salida).write_text(json.dumps(tablas, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("tablas:", len(tablas), "· bytes:", Path(salida).stat().st_size)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])

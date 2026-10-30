"""Buscador por reglas: el mismo de la página (buscador.js), en Python para el servidor."""
import re
import unicodedata

VACIAS = set(["de", "la", "el", "en", "los", "las", "del", "y", "o", "a", "al", "un", "una", "unos", "unas", "cuantos", "cuantas", "cuanto", "cuanta", "cual", "cuales", "como", "ha", "han", "hay", "que", "por", "para", "con", "se", "su", "sus", "es", "son", "fue", "fueron", "era", "total", "numero", "cantidad", "dato", "datos", "universidad", "uaemex", "uaem", "tiene", "tenia", "tuvo", "hubo", "me", "dime", "muestra", "mostrar", "ver", "quiero", "saber", "sobre", "desde", "hasta", "entre", "ano", "anos", "año", "años", "ultimos", "ultimo", "periodo", "durante", "cada", "evolucion", "crecimiento", "crecido", "cambio", "cambiado", "comportamiento", "tendencia", "historico", "historia", "actual", "hoy", "ahora", "este", "esta", "escuela", "escuelas", "institucion", "instituciones", "general"])
SINONIMOS = {
 "licenciatura": [
  "estudios profesionales",
  "licenciatura"
 ],
 "licenciaturas": [
  "estudios profesionales",
  "licenciatura"
 ],
 "carrera": [
  "estudios profesionales"
 ],
 "carreras": [
  "estudios profesionales"
 ],
 "superior": [
  "estudios profesionales"
 ],
 "profesional": [
  "estudios profesionales"
 ],
 "profesionales": [
  "estudios profesionales"
 ],
 "posgrado": [
  "estudios avanzados"
 ],
 "posgrados": [
  "estudios avanzados"
 ],
 "avanzados": [
  "estudios avanzados"
 ],
 "prepa": [
  "bachillerato"
 ],
 "preparatoria": [
  "bachillerato"
 ],
 "preparatorias": [
  "bachillerato"
 ],
 "bachilleratos": [
  "bachillerato"
 ],
 "alumnos": [
  "matricula",
  "alumnado"
 ],
 "alumnas": [
  "matricula",
  "alumnado"
 ],
 "estudiantes": [
  "matricula",
  "alumnado"
 ],
 "inscritos": [
  "matricula"
 ],
 "alumnado": [
  "matricula",
  "alumnado"
 ],
 "matriculados": [
  "matricula"
 ],
 "profesores": [
  "personal academico",
  "ptc"
 ],
 "profesoras": [
  "personal academico",
  "ptc"
 ],
 "docentes": [
  "personal academico",
  "ptc"
 ],
 "maestros": [
  "personal academico",
  "ptc"
 ],
 "academicos": [
  "personal academico"
 ],
 "ptc": [
  "ptc"
 ],
 "tiempo completo": [
  "tiempo completo",
  "ptc"
 ],
 "sni": [
  "snii"
 ],
 "snii": [
  "snii"
 ],
 "sistema": [
  "snii"
 ],
 "investigadores": [
  "investigadoras",
  "snii"
 ],
 "investigadoras": [
  "investigadoras"
 ],
 "investigacion": [
  "proyectos de investigacion"
 ],
 "proyectos": [
  "proyectos"
 ],
 "doctores": [
  "doctorado"
 ],
 "doctorados": [
  "doctorado"
 ],
 "maestrias": [
  "maestria"
 ],
 "especialidades": [
  "especialidad"
 ],
 "titulados": [
  "titulacion",
  "tituladas"
 ],
 "titulacion": [
  "titulacion",
  "tituladas"
 ],
 "tituladas": [
  "tituladas"
 ],
 "egresados": [
  "egreso",
  "egresadas"
 ],
 "egresadas": [
  "egreso",
  "egresadas"
 ],
 "egreso": [
  "egreso"
 ],
 "graduados": [
  "graduadas",
  "graduacion"
 ],
 "eficiencia": [
  "eficiencia terminal"
 ],
 "terminal": [
  "eficiencia terminal"
 ],
 "abandono": [
  "abandono"
 ],
 "desercion": [
  "abandono"
 ],
 "reprobacion": [
  "reprobacion"
 ],
 "reprobados": [
  "reprobacion"
 ],
 "ingreso": [
  "ingreso"
 ],
 "aspirantes": [
  "solicitudes de ingreso"
 ],
 "solicitudes": [
  "solicitudes de ingreso"
 ],
 "aceptacion": [
  "aceptacion"
 ],
 "aceptados": [
  "inscrito a 1er",
  "aceptacion"
 ],
 "nuevo": [
  "inscrito a 1er"
 ],
 "primer": [
  "inscrito a 1er"
 ],
 "becas": [
  "becado",
  "becas"
 ],
 "becados": [
  "becado"
 ],
 "becarios": [
  "becado"
 ],
 "movilidad": [
  "nacional",
  "internacional"
 ],
 "intercambio": [
  "internacional"
 ],
 "extranjero": [
  "internacional"
 ],
 "internacional": [
  "internacional"
 ],
 "presupuesto": [
  "recursos"
 ],
 "dinero": [
  "recursos"
 ],
 "recursos": [
  "recursos"
 ],
 "subsidio": [
  "subsidio"
 ],
 "ingresos": [
  "ingresos propios",
  "ingresos"
 ],
 "gasto": [
  "aplicacion de los recursos"
 ],
 "computadoras": [
  "computadoras"
 ],
 "equipos": [
  "computadoras"
 ],
 "personal": [
  "personal"
 ],
 "trabajadores": [
  "personal"
 ],
 "administrativos": [
  "personal administrativo"
 ],
 "convenios": [
  "convenios"
 ],
 "cultura": [
  "presentaciones artisticas",
  "cultural"
 ],
 "libros": [
  "libros",
  "volumenes"
 ],
 "biblioteca": [
  "acervo bibliografico",
  "bibliotecas"
 ],
 "bibliotecas": [
  "bibliotecas"
 ],
 "acervo": [
  "acervo"
 ],
 "programas": [
  "programas educativos",
  "planes de estudio"
 ],
 "planes": [
  "planes de estudio"
 ],
 "calidad": [
  "calidad",
  "excelencia"
 ],
 "acreditados": [
  "acreditad"
 ],
 "excelencia": [
  "excelencia"
 ],
 "tutoria": [
  "tutoria"
 ],
 "tutores": [
  "tutoras"
 ],
 "deporte": [
  "deportivas"
 ],
 "deportes": [
  "deportivas"
 ],
 "incorporadas": [
  "incorporad"
 ],
 "incorporados": [
  "incorporad"
 ],
 "particulares": [
  "incorporad"
 ],
 "cuerpos": [
  "cuerpos academicos"
 ],
 "patentes": [
  "patentes"
 ],
 "revistas": [
  "revistas"
 ]
}
ESPECIFICOS = ["incorporad", "porcentaje", "%", "indice", "cohorte", "ciees", "copaes", "fomix", "pifop", "cifrhs", "pnpc", "sitaa", "tutoria", "excelencia", "calidad", "acreditad", "capacitad", "evaluables"]


def norm(s):
    s = unicodedata.normalize("NFD", str(s))
    s = "".join(c for c in s if not ("\u0300" <= c <= "\u036f")).lower()
    s = re.sub(r"[^a-z0-9%ñ\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def raiz_palabra(w):
    return re.sub(r"(es|s)$", "", w) if len(w) > 5 else w


def analizar(texto, anio_min=2004, anio_max=2025):
    n = norm(texto)
    anios = [int(a) for a in re.findall(r"\b(?:19|20)\d{2}\b", n) if 1990 <= int(a) <= 2100]
    desde = hasta = unico = None
    ult = re.search(r"ultimos? (\d{1,2}) anos?", n)
    if ult:
        hasta, desde = anio_max, max(anio_min, anio_max - int(ult.group(1)) + 1)
    elif len(anios) >= 2:
        desde, hasta = min(anios), max(anios)
    elif len(anios) == 1:
        if re.search(r"\bdesde\b|\ba partir\b", n):
            desde, hasta = anios[0], anio_max
        elif re.search(r"\bhasta\b", n):
            desde, hasta = anio_min, anios[0]
        else:
            unico = anios[0]
    pide_tasa = bool(re.search(r"porcentaje|%|indice|tasa|proporcion", n))
    resto = " " + re.sub(r"ultimos? \d{1,2} anos?", " ", re.sub(r"\b(?:19|20)\d{2}\b", " ", n), count=1) + " "
    grupos = []
    for k in SINONIMOS:
        if " " in k and f" {k} " in resto:
            grupos.append(SINONIMOS[k])
            resto = resto.replace(f" {k} ", " ", 1)
    for w in resto.split(" "):
        if not w or w in VACIAS or w.isdigit():
            continue
        if w in SINONIMOS:
            grupos.append(SINONIMOS[w])
        elif len(w) >= 3:
            grupos.append([raiz_palabra(w)])
    return {"grupos": grupos, "desde": desde, "hasta": hasta, "unico": unico, "pide_tasa": pide_tasa, "menciona": n}


class Buscador:
    def __init__(self, indicadores, series):
        self.lista = []
        for i in indicadores:
            if not series.get(i["id"]):
                continue
            partes = i["ruta"].split(" > ")
            self.lista.append({**i, "_hoja": " " + norm(partes[-1]) + " ",
                               "_padres": " " + norm(" ".join(partes[:-1])) + " ",
                               "_eje": " " + norm(i["eje"]) + " ", "_n": len(partes)})

    def buscar(self, texto, maximo=8):
        q = analizar(texto)
        if not q["grupos"]:
            return q, []
        res = []
        for i in self.lista:
            pts, cubiertos = 0.0, 0
            for g in q["grupos"]:
                mejor = 0.0
                for t in g:
                    if " " + t in i["_hoja"]:
                        mejor = max(mejor, 3)
                    elif " " + t in i["_padres"]:
                        mejor = max(mejor, 2)
                    elif " " + t in i["_eje"]:
                        mejor = max(mejor, 1.5)
                if mejor >= 1.5:
                    cubiertos += 1
                pts += mejor
            if pts < 2:
                continue
            if cubiertos == len(q["grupos"]):
                pts += 3
            texto_i = i["_hoja"] + i["_padres"]
            for e in ESPECIFICOS:
                if e in texto_i and ("porcentaje" if e == "%" else e) not in q["menciona"]:
                    pts -= 0 if (e in ("%", "porcentaje", "indice") and q["pide_tasa"]) else 1.5
            if q["pide_tasa"] and re.search(r"%|porcentaje|indice", texto_i):
                pts += 1.5
            if i["archivo"] == "His08" and "incorporad" not in q["menciona"] and "particular" not in q["menciona"]:
                pts -= 3
            pts -= (i["_n"] - 1) * 0.25
            if i["_padres"].strip() == "":
                pts += 0.5
            res.append((pts, i["id"]))
        res.sort(key=lambda x: -x[0])  # orden estable, igual que en la página
        return q, [{"id": id_, "pts": round(p, 2)} for p, id_ in res[:maximo]]

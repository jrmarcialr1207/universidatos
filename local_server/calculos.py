"""Herramientas que la IA puede pedir al servidor: buscar indicadores, leer valores y hacer cálculos.
Todas las cifras salen de series_uaemex.json; la IA nunca hace cuentas por su cuenta."""
import ast
import copy
import math
import operator
import re
import unicodedata

from buscador import Buscador
from buscador import norm as norm_b


class Calculos:
    def __init__(self, datos, tablas=None):
        self.tab = tablas or {}
        self.ind = {i["id"]: i for i in datos["indicadores"]}
        self.ser = {k: {int(a): float(v) for a, v in s.items()} for k, s in datos["series"].items()}
        self.anio_min = min(a for s in self.ser.values() for a in s)
        self.anio_max = max(a for s in self.ser.values() for a in s)
        self.buscador = Buscador(datos["indicadores"], datos["series"])

    # ------------------------------------------------------------ utilidades
    def nombre(self, id_):
        return self.ind[id_]["ruta"].replace(" > ", " › ")

    def sesion(self):
        """Copia ligera para una sola pregunta: las series calculadas (S1, S2…) no se mezclan entre personas."""
        s = copy.copy(self)
        s.ser, s.ind, s.calculadas, s.n_series = dict(self.ser), dict(self.ind), {}, 0
        return s

    def unidad(self, id_):
        dv = self.ind[id_].get("derivada")
        if dv:
            return "%" if dv["op"] in ("proporcion", "variacion_anual") else ("" if dv["op"] == "razon" else self.unidad(dv["ids"][0]))
        r = self.ind[id_]["ruta"].lower()
        if "millones de pesos" in r:
            return "millones de pesos"
        if "miles de pesos" in r:
            return "miles de pesos"
        if re.search(r"por alumn|por computadora|por tutor", r):
            return ""
        if re.search(r"%|porcentaje|índice|indice|eficiencia|tasa", r):
            return "%"
        return ""

    def asegurar_celda(self, id_):
        """Convierte una celda de tabla anual (p. ej. P02.f23.c3) en una serie por año."""
        m = re.match(r"^([A-Z]\d{2})\.f(\d+)\.c(\d+)$", str(id_))
        if not m or m.group(1) not in self.tab:
            return False
        T, f, c = self.tab[m.group(1)], int(m.group(2)), int(m.group(3))
        if T.get("tipo") == "lista" or f >= len(T["filas"]) or c >= len(T["columnas"]):
            return False
        vals = {int(a): float(mat[str(f)][str(c)]) for a, mat in T["datos"].items() if str(c) in mat.get(str(f), {})}
        if not vals:
            return False
        self.ser[id_] = vals
        self.ind[id_] = {"id": id_, "ruta": " > ".join([T["titulo"], *T["filas"][f]["ruta"], " › ".join(T["columnas"][c])]),
                         "eje": f"{T['seccion']} · tabla anual", "archivo": T["archivo"], "celda": {"t": T["id"], "f": f, "c": c}}
        return True

    def _id(self, id_):
        id_ = str(id_ or "").strip()
        if id_ not in self.ser:
            self.asegurar_celda(id_)
        if id_ not in self.ser:
            raise ValueError(f"No existe el indicador «{id_}». Usa buscar_indicadores para encontrar el id correcto.")
        return id_

    def _anio(self, v, defecto=None):
        if v in (None, ""):
            return defecto
        a = int(float(v))
        if not 1990 <= a <= 2100:
            raise ValueError(f"Año inválido: {v}")
        return a

    def _valor(self, id_, anio):
        s = self.ser[id_]
        if anio not in s:
            disp = sorted(s)
            raise ValueError(f"{self.nombre(id_)} no tiene dato en {anio}. Años disponibles: {disp[0]}–{disp[-1]}"
                             + (" (con huecos)" if len(disp) != disp[-1] - disp[0] + 1 else "") + ".")
        return s[anio]

    def _tramo(self, id_, desde, hasta):
        desde = self._anio(desde, self.anio_min)
        hasta = self._anio(hasta, self.anio_max)
        if desde > hasta:
            desde, hasta = hasta, desde
        sel = {a: v for a, v in sorted(self.ser[id_].items()) if desde <= a <= hasta}
        if not sel:
            raise ValueError(f"{self.nombre(id_)} no tiene datos entre {desde} y {hasta}.")
        return sel

    def _ultimo_comun(self, ids):
        comunes = set.intersection(*(set(self.ser[i]) for i in ids))
        if not comunes:
            raise ValueError("Esos indicadores no tienen ningún año en común.")
        return max(comunes)

    def f(self, x, d=2):
        v = self.r(x, d)
        return f"{v:,}" if isinstance(v, int) else f"{v:,.{d}f}".rstrip("0").rstrip(".")

    @staticmethod
    def r(x, d=2):
        return int(x) if float(x).is_integer() else round(x, d)

    # ------------------------------------------------------------ herramientas
    def buscar_indicadores(self, texto="", **_):
        _, res = self.buscador.buscar(str(texto), 15)
        if not res:
            raise ValueError(f"No encontré indicadores con «{texto}». Prueba con otras palabras clave.")
        encontrados = [{"id": r["id"], "indicador": self.nombre(r["id"]), "eje": self.ind[r["id"]]["eje"]} for r in res]
        return {"descripcion": f"Buscó indicadores con «{texto}» ({len(encontrados)} encontrados)",
                "resultados": encontrados}

    def obtener_valores(self, ids=None, desde=None, hasta=None, **_):
        if isinstance(ids, str):
            ids = [ids]
        ids = [self._id(i) for i in (ids or [])][:8]
        if not ids:
            raise ValueError("Indica al menos un id.")
        out = []
        for id_ in ids:
            sel = self._tramo(id_, desde, hasta)
            out.append({"id": id_, "indicador": self.nombre(id_), "unidad": self.unidad(id_),
                        "valores": {str(a): self.r(v) for a, v in sel.items()}})
        return {"descripcion": "Consultó valores de: " + "; ".join(o["indicador"] for o in out), "series": out}

    def calcular(self, operacion="", id=None, id2=None, ids=None, anio=None, desde=None, hasta=None,
                 expresion=None, **_):
        op = norm(operacion).replace(" ", "_")
        alias = {"variacion": "cambio", "tcma": "crecimiento_anual_promedio", "tasa_de_crecimiento": "crecimiento_anual_promedio",
                 "media": "promedio"}
        op = alias.get(op, op)
        if op not in OPERACIONES:
            raise ValueError(f"Operación desconocida «{operacion}». Usa una de: {', '.join(OPERACIONES)}.")
        if op == "expresion":
            v = evaluar(str(expresion or ""))
            return {"descripcion": f"Calculó {expresion} = {self.f(v, 4)}", "resultado": self.r(v, 4)}

        if op in ("suma",):
            lista = ids if isinstance(ids, list) else [i for i in (id, id2) if i]
            lista = [self._id(i) for i in lista]
            if len(lista) < 2:
                raise ValueError("Para sumar indica al menos dos ids en «ids».")
            a = self._anio(anio) or self._ultimo_comun(lista)
            partes = {self.nombre(i): self.r(self._valor(i, a)) for i in lista}
            total = sum(self._valor(i, a) for i in lista)
            return {"descripcion": f"Sumó {len(lista)} indicadores en {a} = {self.f(total)}",
                    "anio": a, "partes": partes, "resultado": self.r(total)}

        if op in ("proporcion", "razon", "diferencia"):
            a_id, b_id = self._id(id), self._id(id2)
            a = self._anio(anio) or self._ultimo_comun([a_id, b_id])
            va, vb = self._valor(a_id, a), self._valor(b_id, a)
            if op == "diferencia":
                res, txt = va - vb, "Diferencia"
            else:
                if vb == 0:
                    raise ValueError("El segundo indicador vale 0 ese año; no se puede dividir.")
                res = va / vb * (100 if op == "proporcion" else 1)
                txt = "Proporción (%)" if op == "proporcion" else "Razón"
            return {"descripcion": f"{txt} de {self.nombre(a_id)} entre {self.nombre(b_id)} en {a} = {self.f(res)}",
                    "anio": a, "valor_1": self.r(va), "valor_2": self.r(vb), "resultado": self.r(res),
                    **({"unidad": "%"} if op == "proporcion" else {})}

        id_ = self._id(id)
        sel = self._tramo(id_, desde, hasta)
        anios = sorted(sel)
        base = {"indicador": self.nombre(id_), "unidad": self.unidad(id_)}

        if op in ("valor",):
            a = self._anio(anio, anios[-1])
            v = self._valor(id_, a)
            return {**base, "descripcion": f"{self.nombre(id_)} en {a} = {self.f(v)}", "anio": a, "resultado": self.r(v)}

        if op in ("cambio", "variacion"):
            a1, a2 = anios[0], anios[-1]
            v1, v2 = sel[a1], sel[a2]
            res = {**base, "desde": a1, "valor_desde": self.r(v1), "hasta": a2, "valor_hasta": self.r(v2),
                   "cambio": self.r(v2 - v1)}
            if v1 and base["unidad"] != "%":
                res["cambio_porcentual"] = self.r((v2 - v1) / v1 * 100)
            res["descripcion"] = (f"Cambio de {self.nombre(id_)} de {a1} ({self.f(v1)}) a {a2} ({self.f(v2)}): {self.f(v2 - v1)}"
                                  + (f" ({self.f(res['cambio_porcentual'])}%)" if "cambio_porcentual" in res else
                                     " puntos" if base["unidad"] == "%" else ""))
            return res

        if op in ("crecimiento_anual_promedio", "tcma", "tasa_de_crecimiento"):
            a1, a2 = anios[0], anios[-1]
            v1, v2 = sel[a1], sel[a2]
            if a1 == a2:
                raise ValueError("Se necesitan al menos dos años distintos.")
            if v1 <= 0 or v2 <= 0:
                raise ValueError("El crecimiento compuesto requiere valores positivos en ambos años.")
            t = ((v2 / v1) ** (1 / (a2 - a1)) - 1) * 100
            return {**base, "descripcion": f"Crecimiento anual promedio de {self.nombre(id_)} {a1}–{a2} = {self.f(t)}% por año",
                    "desde": a1, "valor_desde": self.r(v1), "hasta": a2, "valor_hasta": self.r(v2),
                    "anios_transcurridos": a2 - a1, "resultado": self.r(t), "unidad_resultado": "% anual"}

        if op in ("promedio", "media"):
            m = sum(sel.values()) / len(sel)
            return {**base, "descripcion": f"Promedio de {self.nombre(id_)} {anios[0]}–{anios[-1]} ({len(sel)} años con dato) = {self.f(m)}",
                    "desde": anios[0], "hasta": anios[-1], "anios_con_dato": len(sel), "resultado": self.r(m)}

        if op in ("maximo", "minimo"):
            a = (max if op == "maximo" else min)(sel, key=sel.get)
            return {**base, "descripcion": f"{'Máximo' if op == 'maximo' else 'Mínimo'} de {self.nombre(id_)} {anios[0]}–{anios[-1]}: {self.f(sel[a])} en {a}",
                    "anio": a, "resultado": self.r(sel[a])}

        raise ValueError(f"Operación desconocida «{operacion}». Usa una de: {', '.join(OPERACIONES)}.")

    def _rank_tablas(self, texto):
        palabras = []
        # «por espacio académico» dice cómo agrupar, no de qué tema es la tabla
        for w in re.sub(r"\b(por |cada |en cada )?espacios?( (academicos?|universitarios?))?\b", " ", norm_b(texto)).split():
            if len(w) < 3 or w in VACIAS_T or w.isdigit():
                continue
            w = SIN_T.get(w, w)
            if " " not in w and len(w) > 7:
                w = w[:7]
            if w not in palabras:
                palabras.append(w)
        for k, vs in EQUIV_T.items():
            if k in palabras:
                palabras += [v for v in vs if v not in palabras]
        if not palabras:
            return []
        todas = list(self.tab.values())
        for T in todas:
            if "_n" not in T:
                if T.get("tipo") == "lista":
                    a = sorted(T["renglones"])[-1]
                    T["_n"] = (norm_b(T["titulo"] + " " + T["seccion"]), [norm_b(h) for h in T["encabezados"][a]],
                               [norm_b(" ".join(r)) for r in T["renglones"][a]])
                else:
                    # solo cuentan renglones y columnas con dato en el año más reciente (los de años anteriores quedan vacíos)
                    ult = T["datos"][max(T["datos"], key=int)] if T.get("datos") else {}
                    vivas = {int(i) for i in ult}
                    pref = {tuple(T["filas"][k]["ruta"][:n]) for k in vivas for n in range(1, len(T["filas"][k]["ruta"]) + 1)}
                    cols_v = {int(j) for r in ult.values() for j in r}
                    T["_n"] = (norm_b(T["titulo"] + " " + T["seccion"]),
                               [norm_b(" ".join(c)) if (j in cols_v or not cols_v) else "" for j, c in enumerate(T["columnas"])],
                               [norm_b(" ".join(f["ruta"])) if (not vivas or tuple(f["ruta"]) in pref) else "" for f in T["filas"]])
        pide_lista = bool(PIDE_LISTA.search(norm_b(texto)))
        ult_t = max(max(T["renglones"] if T.get("tipo") == "lista" else T.get("datos", {}) or [""]) for T in todas)
        peso = {w: 1 + math.log(len(todas) / (1 + sum(1 for T in todas if w in T["_n"][0]))) for w in palabras}
        res = []
        for T in todas:
            tit, cols, fils = T["_n"]
            pts, fc, cc = 0.0, [], []
            # un renglón que trae todo lo que se pregunta (p. ej. «Árboles plantados») pesa como una columna
            renglon = len(palabras) >= 2 and T.get("tipo") != "lista" and any(all(w in f for w in palabras) for f in fils)
            for w in palabras:
                en_c = [j for j, c in enumerate(cols) if w in c]
                en_f = [i for i, f in enumerate(fils) if w in f]
                pts += max(3 * peso[w] if w in tit else 0, 2 * min(peso[w], 5.5) if en_c or renglon else 0, 1 if en_f else 0)  # una vez, donde pese más
                cc += [j for j in en_c if j not in cc]
                fc += [i for i in en_f if i not in fc]
            if pts > 0 and any(tit.startswith(w) for w in palabras):
                pts += 2  # el título empieza con lo que se pregunta
            if pts > 0:  # desempate: a igual coincidencia, gana el título más general (menos palabras no preguntadas)
                extra = sum(1 for t in norm_b(T["titulo"]).split() if len(t) >= 4 and t not in VACIAS_T and not t.isdigit()
                            and not any(t[:7] in w or w in t for w in palabras))
                pts -= 0.01 * extra
            qn = norm_b(texto)
            pts -= 8 * sum(1 for s in SUBCONJ_T if s in tit and s not in qn)  # tablas de un subconjunto que no se pidió
            pide = [n for n in NIVEL_T if n[0].search(qn)]  # nivel educativo de la pregunta
            if pide and not any(n[1] in tit for n in pide) and any(n[1] in tit for n in NIVEL_T):
                pts -= 4
            elif not pide and "estudios avanzados" in tit:
                pts -= 0.5  # sin nivel en la pregunta: primero licenciatura o bachillerato, luego posgrado
            if T.get("seccion") == "Fichas por espacio" and not PIDE_FICHA.search(qn):
                pts -= 6  # fichas por espacio: resumen de otras tablas, solo arriba si se pide la ficha
            if T.get("tipo") == "lista" and not pide_lista and not all(w in tit for w in palabras):
                pts -= 3  # listas de texto: solo arriba si se pide una lista
            anios_t = list(T["renglones"] if T.get("tipo") == "lista" else T.get("datos", {}))
            if ult_t not in anios_t and not any(a in qn for a in anios_t):
                pts -= 3  # tablas que ya no se publican: abajo, salvo que se pida su año
            pts = round(pts * 1000) / 1000
            if pts > 0:
                res.append({"id": T["id"], "pts": pts, "filas": fc, "columnas": cc})
        return sorted(res, key=lambda x: -x["pts"])  # orden estable, igual que en la página

    def buscar_tablas(self, texto="", **_):
        res = self._rank_tablas(str(texto))[:5]
        if not res:
            raise ValueError(f"No encontré tablas con «{texto}». Tablas disponibles: "
                             + "; ".join(f"{T['id']} {T['titulo']}" for T in self.tab.values()))
        out = []
        for x in res:
            T = self.tab[x["id"]]
            if T.get("tipo") == "lista":
                a = sorted(T["renglones"])[-1]
                out.append({"tabla": T["id"], "tipo": "lista de texto", "titulo": T["titulo"], "anios": sorted(int(k) for k in T["renglones"]),
                            "renglones": len(T["renglones"][a]), "columnas": T["encabezados"][a], "renglones_que_coinciden": len(x["filas"])})
                continue
            grupos = [" › ".join(f["ruta"]) for f in T["filas"]
                      if any(len(g["ruta"]) > len(f["ruta"]) and g["ruta"][:len(f["ruta"])] == f["ruta"] for g in T["filas"])]
            out.append({"tabla": T["id"], "tipo": "numérica", "titulo": T["titulo"], "anios": sorted(int(a) for a in T["datos"]), "filas": len(T["filas"]),
                        "grupos": grupos[:15], "columnas": [{"c": j, "columna": " › ".join(c)} for j, c in enumerate(T["columnas"])][:40],
                        "filas_que_coinciden": [{"f": i, "fila": " › ".join(T["filas"][i]["ruta"])} for i in x["filas"][:10]]})
        return {"descripcion": f"Buscó tablas con «{texto}» ({len(out)} encontradas)", "tablas": out}

    def consultar_tabla(self, tabla="", grupo=None, filas=None, columnas=None, anio=None, **_):
        T = self.tab.get(str(tabla or "").strip().upper())
        if not T:
            raise ValueError(f"No existe la tabla «{tabla}». Usa buscar_tablas.")
        lista = lambda v: v if isinstance(v, list) else ([v] if v else [])
        if T.get("tipo") == "lista":
            anios = sorted(T["renglones"])
            a = str(self._anio(anio, int(anios[-1])))
            if a not in T["renglones"]:
                raise ValueError(f"La tabla {T['id']} no tiene datos de {a}. Años disponibles: {', '.join(anios)}.")
            enc = T["encabezados"][a]
            qs = [norm_b(x) for x in lista(filas) + lista(grupo) if norm_b(x)]
            rs = [r for r in T["renglones"][a] if all(q in norm_b(" ".join(r)) for q in qs)]
            total = len(rs)
            return {"descripcion": f"Consultó la lista {T['id']} «{T['titulos'][a]}»: {total} renglones", "tabla": T["id"],
                    "tipo": "lista de texto", "titulo": T["titulos"][a], "anio": int(a), "renglones_encontrados": total,
                    "renglones": [{h: (r[k] if k < len(r) else "") for k, h in enumerate(enc)} for r in rs[:150]],
                    "aviso": ("Se muestran los primeros 150; filtra con «filas» para ver otros. " if total > 150 else "")
                             + "Es una lista de texto: no se grafica. Cuenta renglones si necesitas cantidades.",
                    "notas": T["notas"].get(a, [])[:4], "fuente": T["fuente"].get(a, "")}
        anios = sorted(T["datos"])
        a = str(self._anio(anio, int(anios[-1])))
        if a not in T["datos"]:
            raise ValueError(f"La tabla {T['id']} no tiene datos de {a}. Años disponibles: {', '.join(anios)}.")
        mat = T["datos"][a]
        lista = lambda v: v if isinstance(v, list) else ([v] if v else [])
        fs = list(range(len(T["filas"])))
        if grupo:
            g = norm_b(grupo)
            fs = [i for i in fs if len(T["filas"][i]["ruta"]) > 1 and g in norm_b(T["filas"][i]["ruta"][-2])]
            if not fs:
                gr = list(dict.fromkeys(f["ruta"][-2] for f in T["filas"] if len(f["ruta"]) > 1))
                raise ValueError(f"No hay filas dentro del grupo «{grupo}». Grupos de la tabla: {'; '.join(gr)}")
        if filas:
            fl = [norm_b(x) for x in lista(filas)]
            fs = [i for i in fs if any(q in norm_b(" ".join(T["filas"][i]["ruta"])) for q in fl)]
            if not fs:
                raise ValueError(f"Ninguna fila coincide con {filas}.")
        cs = list(range(len(T["columnas"])))
        todas = "; ".join(" › ".join(c) for c in T["columnas"])
        if columnas:
            cl = [norm_b(x) for x in lista(columnas)]
            cs = [j for j in cs if any(q in norm_b(" ".join(T["columnas"][j])) for q in cl)]
            if not cs:
                raise ValueError(f"Ninguna columna coincide con {columnas}. Columnas: {todas}")
        if len(fs) * len(cs) > 240:
            raise ValueError(f"La consulta tiene {len(fs) * len(cs)} celdas; filtra con «grupo», «filas» o «columnas» (máximo 240). Columnas: {todas}")
        celdas = []
        for f in fs:
            for c in cs:
                v = mat.get(str(f), {}).get(str(c))
                if v is not None:
                    celdas.append({"id": f"{T['id']}.f{f}.c{c}", "fila": " › ".join(T["filas"][f]["ruta"]),
                                   "columna": " › ".join(T["columnas"][c]), "valor": v})
        ns = [" › ".join(T["columnas"][j]) for j in T.get("no_sumables", [])]
        return {"descripcion": f"Consultó la tabla {T['id']} «{T['titulos'][a]}»: {len(celdas)} celdas", "tabla": T["id"],
                "titulo": T["titulos"][a], "anio": int(a), "celdas": celdas, "notas": T["notas"].get(a, [])[:4],
                "fuente": T["fuente"].get(a, ""),
                "aviso": "Las celdas vacías en la tabla original se leen como 0." + (f" Estas columnas son promedios y no se suman: {'; '.join(ns)}." if ns else "")}

    def calcular_serie(self, operacion="", id=None, id2=None, ids=None, nombre="", **_):
        if not hasattr(self, "calculadas"):
            raise ValueError("Las series calculadas solo están disponibles dentro de una pregunta.")
        op = norm(operacion).replace(" ", "_")
        op = {"division": "razon", "dividir": "razon", "cociente": "razon", "entre": "razon", "porcentaje": "proporcion",
              "resta": "diferencia", "variacion": "variacion_anual", "crecimiento_anual": "variacion_anual"}.get(op, op)
        if op not in OPS_SERIE:
            raise ValueError(f"Operación desconocida «{operacion}». Usa una de: {', '.join(OPS_SERIE)}.")
        if op == "suma":
            ent = [self._id(i) for i in (ids if isinstance(ids, list) else [i for i in (id, id2) if i])]
            if len(ent) < 2:
                raise ValueError("Para sumar indica al menos dos ids en «ids».")
        elif op == "variacion_anual":
            ent = [self._id(id)]
        else:
            if not id or not id2:
                raise ValueError("Indica «id» (numerador o primer término) e «id2» (denominador o segundo término).")
            ent = [self._id(id), self._id(id2)]
        vals = {}
        if op == "variacion_anual":
            s = self.ser[ent[0]]
            for a in sorted(s):
                if a - 1 in s and s[a - 1] != 0:
                    vals[a] = round((s[a] - s[a - 1]) / s[a - 1] * 100, 4)
        else:
            comunes = sorted(set.intersection(*(set(self.ser[i]) for i in ent)))
            for a in comunes:
                v = [self.ser[i][a] for i in ent]
                if op == "suma":
                    vals[a] = round(sum(v), 4)
                elif op == "diferencia":
                    vals[a] = round(v[0] - v[1], 4)
                elif v[1] != 0:
                    vals[a] = round(v[0] / v[1] * (100 if op == "proporcion" else 1), 4)
        if not vals:
            raise ValueError("Esos indicadores no tienen años en común para calcular la serie.")
        simb = {"razon": "÷", "proporcion": "÷", "diferencia": "−", "suma": "+"}.get(op)
        if op == "variacion_anual":
            formula = f"variación anual de {self.nombre(ent[0])}"
        else:
            formula = f" {simb} ".join(self.nombre(i) for i in ent) + (" × 100" if op == "proporcion" else "")
        nm = str(nombre or "").strip()[:100] or (f"Variación anual de {self.nombre(ent[0])}" if op == "variacion_anual"
                                                  else f" {simb} ".join(self.nombre(i).split(" › ")[-1] for i in ent))
        if op in ("proporcion", "variacion_anual") and "%" not in nm:
            nm += " (%)"
        self.n_series += 1
        nid = f"S{self.n_series}"
        self.ser[nid] = vals
        self.ind[nid] = {"id": nid, "ruta": nm, "concepto": nm, "eje": "Serie calculada", "archivo": "calc", "fila_excel": "",
                         "derivada": {"op": op, "ids": ent, "formula": formula}}
        self.calculadas[nid] = {"nombre": nm, "op": op, "ids": ent, "formula": formula,
                                "valores": {str(a): v for a, v in vals.items()}}
        anios = sorted(vals)
        return {"id": nid, "descripcion": f"Creó la serie {nid}: {nm} = {formula} ({len(anios)} años, {anios[0]}–{anios[-1]})",
                "indicador": nm, "formula": formula, "unidad": self.unidad(nid),
                "valores": {str(a): self.r(v) for a, v in vals.items()}}

    def graficar(self, tipo="linea", ids=None, desde=None, hasta=None, anio=None, titulo="", **_):
        tipo = norm(tipo).replace(" ", "_")
        tipo = {"lineas": "linea", "barra": "barras", "columnas": "barras", "comparacion": "comparar_anio",
                "comparar": "comparar_anio", "barras_horizontales": "comparar_anio", "cambio": "cambio_anios",
                "cambio_anual": "cambio_anios", "diferencia": "cambio_anios"}.get(tipo, tipo)
        if tipo not in TIPOS_GRAFICA:
            raise ValueError(f"Tipo de gráfica desconocido «{tipo}». Usa: {', '.join(TIPOS_GRAFICA)}.")
        if isinstance(ids, str):
            ids = [ids]
        ids = list(dict.fromkeys(self._id(i) for i in (ids or [])))
        maximo = 30 if tipo == "comparar_anio" else 80 if tipo == "cambio_anios" else (2 if tipo == "barras" else 4)
        if not ids:
            raise ValueError("Indica al menos un id en «ids».")
        if len(ids) > maximo:
            raise ValueError(f"La gráfica «{tipo}» admite máximo {maximo} indicadores; haz otra gráfica para los demás.")
        if tipo == "comparar_anio" and len(ids) < 2:
            raise ValueError("Para comparar en un año indica al menos 2 indicadores.")
        unidades = {self.unidad(i) for i in ids}
        if len(unidades) > 1:
            raise ValueError("Esos indicadores tienen unidades distintas (" + ", ".join(u or "cantidad" for u in unidades)
                             + "). No se pueden poner en la misma gráfica: haz una gráfica para cada unidad.")
        titulo = str(titulo or "").strip()[:120]
        if tipo == "cambio_anios":  # cada indicador con su valor en dos años y la diferencia
            comunes = sorted(set.intersection(*(set(self.ser[i]) for i in ids)))
            h = self._anio(hasta) or (comunes[-1] if comunes else None)
            d = self._anio(desde) or (max([a for a in comunes if a < h], default=None) if h else None)
            if not d or not h or d == h:
                raise ValueError("Para el cambio indica dos años distintos con datos («desde» y «hasta»).")
            if d > h:
                d, h = h, d
            faltan = [self.nombre(i) for i in ids if d not in self.ser[i] or h not in self.ser[i]]
            if faltan:
                raise ValueError(f"Sin dato en {d} o {h} para: {'; '.join(faltan[:10])}. Quita esos indicadores.")
            orden = sorted(ids, key=lambda i: -(self.ser[i][h] - self.ser[i][d]))
            valores = {self.nombre(i): {"desde": self.r(self.ser[i][d]), "hasta": self.r(self.ser[i][h]),
                                        "cambio": self.r(self.ser[i][h] - self.ser[i][d])} for i in orden}
            spec = {"tipo": tipo, "ids": orden, "desde": d, "hasta": h, "titulo": titulo or f"Cambio {d}–{h}"}
            return {"descripcion": f"Preparó gráfica del cambio {d}–{h} de {len(ids)} indicadores (del que más subió al que más bajó)",
                    "grafica": spec, "valores_graficados": valores, "unidad": unidades.pop()}
        if tipo == "comparar_anio":
            a = self._anio(anio) or self._ultimo_comun(ids)
            faltan = [self.nombre(i) for i in ids if a not in self.ser[i]]
            if faltan:
                raise ValueError(f"Sin dato en {a} para: {'; '.join(faltan)}. Elige otro año o quita esos indicadores.")
            valores = {self.nombre(i): self.r(self.ser[i][a]) for i in ids}
            spec = {"tipo": tipo, "ids": ids, "anio": a, "titulo": titulo or f"Comparación {a}"}
            return {"descripcion": f"Preparó gráfica de barras comparando {len(ids)} indicadores en {a}",
                    "grafica": spec, "valores_graficados": valores, "unidad": unidades.pop()}
        d = self._anio(desde, self.anio_min)
        h = self._anio(hasta, self.anio_max)
        if d > h:
            d, h = h, d
        resumen = []
        for i in ids:
            sel = {k: v for k, v in sorted(self.ser[i].items()) if d <= k <= h}
            if not sel:
                raise ValueError(f"{self.nombre(i)} no tiene datos entre {d} y {h}.")
            k1, k2 = min(sel), max(sel)
            resumen.append({"indicador": self.nombre(i), "primer_anio": k1, "valor_inicial": self.r(sel[k1]),
                            "ultimo_anio": k2, "valor_final": self.r(sel[k2]),
                            "maximo": self.r(max(sel.values())), "anio_maximo": max(sel, key=sel.get)})
        spec = {"tipo": tipo, "ids": ids, "desde": d, "hasta": h,
                "titulo": titulo or (self.nombre(ids[0]) if len(ids) == 1 else f"Evolución {d}–{h}")}
        nombre_tipo = "líneas" if tipo == "linea" else "barras"
        return {"descripcion": f"Preparó gráfica de {nombre_tipo} de {len(ids)} indicador{'es' if len(ids) > 1 else ''}, {d}–{h}",
                "grafica": spec, "resumen": resumen, "unidad": unidades.pop()}

    def ejecutar(self, nombre, args):
        fn = {"buscar_indicadores": self.buscar_indicadores, "obtener_valores": self.obtener_valores,
              "calcular": self.calcular, "calcular_serie": self.calcular_serie, "graficar": self.graficar,
              "buscar_tablas": self.buscar_tablas, "consultar_tabla": self.consultar_tabla}.get(nombre)
        if not fn:
            return {"error": f"La herramienta «{nombre}» no existe."}
        try:
            return fn(**(args if isinstance(args, dict) else {}))
        except (ValueError, TypeError, ZeroDivisionError, OverflowError) as e:
            return {"error": str(e)}

    def ids_en(self, args):
        if not isinstance(args, dict):
            return []
        out = [args.get("id"), args.get("id2")] + (args.get("ids") if isinstance(args.get("ids"), list) else [args.get("ids")])
        return [str(i) for i in out if i and str(i) in self.ser]


TIPOS_GRAFICA = ["linea", "barras", "comparar_anio", "cambio_anios"]
OPS_SERIE = ["razon", "proporcion", "diferencia", "suma", "variacion_anual"]

OPERACIONES = ["valor", "cambio", "crecimiento_anual_promedio", "promedio", "maximo", "minimo",
               "suma", "proporcion", "razon", "diferencia", "expresion"]

HERRAMIENTAS = [
    {"type": "function", "function": {
        "name": "buscar_indicadores",
        "description": "Busca indicadores en el catálogo por palabras clave y devuelve hasta 15 con su id. Úsala si los indicadores sugeridos no sirven.",
        "parameters": {"type": "object", "properties": {
            "texto": {"type": "string", "description": "Palabras clave, por ejemplo 'egreso doctorado' o 'subsidio federal'"}},
            "required": ["texto"]}}},
    {"type": "function", "function": {
        "name": "obtener_valores",
        "description": "Devuelve los valores por año de uno o varios indicadores (máximo 8).",
        "parameters": {"type": "object", "properties": {
            "ids": {"type": "array", "items": {"type": "string"}, "description": "ids de indicadores, por ejemplo ['His01-48']"},
            "desde": {"type": "integer", "description": "Año inicial (opcional)"},
            "hasta": {"type": "integer", "description": "Año final (opcional)"}},
            "required": ["ids"]}}},
    {"type": "function", "function": {
        "name": "calcular",
        "description": ("Hace cálculos exactos con los datos (también con series S… creadas con calcular_serie). Operaciones: "
                        "valor (id, anio); cambio (id, desde, hasta: diferencia y % de cambio); "
                        "crecimiento_anual_promedio (id, desde, hasta: tasa de crecimiento anual compuesta); "
                        "promedio, maximo, minimo (id, desde, hasta); "
                        "suma (ids, anio); proporcion (id = parte, id2 = total, anio: porcentaje que representa); "
                        "razon (id, id2, anio: cuántos de id hay por cada uno de id2, p. ej. alumnos por profesor); "
                        "diferencia (id, id2, anio); "
                        "expresion (expresion: aritmética con números, p. ej. '(65744-64208)/64208*100'). "
                        "Si no indicas anio se usa el más reciente disponible."),
        "parameters": {"type": "object", "properties": {
            "operacion": {"type": "string", "enum": OPERACIONES},
            "id": {"type": "string"}, "id2": {"type": "string"},
            "ids": {"type": "array", "items": {"type": "string"}},
            "anio": {"type": "integer"}, "desde": {"type": "integer"}, "hasta": {"type": "integer"},
            "expresion": {"type": "string"}},
            "required": ["operacion"]}}},
    {"type": "function", "function": {
        "name": "buscar_tablas",
        "description": "Busca tablas anuales (detalle por espacio universitario, programa, categoría o sexo) por palabras clave. Devuelve hasta 5 tablas con su id (P01…P18, A01…A69), tipo (numérica o lista de texto), años, grupos de filas, columnas y filas que coinciden.",
        "parameters": {"type": "object", "properties": {
            "texto": {"type": "string", "description": "Palabras clave, p. ej. 'personal académico facultad' o 'PROED'"}},
            "required": ["texto"]}}},
    {"type": "function", "function": {
        "name": "consultar_tabla",
        "description": ("Devuelve celdas de una tabla anual con su id, fila, columna y valor (máximo 240 celdas). "
                        "Filtra con grupo (los espacios dentro de un grupo, p. ej. «Facultad», «Centro universitario UAEM», «Plantel»), "
                        "filas (texto que deben contener) y columnas (texto que deben contener, p. ej. «Tiempo completo › Total»)."),
        "parameters": {"type": "object", "properties": {
            "tabla": {"type": "string", "description": "Id de la tabla, p. ej. P02"},
            "grupo": {"type": "string"},
            "filas": {"type": "array", "items": {"type": "string"}},
            "columnas": {"type": "array", "items": {"type": "string"}},
            "anio": {"type": "integer"}},
            "required": ["tabla"]}}},
    {"type": "function", "function": {
        "name": "calcular_serie",
        "description": ("Crea una serie nueva calculada año por año a partir de indicadores (o de otras series S…). "
                        "Operaciones: razon (id ÷ id2, p. ej. alumnos por PTC); proporcion (id ÷ id2 × 100, en %); "
                        "diferencia (id − id2); suma (ids); variacion_anual (% de cambio de id respecto al año anterior). "
                        "Devuelve el id de la serie (S1, S2…) y sus valores; úsalo en graficar o calcular."),
        "parameters": {"type": "object", "properties": {
            "operacion": {"type": "string", "enum": OPS_SERIE},
            "id": {"type": "string"}, "id2": {"type": "string"},
            "ids": {"type": "array", "items": {"type": "string"}},
            "nombre": {"type": "string", "description": "Nombre corto en español, p. ej. «Alumnos de bachillerato por PTC»"}},
            "required": ["operacion"]}}},
    {"type": "function", "function": {
        "name": "graficar",
        "description": ("Muestra una gráfica al usuario dibujada con los datos reales. Tipos: "
                        "linea (evolución por año de 1 a 4 indicadores con la misma unidad); "
                        "barras (evolución por año en columnas, 1 o 2 indicadores); "
                        "comparar_anio (barras que comparan de 2 a 30 indicadores o celdas de tabla en un solo año, p. ej. matrícula por nivel o personal por facultad). "
                        "Devuelve un resumen con las cifras clave para que puedas comentarla."),
        "parameters": {"type": "object", "properties": {
            "tipo": {"type": "string", "enum": TIPOS_GRAFICA},
            "ids": {"type": "array", "items": {"type": "string"}},
            "desde": {"type": "integer"}, "hasta": {"type": "integer"},
            "anio": {"type": "integer", "description": "Solo para comparar_anio"},
            "titulo": {"type": "string", "description": "Título corto en español"}},
            "required": ["tipo", "ids"]}}},
]

EQUIV_T = {"licenci": ["estudios profesionales"], "posgrad": ["estudios avanzados"], "prepa": ["bachillerato"], "prepara": ["bachillerato"],
           "alumno": ["matricu", "alumnado"], "alumnos": ["matricu", "alumnado"], "estudia": ["matricu", "alumnado"], "aspiran": ["solicit"], "aspirant": ["solicit"]}
NIVEL_T = [(re.compile(r"licenci|profesional"), "estudios profesionales"), (re.compile(r"posgrad|maestr|doctor|especialidad|avanzad"), "estudios avanzados"),
           (re.compile(r"prepa|bachill|plantel"), "bachillerato")]
SUBCONJ_T = ["excelencia", "deport", "emprend", "afiliad", "empleo", "desocupad", "ocupacion", "continuan", "verano", "delfin", "discapa", "lenguas indigenas", "incorpor", "riesgo", "municip", "campo de formacion", "lineamiento"]
PIDE_FICHA = re.compile(r"ficha|resumen|panorama|datos generales|informacion general|fundacion|fundad|se fundo|perfil del|todo sobre|semblanza")
PIDE_LISTA = re.compile(r"lista|cuales|que programas|nombres?|acredit|vigente|oferta|planes? de estudio|organismo|snp|cifrhs|intrainstitucional|interinstitucional|creacion|reestructuracion")
VACIAS_T = set("tiene tienen tuvo tuvieron hay hubo fueron existen de la el en los las del y por para con que como cuantos cuantas cual total numero porcentaje porcentajes proporcion universidad uaemex tabla tablas dato datos anio ano dame muestra muestrame grafica graficas grafico graficos graficar grafiques barras barra pastel linea lineas haz hazme quiero necesito relacion relaciones comparacion comparativo compara comparar".split())
SIN_T = {"profesores": "profesora", "profesor": "profesora", "docentes": "profesora", "docente": "profesora", "maestros": "profesora",
         "ptc": "tiempo completo", "sni": "sistema nacional", "snii": "sistema nacional", "becas": "beca", "deportivas": "deport", "deportivos": "deport", "deportiva": "deport", "deportivo": "deport", "deportes": "deport", "deporte": "deport", "becados": "beca", "becadas": "beca", "becado": "beca", "becada": "beca", "facultades": "facultad", "planteles": "plantel", "prepas": "plantel", "preparatorias": "plantel",
         "dependencias": "dependencia", "centros": "centro", "hombres": "hombres", "mujeres": "mujeres", "genero": "hombres",
         "sexo": "hombres", "estimulos": "proed", "capacitacion": "capacit", "capacitados": "capacit", "cursos": "curso",
         "incorporadas": "incorporad", "particulares": "incorporad"}

VACIAS = set("de la el en los las del y por para con que como cuantos cuantas total numero universidad uaemex".split())


def norm(s):
    s = unicodedata.normalize("NFD", str(s))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9%\s]", " ", s)).strip()


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos}


def evaluar(expr):
    """Evalúa aritmética simple de forma segura (sin variables ni funciones)."""
    expr = expr.replace(",", "").replace("×", "*").replace("÷", "/").replace("^", "**")
    if not expr.strip() or len(expr) > 200:
        raise ValueError("Expresión vacía o demasiado larga.")

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return float(n.value)
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            a, b = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Pow) and (abs(b) > 100 or abs(a) > 1e12):
                raise ValueError("Potencia demasiado grande.")
            return _OPS[type(n.op)](a, b)
        if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.operand))
        raise ValueError("Solo se permiten números y + - * / ** ( ).")

    try:
        v = ev(ast.parse(expr, mode="eval"))
    except SyntaxError:
        raise ValueError(f"No entendí la expresión «{expr}».")
    if isinstance(v, complex) or math.isnan(v) or math.isinf(v):
        raise ValueError("El resultado no es un número válido.")
    return v

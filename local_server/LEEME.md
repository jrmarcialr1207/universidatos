# Universidatos con IA: versión local (Ollama)

La IA corre en tu propia computadora o en un servidor de la universidad. No pagas por consulta y los datos no salen de tu equipo.

## Contenido de la carpeta

| Archivo | Para qué sirve |
|---|---|
| `index.html` | La página (buscador, gráficas y modo IA). Es la misma que puedes subir a GitHub Pages. |
| `series_uaemex.json` | Los datos de las series 2004–2025. |
| `tablas_uaemex.json` | Las 364 tablas anuales con detalle de 2018 a 2025 (318 de 2025, casi todas también con los años anteriores, y 46 que solo existen en años anteriores o cambiaron de formato): 83 de Docencia, 30 de Ciencia, 9 de Internacionalización, 24 de Difusión, 74 de Extensión, 47 de Gestión, 23 de Personal, 1 de Cobertura, 10 de Presencia y 63 fichas por espacio. En `index.html` van comprimidas (gzip) y la página las descomprime con fflate (licencia MIT). |
| `tablas_a_json.py` | Regenera `tablas_uaemex.json` a partir de los Excel de las tablas anuales. |
| `servidor.py` | Sirve la página y conecta las preguntas con Ollama. |
| `calculos.py` | Las herramientas de cálculo que la IA puede pedir. |
| `buscador.py` | El mismo buscador de la página, para que la IA pueda buscar indicadores. |
| `iniciar.bat` | Doble clic para arrancar en Windows. |
| `iniciar.command` | Arranque en Mac (doble clic) o Linux. Ahí se elige el modelo. |
| `equivalencias.json` | Qué tabla de 2025 corresponde a cada archivo de las Agendas 2018 a 2024 (lo usa `tablas_a_json.py`). |
| `origenes_2018_2021.json` | Nombre original de cada archivo de las Agendas 2018–2021 (ver abajo). |
| `series_a_tabla.py` | Regenera `series_uaemex.json` cuando salga una nueva Agenda. |

## Requisitos

- **Memoria:** 8 GB de RAM como mínimo para un modelo de 7–8 mil millones de parámetros; 16 GB recomendados.
- **Tarjeta gráfica:** opcional. Sin ella funciona, solo tarda más (de 20 a 60 segundos por respuesta en lugar de 2 a 10).
- **Espacio:** unos 5 GB para el modelo.
- **Python 3.9 o más reciente** (https://www.python.org). No hace falta instalar librerías.

## Instalación (una sola vez)

1. **Instala Ollama** desde https://ollama.com/download.
   - Windows y Mac: descarga el instalador y ábrelo.
   - Linux: `curl -fsSL https://ollama.com/install.sh | sh`
2. **Descarga el modelo.** Abre una terminal (en Windows, "Símbolo del sistema" o PowerShell) y ejecuta:
   ```
   ollama pull qwen2.5:7b
   ```
   Pesa unos 4.7 GB; tarda según tu internet.
3. **Prueba que responde:** `ollama run qwen2.5:7b "Hola"` debe contestar algo. Sal con `/bye`.

## Uso diario

1. Verifica que Ollama esté abierto (en Windows y Mac aparece su ícono junto al reloj).
2. Arranca el servidor:
   - **Windows:** doble clic en `iniciar.bat`.
   - **Mac:** doble clic en `iniciar.command`. La primera vez, si macOS lo bloquea, haz clic derecho › Abrir.
   - **Mac / Linux desde la terminal:** dentro de esta carpeta, `./iniciar.command` (o `python3 servidor.py` para el modelo predeterminado).
3. Abre **http://localhost:8000** en el navegador.
4. Debajo de los ejemplos aparece la casilla **"Redactar la respuesta con IA local"**. Escribe tu pregunta: primero verás el dato del buscador al instante y, segundos después, la respuesta redactada por la IA.

Para detener el servidor cierra la ventana o presiona `Ctrl+C`.

## Modo guiado (por omisión)

Los modelos que corren en Ollama son pequeños: si tienen que decidir solos qué tabla consultar, qué calcular y en qué orden, se equivocan seguido. Por eso el servidor trabaja en **modo guiado**:

1. El servidor interpreta la pregunta con reglas: detecta si habla de un espacio (por ejemplo, «Facultad de Ingeniería»), si compara espacios («¿qué facultad tiene más…?», «por centro universitario»), si pide porcentaje de mujeres u hombres, años, crecimiento o una gráfica.
2. El servidor hace las consultas, los cálculos y las gráficas con los datos oficiales.
3. El modelo **solo redacta** la respuesta con esa lista de hechos ya calculados.

Ejemplos que resuelve así:

- «¿Qué datos tienen de la Facultad de Ingeniería respecto a personal?» → ficha con 6 tablas, el porcentaje que representa y una gráfica.
- «¿Qué facultad tiene más personal académico?» → comparación de las 21 facultades.
- «Porcentaje de mujeres en el personal académico por facultad».
- «Grafica los profesores de tiempo completo por centro universitario».
- «Personal administrativo de Medicina y Odontología».
- «¿Cuántos alumnos tiene la Facultad de Ingeniería?» → licenciatura, posgrado, abandono y tutoría de esa facultad.
- «Matrícula de licenciatura por facultad», «eficiencia terminal por facultad», «alumnos de prepa por plantel».
- «Porcentaje de mujeres en la matrícula por facultad».
- «¿Qué programa tiene la mayor matrícula?» (sumando sedes) o «… por espacio académico» (cada sede).
- «¿Qué espacio tiene la mejor relación alumnos por PTC?».
- «Miembros del SNII por facultad», «proyectos de investigación por facultad», «patentes en trámite».
- «¿Cuántos alumnos becados tiene la Facultad de Ingeniería?», «servicio social por facultad», «atenciones médicas por plantel».
- «Dame una tabla con PTC y PTC en el SNII por espacio académico» → tabla con totales y porcentaje, que se puede descargar en CSV.
- «¿Quién tiene la mejor relación entre PTC y PTC en el SNII (o Prodep, doctorado, alumnos) por espacio?».
- «Crecimiento de la matrícula de licenciatura desde 2015», «matrícula licenciatura 2020», «grafica los titulados».

Si la pregunta no encaja (por ejemplo, «alumnos por cada PTC»), el servidor pasa solo al modo con herramientas, donde la IA decide los pasos. En «Ver cómo obtuvo la respuesta» se ve qué hizo el servidor.

Para cambiar de modo: `MODO=herramientas` (la IA decide todo) o `MODO=simple` (solo redacta con el indicador más parecido).

## Cómo hace cálculos la IA

La IA no hace cuentas de memoria (los modelos pequeños se equivocan seguido). En su lugar **pide herramientas** al servidor, que hace las operaciones en Python con los datos exactos:

| Herramienta | Qué hace |
|---|---|
| `buscar_indicadores` | Busca indicadores por palabras clave. |
| `obtener_valores` | Lee los valores por año de uno o varios indicadores. |
| `calcular_serie` | Crea una serie nueva año por año (S1, S2…): `razon` (por ejemplo, alumnos por PTC), `proporcion` (en %), `diferencia`, `suma` o `variacion_anual`. Esa serie se puede graficar y usar en otros cálculos. |
| `calcular` | `valor`, `cambio` (diferencia y %), `crecimiento_anual_promedio` (tasa compuesta), `promedio`, `maximo`, `minimo`, `suma`, `proporcion` (parte / total en %), `razon` (por ejemplo, alumnos por profesor), `diferencia` y `expresion` (aritmética libre y segura). |

Ejemplos de preguntas que ya puede contestar con cálculo:

- «¿Cuál fue el crecimiento anual promedio de la matrícula de licenciatura de 2015 a 2025?»
- «¿Qué porcentaje de los PTC tiene doctorado en 2025?»
- «¿Cuántos alumnos de licenciatura hay por cada PTC?»
- «Suma la matrícula de bachillerato, licenciatura y posgrado en 2020.»
- «¿En qué año hubo más titulados?»
- «Grafica por separado la matrícula de cada nivel dividida entre los PTC.»

Debajo de cada respuesta, **"Ver cómo obtuvo la respuesta"** muestra cada paso y su resultado.

## Tablas anuales (detalle por espacio universitario)

Además de las series, la página incluye 364 tablas anuales de 2018 a 2025. Por omisión se usa 2025; pregunta «en 2019» para otro año o «de 2018 a 2025» para ver el cambio.

**Docencia (69 tablas):** oferta educativa y programas acreditados; aspirantes, ingreso y matrícula de bachillerato, licenciatura y posgrado por plantel, facultad, centro universitario y programa; egreso, titulación, eficiencia terminal, abandono, transición, promoción, regularización y reprobación; alumnado con discapacidad y hablante de lengua indígena; tutoría, riesgo académico y orientación educativa; acervo y recursos electrónicos de bibliotecas; infraestructura (laboratorios, talleres y más); y escuelas incorporadas. Algunas tablas son listas de texto (por ejemplo, los programas vigentes en el SNP); el visor las muestra como lista y se pueden filtrar.

**Ciencia (27 tablas):** PTC registrados en la SEP, con perfil Prodep e investigadores, por espacio y grado; miembros del SNII por espacio y nivel (PTC y no PTC); licencias y apoyos académicos; cuerpos académicos y LGAC (listas); proyectos de investigación por espacio, área, fuente de financiamiento y tipo; recursos asignados; productos académicos; revistas y publicaciones de divulgación (listas); Octubre, mes de la ciencia; redes de colaboración (lista); becas Verano Delfín; becarios extranjeros; patentes en trámite y diplomados superiores.

**Difusión (18 tablas):** identidad y cultura, talleres culturales por espacio, eventos artísticos, Casa de las Diligencias, patrimonio, exposiciones (lista), conferencias, talleres de ciencia y cultura, CeAC, elenco artístico, función y producción editorial, publicaciones (lista), revistas, teatro y visitas guiadas por espacio.

**Extensión (61 tablas):** alumnado becado y becas por nivel, espacio, programa, tipo y fuente (montos en miles de pesos); seguro estudiantil y servicios de salud; consultorios y atenciones médicas y psicológicas; servicio social y prácticas profesionales por programa; servicios comunitarios y brigadas; CELe y CILC; educación continua; convenios; emprendimiento; seguimiento de egresados; Clínica Multidisciplinaria de Salud; deporte y cultura física. Varias vienen por nivel educativo (Bachillerato › Plantel…, Estudios profesionales › Facultad…).

**Gestión (45 tablas):** certificación ISO y manuales (listas); origen y aplicación de recursos, recursos etiquetados y adquisiciones (miles de pesos); bienes inventariados e inmuebles; obra universitaria (lista); servicios de mantenimiento y servicios generales por tipo y por espacio; salas de lactancia (lista); Potrobús; computadoras por espacio y en la red institucional; sistemas y sitios web (listas); comunidades virtuales; videoconferencias; internet inalámbrico; planeación y evaluación; fomento ambiental y residuos peligrosos; protección universitaria; Consejo Universitario; legislación y convenios; jornadas de igualdad de género; transparencia; comunicación universitaria y redes sociales.

**Internacionalización (9 tablas):** alumnado UAEMEX y externo en movilidad por país, institución y espacio; personal en movilidad; instituciones con convenios de internacionalización.

**Cobertura (1 tabla):** población por grupo de edad, matrícula estatal, nacional y UAEMEX por nivel, con la tasa de cobertura y la participación de la UAEMEX.

**Presencia (10 tablas, listas):** espacios universitarios por municipio; institutos y centros de investigación; espacios culturales; CELe; CILC; incubadoras; unidades de emprendimiento; centros deportivos; librerías; estructura de las DES.

**Fichas por espacio (60):** una ficha por facultad o escuela (O01–O22), centro universitario (U01–U12), unidad académica profesional (V01–V07), instituto o centro de investigación (N01–N08) y plantel de la Escuela Preparatoria (B01–B11), con año de fundación, alumnado por programa, tutoría, investigación, movilidad, becas, servicio social, personal e infraestructura. Pregunta, por ejemplo, «dame la ficha de la Facultad de Ingeniería» o «¿en qué año se fundó la Facultad de Medicina?».

**Personal (18 tablas):** personal académico y administrativo por facultad, plantel, centro universitario, UAP, instituto y dependencia, por categoría y por sexo; PROED; concursos de oposición; juicios de promoción; capacitación; carrera administrativa; evaluaciones; y personal de escuelas incorporadas.

- **Sin IA:** en la sección «Tablas anuales» eliges la tabla, tocas una columna y la página grafica esa columna comparando las facultades (u otro grupo).
- **Con IA:** pregunta, por ejemplo, «¿qué facultad tiene más personal académico?» o «porcentaje de mujeres en el personal académico de Ingeniería». La IA usa `buscar_tablas` y `consultar_tabla`, y puede calcular y graficar con esas celdas (comparaciones de hasta 30 barras).
- Las celdas vacías de los renglones de detalle se leen como 0. En los renglones que agrupan a otros, y en columnas que solo se llenan en los grupos, quedan como «sin dato».

Para agregar otros años o secciones, pon los Excel en carpetas por año (por ejemplo `2025/Acad01.xlsx` o `2024/Doc01.xlsx`; se reconocen los nombres de 2025 —Acad, Ciencia, Interna, IdentiyCul, Ext, Personal, Ges, Pres, Cob, OA, CU, UAP, ICI, PEP— los de 2024 —Doc, Inv, Int, Dif, Per— y los de 2023 —DOC, INV, COOP, DIFCUL, EXT, PER, GES, IyC— y los de 2022 —Coo, Pep—) y ejecuta:

```
python tablas_a_json.py tablas_uaemex.json 2025 2024 2023 2022 2021 2020 2019 2018
```

En las Agendas 2018–2021 los archivos se llaman por el número de cuadro (`Docencia/100.xlsx`, `Difusion/211a.xlsx`…). Para usarlos se copian a la carpeta del año con el prefijo de su sección (Doc, Inv, Coo, Dif, Ext, Per, Ges, OA, CU, UAP, IyC, Pep) y el número 5000 + 4 × cuadro + parte (0 sin letra, 1 para «a» o «.1», 2 para «b», 3 para «c»): `Docencia/100.xlsx` → `Doc5400.xlsx`, `Difusion/211a.xlsx` → `Dif5845.xlsx`. `origenes_2018_2021.json` tiene la lista completa.

La numeración de las tablas cambia entre Agendas (por ejemplo, «Computadoras por espacio» es la 13 de Gestión en 2024 y la 15 en 2025). El archivo `equivalencias.json`, junto a las carpetas de los años, dice a qué tabla actual corresponde cada archivo de un año anterior (`"2024": {"Ges13": "G15", …}`); las tablas que solo existen en ese año llevan un número del 81 en adelante (p. ej. G81). Los renglones y columnas se unen por su nombre sin importar el ciclo («Personas egresadas global 2023-2024» y «… 2024-2025») ni el lenguaje incluyente («Profesores» y «Profesoras / es»); el año más reciente da las etiquetas que se muestran, y las de cada año se guardan aparte. Ojo: en 2024 los programas educativos se separaban por modalidad («(mixta)») y en 2025 no, así que a nivel programa no siempre hay los dos años; a nivel espacio sí. Después hay que regenerar `index.html` con las tablas nuevas.

## Gráficas pedidas a la IA

La IA también tiene la herramienta `graficar`. No dibuja ni escribe números: elige **qué** graficar y la página dibuja la gráfica con los datos oficiales.

| Tipo | Para qué | Ejemplo de pregunta |
|---|---|---|
| `linea` | Evolución por año de 1 a 4 indicadores | «Grafica la matrícula de bachillerato, licenciatura y posgrado desde 2010» |
| `barras` | Evolución por año en columnas (1 o 2 indicadores) | «Haz una gráfica de barras de los titulados en los últimos 8 años» |
| `comparar_anio` | Comparar de 2 a 8 indicadores en un solo año | «Compara en una gráfica la matrícula por nivel en 2025» |

- Cada respuesta puede traer hasta 4 gráficas, cada una con su tabla y el archivo y las filas de origen.
- También se pueden graficar series calculadas (por ejemplo, alumnos por PTC); debajo de la gráfica aparece la fórmula usada.
- Las series calculadas solo existen durante esa pregunta; las preguntas de otras personas no se mezclan.
- Los botones **Descargar PNG** y **Descargar CSV** guardan la imagen (con título, leyenda y fuente) y los datos, listos para un informe o para Excel.
- El servidor no deja mezclar unidades en una misma gráfica (por ejemplo, porcentajes con número de alumnos). Si la IA lo intenta, le pide que haga gráficas separadas.

Además:

- La gráfica y la tabla siempre salen directo de los datos, nunca de la IA.
- El servidor revisa cada número que escribe la IA. Si alguno no salió de los datos o de un cálculo, la página muestra el aviso **"Revisa estas cifras"**.
- Si el modelo no admite herramientas, el servidor cambia solo al modo simple: le entrega los datos con los cambios ya calculados y la IA solo redacta.
- Las preguntas con cálculos tardan más, porque la IA hace varias rondas (pide una herramienta, lee el resultado y decide). En una computadora sin tarjeta gráfica puede ser 1 a 2 minutos. Si prefieres rapidez, arranca con `MODO=simple`.

## Usarlo desde otras computadoras de la red

Arranca el servidor permitiendo conexiones de la red:

- Windows (Símbolo del sistema): `set HOST=0.0.0.0` y luego `python servidor.py`
- Mac / Linux: `HOST=0.0.0.0 python3 servidor.py`

Los demás entran con la IP de la computadora servidor, por ejemplo `http://192.168.1.50:8000`. La IP aparece con `ipconfig` (Windows) o `ip addr` (Linux). Si no conecta, permite el puerto 8000 en el firewall.

Cada visitante puede hacer hasta 10 preguntas por minuto y el servidor procesa 2 a la vez; las demás esperan su turno.

**Para abrirlo a internet**, pide apoyo a TI: hace falta un dominio, HTTPS y un proxy como Nginx o Caddy delante de `servidor.py`. Coordínalo con la SDFI si llevará el nombre de la UAEMEX.

## Qué modelo estoy usando

- En la página aparece junto a la casilla de IA: «Modelo …, instalado en este servidor».
- En una terminal: `ollama list` muestra los modelos descargados.
- En la ventana del servidor, al arrancar, se ve la línea «Modelo: …».

Con **36 GB de RAM** te conviene `qwen2.5:14b` (unos 9 GB): redacta y entiende bastante mejor que el de 7b y sigue siendo ágil. `qwen2.5:32b` (unos 20 GB) también cabe y es aún mejor, pero responde más lento, sobre todo sin tarjeta gráfica.

## Cambiar de modelo

| Modelo | Comando | Cuándo usarlo |
|---|---|---|
| `qwen2.5:7b` | `ollama pull qwen2.5:7b` | Recomendado: buen español y usa bien las herramientas. |
| `llama3.1:8b` | `ollama pull llama3.1:8b` | Alternativa de calidad parecida. |
| `qwen2.5:3b` | `ollama pull qwen2.5:3b` | Computadoras con poca memoria; más rápido, pero elige peor las herramientas. |
| `qwen2.5:14b` | `ollama pull qwen2.5:14b` | Si tienes 16 GB de memoria de video o más; mejores respuestas. |

Para usar otro modelo, descárgalo y arranca el servidor indicándolo:

- Windows: `set MODELO=llama3.1:8b` y luego `python servidor.py` (o edita `iniciar.bat`)
- Mac / Linux: `MODELO=llama3.1:8b python3 servidor.py`

## Problemas frecuentes

| Mensaje | Solución |
|---|---|
| "No se pudo conectar con Ollama" | Abre la aplicación Ollama y recarga la página. |
| "Falta descargar el modelo" | Ejecuta `ollama pull qwen2.5:7b` (o el modelo que configuraste). |
| La casilla de IA no aparece | Estás abriendo `index.html` directamente. Entra por `http://localhost:8000`. |
| "python no se reconoce" (Windows) | Reinstala Python marcando "Add Python to PATH", o usa `py servidor.py`. |
| La primera respuesta tarda mucho | Es normal: Ollama carga el modelo en memoria. Las siguientes son más rápidas. |
| La IA no usa las herramientas o responde sin cifras | Usa un modelo más grande (`qwen2.5:14b`) o el modo simple (`MODO=simple`). |
| En la ventana del servidor dice "no admite herramientas" | Ese modelo no soporta herramientas; funciona en modo simple. Para cálculos usa `qwen2.5:7b` o `llama3.1:8b`. |
| "Address already in use" | El puerto 8000 está ocupado. Usa otro: `set PUERTO=8080` (Windows) o `PUERTO=8080 python3 servidor.py`. |

## Actualizar los datos

1. Descarga los nuevos `His01.xlsx` a `His08.xlsx` de la Agenda más reciente.
2. Ejecuta `python series_a_tabla.py carpeta_con_los_xlsx salida` (necesita `pip install openpyxl`).
3. Copia el nuevo `salida/series_uaemex.json` a esta carpeta.
4. Regenera `index.html` con los datos nuevos, porque la página también los lleva dentro para el buscador. Si cambia el último año (por ejemplo, llega 2026), también hay que ampliar la lista de años de la página.

Datos: Secretaría de Desarrollo y Fortalecimiento Institucional, UAEMEX. Agenda Estadística 2025, Series 2004–2025.

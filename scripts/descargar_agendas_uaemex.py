"""
Descarga todos los archivos Excel de las Agendas Estadísticas de la UAEMEX (2018-2025).

Uso:
    pip install requests beautifulsoup4
    python descargar_agendas_uaemex.py

Crea una carpeta "agendas_uaemex/<año>/<sección>/archivo.xlsx" y un
"catalogo.csv" con el año, la sección, el título de cada tabla y su archivo.
"""
import csv
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "http://web.uaemex.mx/universidatos/AE{year}/indiceAE{yy}.html"
SALIDA = Path("agendas_uaemex")
AÑOS = range(2018, 2026)

sesion = requests.Session()
sesion.headers["User-Agent"] = "Mozilla/5.0 (descarga de agendas estadisticas)"

catalogo = []

for año in AÑOS:
    url_indice = BASE.format(year=año, yy=str(año)[2:])
    print(f"\n== {año}: {url_indice}")
    try:
        r = sesion.get(url_indice, timeout=30)
        r.raise_for_status()
    except Exception as e:
        print(f"   No se pudo abrir el índice: {e}")
        continue

    r.encoding = r.apparent_encoding
    soup = BeautifulSoup(r.text, "html.parser")

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.lower().endswith((".xlsx", ".xls")):
            continue

        url_archivo = urljoin(url_indice, href)
        partes = href.split("/")
        seccion = partes[-2] if len(partes) > 1 else "general"
        titulo = " ".join(a.get_text(" ", strip=True).replace("▸", "").split())

        destino = SALIDA / str(año) / seccion / partes[-1]
        destino.parent.mkdir(parents=True, exist_ok=True)

        if not destino.exists():
            try:
                f = sesion.get(url_archivo, timeout=60)
                f.raise_for_status()
                destino.write_bytes(f.content)
                print(f"   ✓ {seccion}/{partes[-1]}  {titulo[:60]}")
                time.sleep(0.3)  # ser amable con el servidor
            except Exception as e:
                print(f"   ✗ {url_archivo}: {e}")
                continue

        catalogo.append({
            "anio": año,
            "seccion": seccion,
            "titulo": titulo,
            "archivo": str(destino),
            "url": url_archivo,
        })

SALIDA.mkdir(exist_ok=True)
with open(SALIDA / "catalogo.csv", "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.DictWriter(fh, fieldnames=["anio", "seccion", "titulo", "archivo", "url"])
    w.writeheader()
    w.writerows(catalogo)

print(f"\nListo: {len(catalogo)} archivos. Catálogo en {SALIDA / 'catalogo.csv'}")

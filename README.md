# Universidatos

Natural-language querying of the Statistical Agenda (*Agenda Estadística*) of the Universidad Autónoma del Estado de México (UAEMEX), with language models and verifiable tools.

Universidatos answers questions such as "How did enrollment change in each academic unit from 2018 to 2025?" and returns figures, calculations and charts that can be traced back to the cell of the official Excel file. A language model chooses the tools and writes the answer; deterministic tools read the data, calculate and plot, so the model never writes a figure of its own.

## Contents

| Folder | What it contains |
| --- | --- |
| `data/` | Processed data: 364 annual tables 2018–2025 (`tablas_uaemex.json`), 453 historical series 2004–2025 (`series_uaemex.json`, `series_uaemex_2004_2025.csv`), the equivalence file used to merge years (`equivalencias.json`) and the file-name origins of the 2018–2021 Agendas (`origenes_2018_2021.json`) |
| `scripts/` | Download of the Agenda Excel files, the Excel reader, the series converter and the page builder |
| `web/` | Source of the web interface (template, search engine, Claude agent code, fflate) |
| `static_site/` | Static site without a language model (search engine only); publishable on any web server or GitHub Pages |
| `claude_page/` | Page that uses Claude as the agent (runs as a Claude artifact) |
| `local_server/` | Local server with a language model running on Ollama (default Qwen2.5-7B) and the guided mode; works offline. Instructions in `local_server/LEEME.md` (Spanish) |

## Source data

The source data are the Statistical Agendas published by UAEMEX at
<https://sdfi.uaemex.mx/estadisticas/universidatos/agendas-estadísticas.html>.
The Excel files are not redistributed here; `scripts/descargar_agendas_uaemex.py` downloads them.

## Reproducing the data

Requirements: Python 3.9 or later, `openpyxl`, `requests`, `beautifulsoup4`.

```bash
pip install openpyxl requests beautifulsoup4
python scripts/descargar_agendas_uaemex.py          # downloads the Agenda Excel files
# arrange the files by year in datos_anuales/<year>/ (see local_server/LEEME.md, section "Tablas anuales")
python scripts/tablas_a_json.py data/tablas_uaemex.json datos_anuales/2025 datos_anuales/2024 datos_anuales/2023 datos_anuales/2022 datos_anuales/2021 datos_anuales/2020 datos_anuales/2019 datos_anuales/2018
python scripts/construir.py                         # rebuilds static_site/, local_server/ and claude_page/
```

Every cell in `tablas_uaemex.json` keeps its Excel row and column, so any value can be checked against the original file.

## Running the local version

1. Install [Ollama](https://ollama.com) and download the model: `ollama pull qwen2.5:7b`
2. In `local_server/`, run `python servidor.py` (or `iniciar.bat` on Windows, `iniciar.command` on macOS).
3. Open <http://localhost:8000>.

No Python packages are needed for the server.

## License

Code and processed data: MIT License (see `LICENSE`). The source statistics belong to UAEMEX. `web/vendor/fflate-0.8.2.umd.js` is © 2023 Arjun Barrett, MIT License.

## Citation

If you use this software or data, please cite it as described in `CITATION.cff`.

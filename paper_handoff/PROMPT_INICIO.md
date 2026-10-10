# Prompt para pegar en Claude Code

Antes: copia `CLAUDE.md` y la carpeta `paper/` a la raíz del repo `Sentiment_and_news-Peru` (rama `updated_version`)
y copia tus 10 PDFs a `paper/docs/pdfs/` (agrega `paper/docs/pdfs/` al .gitignore: pesan ~44 MB y tienen copyright). Luego abre Claude Code en esa carpeta y pega:

---

Continúa mi proyecto de paper. Lee primero `CLAUDE.md`, `paper/docs/RESULTADOS_2026-09.md`, `paper/docs/ROADMAP_PAPER.md`
y `paper/docs/LITERATURA.md`. Resumen: este repo es mi tesis 2022 (titulares de Gestión + VADER + VAR con intervención del BCRP
y tipo de cambio). Ya auditamos el código, encontramos que ~96% de los titulares se publicó tras el cierre de las 13:30,
escribimos un scraper v2 con horas reales y un script que replica el VAR original vs uno corregido. Ahora quiero llegar a un
preprint antes del 15 de diciembre de 2026.

Haz esto, en orden, con commits pequeños en una rama `paper-llm`:

1. Crea un entorno (`python -m venv .venv` + `pip install -r paper/code/requirements.txt`) y verifica que ambos scripts corren.
2. **Paso 1.1 del roadmap:** toma una muestra aleatoria de 400 titulares de `data/data_en.csv` entre 2020-12-28 y 2021-11-10
   (semilla 7), corre `gestion_scraper.py historico` sobre ella y luego `replicacion_var.py --repo . --horas <salida>`.
   Compara con `paper/resultados/replicacion_var/resumen.txt` y repórtame las diferencias.
3. Escribe `paper/code/figura_timing.py`: histograma de la hora de publicación (hora Lima) de esa muestra con una línea en 13:30.
4. Deja corriendo en segundo plano los pasos 1.2 y 1.3 (`historico` sobre `data/data_es.csv` y `listar` desde 2022-01-01),
   con logs en `paper/data/logs/`. Antes, pon mi correo en la constante `UA` del scraper (pregúntamelo).
5. Mientras tanto, escribe `paper/code/mercado.py` (paso 1.5) y busca en BCRPData las series diarias de intervención
   cambiaria con signo (compras/ventas spot y swaps). Si no existen diarias, dime qué alternativas hay.
6. Al terminar, actualiza las casillas de `ROADMAP_PAPER.md` y dame un resumen de 5 líneas con el siguiente paso.

Reglas: no modifiques `thesis/` ni `data/` originales; todo lo nuevo va en `paper/`. No subas datos scrapeados masivos.
Respóndeme en español y conciso.

---

## Prompts para las fases siguientes (úsalos cuando toque)

**Fase 2 (gold set):**
"Implementa la fase 2 del roadmap: escribe `paper/docs/guia_anotacion.md` con 20 ejemplos difíciles, haz el muestreo estratificado
de 2,500 titulares desde `paper/data/alineado.csv` y prepara un CSV para anotar en Label Studio con los campos relevante, s_pe, s_us, tema."

**Fase 3 (LLMs):**
"Implementa la fase 3: baseline VADER traducido, BETO fine-tuned multi-salida y un LLM abierto zero/few-shot con salida JSON
validada con pydantic. Reporta F1 macro por tarea en el test set y guarda las predicciones en `paper/data/pred/`."

**Fase 4 (econometría):**
"Implementa la fase 4: construye S_PE, S_US y atención por día cambiario y ventana; corre regresión base HAC, proyecciones locales
h=0..10, VARX con identificación alternativa de la intervención, EGARCH y evaluación OOS vs paseo aleatorio. Una figura y una tabla por script."

**Fase 5 (paper):**
"Crea `paper/tex/` con una plantilla de arXiv y redacta el borrador con las secciones del roadmap usando solo resultados
que estén en `paper/resultados/`. Cita desde `paper/docs/LITERATURA.md` en un `refs.bib`."

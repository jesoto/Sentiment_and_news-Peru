# Hoja de ruta al paper

Meta intermedia: **preprint en SSRN/arXiv antes del 15-dic-2026** (postulación MBZUAI).
Meta final: envío a revista/workshop (FinNLP, LatinX in AI, Encuentro de Economistas BCRP; luego una revista
tipo *Emerging Markets Review*, *Journal of International Money and Finance* o *Finance Research Letters*).

Marca cada casilla al terminar. Cada paso deja un script en `paper/code/` y una salida en `paper/resultados/`.

## Fase 1 — Datos (semanas 1-2)
- [ ] **1.1 Reproducir la replicación.** Muestra de 400 titulares → `historico` → `replicacion_var.py --horas`.
      Verificar que los números coinciden con `resultados/replicacion_var/resumen.txt`.
- [ ] **1.2 Horas del corpus completo 2018-2022.** `historico --entrada data/data_es.csv --workers 2` (~26.9k URLs, ~4-6 h).
- [ ] **1.3 Listado completo 2022-01-01 → hoy.** `listar` (~1,750 días, ~1 h).
- [ ] **1.4 Alinear** ambos con `alinear` → `paper/data/alineado.csv` + `tc_cierre_bcrp.csv`.
- [ ] **1.5 Datos de mercado** (`paper/code/mercado.py`): BCRP (TC 13:30 PD04646PD, cobre PD04701XD, EMBIG Perú PD04709XD,
      intervención spot y swaps con signo — buscar series en BCRPData), FRED (DTWEXBGS, VIXCLS, DGS10), CLP y COP.
- [ ] **1.6 Filtro de relevancia v0** por sección (economía, mercados, política, tu-dinero, mundo) + palabras clave
      (dólar, tipo de cambio, BCRP, Fed, cobre, vacancia...). Medir cuántas notas por día quedan.

## Fase 2 — Gold set (semanas 3-4)
- [ ] **2.1 Guía de anotación** (`docs/guia_anotacion.md`) con 20 ejemplos difíciles (p. ej. "Fed sube tasas" → S_US = +1, S_PE = 0).
- [ ] **2.2 Muestreo estratificado** de 2,500 titulares (por año, sección y días de alta volatilidad).
- [ ] **2.3 Anotación doble** (Jesús + otro anotador; 300 en común para kappa). Herramienta: Label Studio o una hoja.
- [ ] **2.4 Split** train/dev/test fijo por fecha (test = el periodo más reciente).

## Fase 3 — Extracción de sentimiento (semanas 5-6)
- [ ] **3.0 Baseline tesis:** traducción + VADER (reutilizar el pipeline de `thesis/`).
- [ ] **3.1 Encoder español:** BETO o RoBERTa-BNE fine-tuned en el gold set (multi-salida: relevancia, S_PE, S_US).
- [ ] **3.2 LLM abierto zero/few-shot** con salida JSON (`{relevante, s_pe, s_us, tema}`), temperatura 0.
- [ ] **3.3 QLoRA** del mismo LLM sobre el gold set.
- [ ] **3.4 LLM cerrado** como techo (solo en test por costo).
- [ ] **3.5 Tabla 1:** F1 macro por tarea y modelo.
- [ ] **3.6 Anonimización** (entidades, fechas, cifras → marcadores) y reetiquetado del test con 3.2/3.4 para RQ3.

## Fase 4 — Índices y econometría (semanas 7-8)
- [ ] **4.1 Índices diarios** S_PE, S_US, atención (n notas relevantes), por ventana `pre_apertura` / `intradia`.
- [ ] **4.2 Regresión base** r_{t+h} ~ S_PE + S_US + controles + rezagos, HAC.
- [ ] **4.3 Proyecciones locales** h = 0..10 (figura principal).
- [ ] **4.4 VARX** con exógenas globales; intervención identificada por (a) sorpresa de función de reacción,
      (b) orden alternativo, (c) restricciones de signo. Comparar con Cholesky de la tesis.
- [ ] **4.5 Volatilidad:** EGARCH con S_PE, S_US e intervención en la varianza.
- [ ] **4.6 Heterogeneidad:** crisis política (vacancias, elecciones 2021, dic-2022) vs calma; días con/sin intervención.
- [ ] **4.7 OOS:** ventana móvil vs paseo aleatorio; Diebold-Mariano, Clark-West, % aciertos de dirección.
- [ ] **4.8 RQ3:** comparar resultados con y sin anonimizar, y dentro vs después del cutoff del LLM.

## Fase 5 — Escritura (semanas 9-10)
- [ ] **5.1 Esqueleto LaTeX** en `paper/tex/` (plantilla Elsevier o arXiv).
- [ ] **5.2 Secciones:** 1 Introducción · 2 Literatura · 3 Datos (incluye el problema de timing como contribución
      metodológica) · 4 Medición del sentimiento · 5 Estrategia empírica · 6 Resultados · 7 Robustez y look-ahead · 8 Conclusión.
- [ ] **5.3 Figuras:** timing de publicación (histograma de horas), IRF original vs corregido, LP de S_PE/S_US, F1 por modelo.
- [ ] **5.4 Publicar** gold set + índices diarios + código (Zenodo/GitHub con licencia CC-BY para los datos derivados;
      no redistribuir texto completo de Gestión).
- [ ] **5.5 Preprint** en SSRN y arXiv (q-fin.ST / cs.CL).

## Fase 6 — Coautores (en paralelo, desde la semana 2)
- [ ] Correo a Rodríguez, Villavicencio y Bendezú con `resultados/replicacion_var/irf_original_vs_corregido.png`
      y la tabla del timing. Propuesta: Jesús = datos, NLP y LLMs; Rodríguez = identificación de la intervención y volatilidad;
      Villavicencio = marco financiero e incertidumbre política; Bendezú = econometría financiera aplicada.
- [ ] Reunión: acordar autoría, revista objetivo y si conviene el Encuentro de Economistas del BCRP como primer foro.

## Riesgos y mitigación
| Riesgo | Mitigación |
|---|---|
| Efecto diario pequeño vs ruido | El gold set y el análisis de timing/look-ahead sostienen el paper; un nulo OOS bien hecho es publicable |
| Gestión cambia la API | Guardar crudos (`.parcial.jsonl`) y versionar las fechas de descarga |
| Intervención sin signo/swaps | Bajar series oficiales del BCRP; si no hay diarias con signo, usar notas informativas del BCRP |
| Costo de LLM cerrado | Usarlo solo en el test set |
| Look-ahead en 2022-2024 | Anonimización + submuestra posterior al cutoff del modelo abierto |

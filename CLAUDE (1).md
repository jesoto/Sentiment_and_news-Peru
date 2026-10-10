# CLAUDE.md — Paper: sentimiento de noticias con LLMs y tipo de cambio en Perú

Contexto del proyecto para Claude Code. Léelo completo antes de tocar código.

## Quién y qué
- Autor: Jesús Soto Enríquez (Gzuz). Data Scientist / ML Engineer en Lima. Egresado de Economía PUCP.
- Este repo (`Sentiment_and_news-Peru`, rama `updated_version`) es su **tesis de pregrado de 2022**:
  scraping de titulares de Gestión, traducción al inglés con Google Translate, VADER, LDA y un VAR
  (sentimiento, intervención cambiaria BCRP, tipo de cambio) con impulso-respuesta.
- Objetivo ahora: convertir la tesis en un **paper publicable** que use LLMs en español, corrija los
  problemas de identificación y timing, y sirva como evidencia de investigación para postular a maestrías
  (MBZUAI, cierre 15-dic-2026; Konrad Zuse / DAAD en 2027).
- Comunicarse en **español, conciso, ejecutar más que explicar**.

## Estructura
```
thesis/            # notebooks originales 2022 (no modificar; son el baseline)
  BeautifulSoup.ipynb, ScrapeAndProcess.ipynb  -> scraper viejo (archivo /archivo/todas/{fecha}/)
  Sentiment_Analysis.ipynb                     -> limpieza, VADER sobre títulos traducidos, LDA, TF-IDF
  iter.ipynb                                   -> bigramas + RandomForest para dirección del TC
data/              # datos 2022
  data_es.csv      # 26,898 titulares (2018-01-01 a 2022-05-01), 6 categorías, columnas categoria,titulo,href,fecha
  data_en.csv      # igual + columna 'title' traducida al inglés
  data_news.csv    # 11,927 titulares 2020-2021 traducidos
  data.xlsx        # 17,550 notas 2020-2021 con texto completo ('content')
  MONTO DE INTERVENCION.xlsx  # 219 días (28-dic-2020 a 10-nov-2021): Fecha, Monto de intervención (USD mm, SIN signo),
                              # Tipo de Cambio, tasa, label (1 = sube), TCVENTA, Precio, Volumen
paper/             # TRABAJO NUEVO (2026)
  code/gestion_scraper.py   # scraper v2 (ver abajo)
  code/replicacion_var.py   # replica el VAR de la tesis vs versión corregida
  resultados/replicacion_var/  # figuras y tablas ya generadas
  docs/                     # resultados, literatura, hoja de ruta
  data/                     # salidas del scraper (no versionar parciales)
```

## Hallazgos de la auditoría del código 2022 (septiembre 2026)
1. **Timing (crítico).** El archivo `/archivo/todas/{fecha}/` de Gestión solo listaba las ~25 últimas notas
   del día. En una muestra aleatoria de 400 titulares (dic-2020 a nov-2021) con hora recuperada:
   **95.5% se publicó después del cierre interbancario (13:30)**, mediana 18:52 hora Lima, 0 antes de las 9:00.
   La tesis emparejaba noticias nocturnas con el TC del mismo día → el sentimiento *describía* el movimiento.
2. El RandomForest de `iter.ipynb` predijo "sube" en los 54 días de test (accuracy 0.519 = tasa base, F1 macro 0.34).
3. El sentimiento VADER nunca entró al modelo de `iter.ipynb`.
4. VADER sobre traducción automática añade ruido (el propio notebook lo advierte).
5. El TC entró en niveles (ADF p = 0.63, no estacionario).
6. Intervención sin signo; no incluye swaps cambiarios (instrumento principal del BCRP en 2021).
7. Categorías Mundo/Internacional meten ruido (NBA, vinos eslovenos...).
8. El selector CSS del scraper viejo ya no funciona (Gestión añadió clases; el `try/except` lo oculta y devuelve vacío).

## Scraper v2 (`paper/code/gestion_scraper.py`)
Subcomandos (todos reanudables con checkpoint `.parcial.jsonl` + `.hechos.txt`):
- `listar --inicio --fin`: día completo vía API Arc del sitio
  (`/pf/api/v3/content/fetch/story-feed-by-section-and-date-v2`, paginación con `from`). Ej.: 113 notas el 1-jun-2023
  vs 25 del archivo. **Cobertura solo desde ~18-dic-2021.**
- `historico --entrada data/data_es.csv`: baja cada `href` y saca del JSON-LD `datePublished`, bajada, sección, keywords.
- `articulos`: texto completo (`articleBody` del JSON-LD).
- `alinear`: baja TC cierre venta 13:30 del BCRP (serie **PD04646PD**) y asigna cada nota al primer día cambiario
  cuyo cierre es posterior a su publicación. Columna `ventana` = `pre_apertura` | `intradia`; columna `republicada`
  (display_date vs first_publish_date > 24 h).
- Antes de correr: poner el correo real en la constante `UA`. Pausa ≥ 1 s, máx 4 workers. robots.txt permite `/archivo/` y la API.

## Resultados de la replicación (`paper/code/replicacion_var.py`)
Muestra 28-dic-2020 a 10-nov-2021, 217 obs, 2 rezagos (AIC). Corregido = timing t+1 + Δlog TC + exógenas
(Δlog DXY, ΔVIX, Δlog cobre, ΔEMBIG Perú, contemporáneas y t-1).
| Resultado | Valor |
|---|---|
| sent. nocturno(t) ~ r_t (ya ocurrido) | b = +0.045, p = 0.51 |
| r_{t+1} ~ sent. nocturno(t), estandarizado | **b = −0.173, p = 0.012** (signo esperado) |
| VAR corregido, sent → Δlog TC h0 | −0.06% (banda 90%: −0.13 a 0.00) |
| Granger sent → r (corregido) | p = 0.67 |
| Intervención, Cholesky de la tesis [sent, interv, TC] | +0.22–0.25% en h0 (simultaneidad) |
| Intervención, orden alt. [sent, r, interv] | **−0.21% acumulado a h5–h10, sig. 90%** |
| Proyección local intervención | +0.21% h0 → −0.43% h10 |
| Función de reacción implícita | 1 d.e. de depreciación → BCRP vende 26–37 USD mm |
Supuesto: montos = ventas de USD (lo usual en 2021). La muestra de horas de 400 titulares **no está en el repo**:
se regenera con el paso 1 de `docs/ROADMAP_PAPER.md`.

## Diseño del paper (acordado)
Título tentativo: *"¿Bueno para el sol o para el dólar? Sentimiento dirigido con LLMs y el tipo de cambio en Perú"*.
- RQ1: ¿LLMs en español explican/predicen Δlog PEN/USD mejor que VADER(traducido) y BERT en español?
- RQ2: ¿sentimiento **dirigido** (S_PE hacia Perú, S_US hacia USD/global) supera a polaridad única? Hipótesis β_PE < 0, β_US > 0.
- RQ3: ¿cuánto del resultado es look-ahead bias? (anonimización tipo Glasserman & Lin + ventana post-cutoff del modelo)
- Muestra principal 2022-2026 (cobertura completa vía API); 2018-2021 como robustez (solo notas nocturnas).
- Modelos: 0) traducción+VADER (tesis) 1) BETO/RoBERTa-BNE fine-tuned 2) LLM abierto (Llama/Qwen) zero/few-shot JSON
  3) mismo LLM con QLoRA 4) un LLM cerrado como techo.
- Gold set: 2,000–3,000 titulares, 2 anotadores, kappa de Cohen; etiquetas: relevancia TC, sent. Perú (−1/0/1),
  sent. USD/global (−1/0/1), tema (política, commodities, BCRP, Fed, fiscal, otro).
- Econometría: regresión r_{t+h} con HAC; proyecciones locales h=0..10; VARX con exógenas globales; identificación
  de intervención por función de reacción (sorpresa), heterocedasticidad o signos; EGARCH/vol. estocástica;
  pronóstico OOS vs paseo aleatorio (Diebold-Mariano, Clark-West, % dirección).
- Controles: intervención neta con signo (spot + swaps, BCRP), DXY, cobre, UST10Y, EMBIG Perú, VIX, CLP y COP.

## Coautores potenciales (PUCP)
- **Gabriel Rodríguez**: intervención y volatilidad cambiaria en Perú (Humala & Rodríguez 2010, AEL), vol. estocástica
  bayesiana, DSGE con intervención, modelos de conteo de frecuencia de intervención → identificación y volatilidad.
- **Julio Villavicencio** (Finanzas): incertidumbre política y mercados adaptativos en Perú (2026), AMH con ML (Heliyon 2025),
  instituciones/incertidumbre y ratings → marco financiero e incertidumbre política.
- **Luis Bendezú** (Finanzas): Econometría Financiera, seminarios de tesis; coautor con Rodríguez (JEFAS 2025) → econometría aplicada.

## Convenciones
- No modificar `thesis/` ni `data/` originales; todo lo nuevo en `paper/`.
- r = 100·Δlog(TC cierre 13:30) > 0 = depreciación del sol.
- Hora Lima = America/Lima (UTC−5, sin horario de verano).
- Semillas fijas; cada figura/tabla del paper debe generarse con un script en `paper/code/`.
- Commits pequeños y descriptivos; no subir datos scrapeados masivos ni API keys.

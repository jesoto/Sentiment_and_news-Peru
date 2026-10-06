# Resultados preliminares (septiembre 2026)

## 1. Auditoría del timing de las noticias
- Muestra aleatoria de 400 titulares de `data/data_en.csv` entre 28-dic-2020 y 10-nov-2021; horas recuperadas del JSON-LD
  de cada nota (`datePublished`).
- **95.5% publicados después de las 13:30** (cierre interbancario). Mediana 18:52, media 18:53 (d.e. 2.4 h).
- Distribución: 9:00-13:30 → 11 · 13:30-17:00 → 67 · 17:00-20:00 → 196 · 20:00-24:00 → 119 · antes de 9:00 → 0.
- 98.2% tiene fecha Lima = fecha del archivo (el desfase no viene de UTC sino del cierre del mercado).
- Ejemplo: "Activos peruanos caen tras avance de Pedro Castillo" se publicó el 7-jun-2021 a las 17:55. La tesis la asignaba
  al 7-jun; la regla correcta la asigna al 8-jun.
- Cobertura: el archivo da ~25 notas por día; la API da el día completo (p. ej. 113 notas el 1-jun-2023).

## 2. Replicación del VAR de la tesis vs versión corregida
Script: `paper/code/replicacion_var.py`. Salidas: `paper/resultados/replicacion_var/`.

| Especificación | Original (tesis) | Corregida |
|---|---|---|
| Variables | sentimiento, intervención, TC en **niveles** | sentimiento, intervención, **100·Δlog TC** |
| Fecha de la noticia | calendario (mismo día) | primer día con cierre 13:30 posterior |
| Exógenas | ninguna | Δlog DXY, ΔVIX, Δlog cobre, ΔEMBIG Perú (t, t−1) |
| Obs. / rezagos | 217 / 2 | 217 / 2 |

### Sentimiento
| Prueba | Resultado |
|---|---|
| sent_noche(t) ~ r_t (retorno ya ocurrido) | b = +0.045, p = 0.514 |
| r_{t+1} ~ sent_noche(t) + r_t (estandarizado, HC1) | **b = −0.173, p = 0.012** |
| Granger sent → TC (original) | F = 2.14, p = 0.118 |
| Granger sent → r (corregido) | F = 0.40, p = 0.667 |
| IRF corregida h0 / h1 | −0.060% / −0.070% (banda 90% h0: −0.128 a 0.001) |
| Proyección local h0 / h1 | −0.040% / −0.059% (no significativas) |

Lectura: con el timing correcto el signo es el esperado (buenas noticias → el sol se aprecia al día siguiente), pero
VADER sobre traducción es demasiado ruidoso para que el VAR lo detecte con fuerza. Esto motiva la medición con LLMs.

### Intervención (supuesto: montos = ventas de USD)
| Identificación | h0 | h1 | h5 | h10 |
|---|---|---|---|---|
| Cholesky tesis [sent, interv, TC] | +0.246% | +0.204% | +0.032% | +0.023% |
| Corregido [sent, interv, r], acumulado | +0.221% | +0.151% | +0.014% | +0.013% |
| **Orden alt. [sent, r, interv], acumulado** | 0.000 | **−0.086%** | **−0.211%** | **−0.212%** (sig. 90%) |
| Proyección local (acumulada) | +0.214% | +0.098% | −0.165% | −0.429% |

Lectura: el signo positivo de la tesis es simultaneidad (el BCRP vende cuando el dólar sube). Si el BCRP reacciona
dentro del día, la intervención aprecia el sol ~0.2% en una semana. Función de reacción implícita: 1 d.e. de depreciación
→ ventas de 26-37 USD mm en h0-h1.

### Estacionariedad (ADF)
TC nivel p = 0.628 · Δlog TC p = 0.000 · sentimiento p = 0.000 · intervención p = 0.000.

## 3. Limitaciones a resolver
- Horas reales solo para 400 titulares; el resto usa la regla "publicado tras el cierre" (validada al 95.5%).
- Intervención sin signo y sin swaps cambiarios.
- 217 días dominados por el ciclo electoral 2021.
- Un solo medio (Gestión) y solo titulares.

# Scraper v2 — Gestión + alineación cambiaria

```bash
pip install -r requirements.txt

# 1) 2022 → hoy: cobertura completa por día (API de contenido del sitio)
python gestion_scraper.py listar --inicio 2022-01-01 --fin 2026-09-28 --salida data/listado.csv

# 2) 2018 → 2021: recupera hora de publicación de tu corpus 2022 (columna href)
python gestion_scraper.py historico --entrada ../data/data_es.csv --salida data/historico.csv --workers 2

# 3) (opcional) texto completo
python gestion_scraper.py articulos --entrada data/listado.csv --salida data/articulos.csv --workers 2

# 4) Asignar cada nota al día cambiario (cierre 13:30, serie BCRP PD04646PD)
python gestion_scraper.py alinear --entrada data/listado.csv --entrada data/historico.csv --salida data/alineado.csv
```

Todo es reanudable: si se corta, corre el mismo comando y sigue donde quedó.

## Columnas clave de `alineado.csv`
| Columna | Significado |
|---|---|
| `fecha_pub_utc`, `ts_lima`, `hora_lima` | Primera publicación (no la fecha "display", que puede cambiar) |
| `fecha_cambiaria` | Primer día con cierre (13:30) posterior a la publicación |
| `ventana` | `pre_apertura`: entre el cierre previo y las 9:00 (predeterminada para r_t). `intradia`: durante la sesión |
| `republicada` | Nota antigua re-destacada por el sitio; excluir en la estimación principal |
| `fuente` | `api` (2022+) o `historico` (tu corpus 2018–2022) |

`tc_cierre_bcrp.csv` trae el TC de cierre y `r_log` (>0 = depreciación del sol).

## Limitaciones
- La API cubre desde ~dic-2021. Para 2018–2021 solo tienes las 25 notas nocturnas por día que capturó el scraper original: úsalo como muestra secundaria o de robustez.
- Pausa mínima de 1 s entre requests y máximo 4 workers. Uso académico; revisa los términos de uso del sitio antes de publicar datos.

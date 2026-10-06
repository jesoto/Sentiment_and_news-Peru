"""Paso 1.5: datos diarios de mercado -> paper/data/mercado.csv

BCRP (BCRPData): TC cierre 13:30, cobre, EMBIG Perú, operaciones cambiarias con signo (spot y swaps).
FRED: dólar amplio (DTWEXBGS), VIX, UST10Y.
Signo de intervención: positivo = BCRP VENDE USD (presiona a la apreciación del sol).
  interv_spot  = ventas spot - compras spot                 (PD37516TD - PD37515TD)
  interv_swap  = swaps venta pactado - swaps compra pactado (PD37521TD - PD37523TD)
  interv_neta  = interv_spot + interv_swap   (flujo pactado; los 'vencidos' son reversiones de contratos previos)
Pendiente: CLP y COP (sin serie diaria verificada en BCRP/FRED).

Uso: python paper/code/mercado.py [--inicio 2018-01-01] [--fin hoy] [--salida paper/data/mercado.csv]
"""
import argparse
import datetime as dt
import io
import json
import zipfile
from pathlib import Path

import pandas as pd
import requests

MESES = {"Ene": 1, "Feb": 2, "Mar": 3, "Abr": 4, "May": 5, "Jun": 6, "Jul": 7,
         "Ago": 8, "Set": 9, "Sep": 9, "Oct": 10, "Nov": 11, "Dic": 12}
BCRP = {
    "tc": "PD04646PD", "cobre": "PD04701XD", "embig_pe": "PD04709XD",
    "spot_compras": "PD37515TD", "spot_ventas": "PD37516TD",
    "swap_venta_pactado": "PD37521TD", "swap_venta_vencido": "PD37522TD",
    "swap_compra_pactado": "PD37523TD", "swap_compra_vencido": "PD37524TD",
}
FRED = {"dxy": "DTWEXBGS", "vix": "VIXCLS", "ust10y": "DGS10"}


def bcrp(serie: str, ini: str, fin: str) -> pd.Series:
    r = requests.get(f"https://estadisticas.bcrp.gob.pe/estadisticas/series/api/{serie}/json/{ini}/{fin}", timeout=60)
    r.raise_for_status()
    out = {}
    for p in json.loads(r.content.decode("latin1"))["periods"]:
        d, m, y = p["name"].split(".")
        try:
            out[pd.Timestamp(2000 + int(y), MESES[m], int(d))] = float(p["values"][0])
        except (ValueError, IndexError):
            pass  # 'n.d.'
    return pd.Series(out, name=serie).sort_index()


def fred(ids: list[str], ini: str, fin: str) -> pd.DataFrame:
    r = requests.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={','.join(ids)}&cosd={ini}&coed={fin}", timeout=60)
    r.raise_for_status()
    if r.content[:2] == b"PK":
        z = zipfile.ZipFile(io.BytesIO(r.content))
        frames = [pd.read_csv(z.open(n), parse_dates=["observation_date"], index_col=0) for n in z.namelist() if n.endswith(".csv")]
    else:
        frames = [pd.read_csv(io.StringIO(r.text), parse_dates=["observation_date"], index_col=0)]
    return pd.concat(frames, axis=1).apply(pd.to_numeric, errors="coerce")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inicio", default="2018-01-01")
    ap.add_argument("--fin", default=dt.date.today().isoformat())
    ap.add_argument("--salida", default="paper/data/mercado.csv", type=Path)
    a = ap.parse_args()

    df = pd.concat({k: bcrp(v, a.inicio, a.fin) for k, v in BCRP.items()}, axis=1)
    dias = df["tc"].dropna().index  # días cambiarios
    df = df.loc[dias]
    f = fred(list(FRED.values()), a.inicio, a.fin).rename(columns={v: k for k, v in FRED.items()})
    df = df.join(f.reindex(dias, method="ffill"))  # FRED: último dato disponible (rezago de huso/feriados EEUU)

    df["interv_spot"] = df["spot_ventas"] - df["spot_compras"]
    df["interv_swap"] = df["swap_venta_pactado"] - df["swap_compra_pactado"]
    df["interv_neta"] = df["interv_spot"] + df["interv_swap"]
    df.index.name = "fecha"
    a.salida.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(a.salida)
    print(df.describe().T[["count", "mean", "min", "max"]].round(2).to_string())


if __name__ == "__main__":
    main()

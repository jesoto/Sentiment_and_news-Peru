"""Figura: histograma de la hora de publicación (hora Lima) de la muestra de 400 titulares, con el cierre 13:30.

Uso: python paper/code/figura_timing.py [--horas paper/data/muestra400_horas.csv] [--salida paper/resultados/timing]
"""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

LIMA = "America/Lima"
CIERRE = 13.5


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--horas", default="paper/data/muestra400_horas.csv", type=Path)
    ap.add_argument("--salida", default="paper/resultados/timing", type=Path)
    a = ap.parse_args()

    h = pd.read_csv(a.horas)
    h = h[h["estado"] == 200]
    t = pd.to_datetime(h["fecha_pub_utc"], utc=True, format="ISO8601").dt.tz_convert(LIMA)
    x = t.dt.hour + t.dt.minute / 60
    post = (x > CIERRE).mean()
    med = x.median()

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(x, bins=np.arange(0, 25, 1), color="#4c72b0", edgecolor="white")
    ax.axvline(CIERRE, color="#c44e52", lw=2, ls="--")
    ax.text(CIERRE + 0.2, ax.get_ylim()[1] * 0.95, "Cierre 13:30", color="#c44e52", va="top")
    ax.set_xlim(0, 24)
    ax.set_xticks(range(0, 25, 3))
    ax.set_xlabel("Hora de publicación (Lima)")
    ax.set_ylabel("Titulares")
    ax.set_title(f"{post:.1%} de {len(x)} titulares se publicó tras el cierre (mediana {int(med)}:{int(med % 1 * 60):02d})")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()

    a.salida.mkdir(parents=True, exist_ok=True)
    fig.savefig(a.salida / "hist_hora_publicacion.png", dpi=200)
    tabla = pd.cut(x, [0, 9, 13.5, 17, 20, 24], right=False,
                   labels=["<9:00", "9:00-13:30", "13:30-17:00", "17:00-20:00", "20:00-24:00"]).value_counts().sort_index()
    tabla.rename("n").to_csv(a.salida / "tabla_horas.csv")
    print(f"n={len(x)} post-cierre={post:.3f} mediana={med:.2f}h")


if __name__ == "__main__":
    main()

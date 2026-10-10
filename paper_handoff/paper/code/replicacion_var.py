#!/usr/bin/env python3
"""
Replicación del VAR de la tesis (2022) vs versión corregida.

Muestra: 28-dic-2020 a 10-nov-2021 (la ventana de tu archivo 'MONTO DE INTERVENCION.xlsx').

ORIGINAL (como en la tesis):
  - Sentimiento = promedio diario del compound de VADER sobre titulares traducidos, por fecha calendario.
  - Se une con el TC por la misma fecha (las noticias del fin de semana se pierden).
  - VAR en niveles: [sentimiento, intervención, TC], Cholesky en ese orden.

CORREGIDO:
  1. Timing: cada titular pasa al primer día cambiario cuyo cierre (13:30) es posterior a su publicación.
     Se usa la hora real cuando se recuperó; si no, la regla "publicado tras el cierre" (validada en una
     muestra de 400 titulares). Así el sentimiento es predeterminado respecto de r_t.
  2. TC en variación logarítmica diaria (cierre 13:30, BCRP PD04646PD), no en niveles.
  3. Bloque exógeno de economía pequeña y abierta: Δlog DXY, ΔVIX, Δlog cobre, ΔEMBIG Perú (t y t-1).
  4. Robustez: orden alternativo (intervención reacciona dentro del día) y proyecciones locales.
  5. Prueba de causalidad inversa: ¿el sentimiento "nocturno" de t explica r_t (ya ocurrido)?

Uso:
  python replicacion_var.py --repo ../Sentiment_and_news-Peru --horas ts/historico_muestra.csv --salida resultados
"""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
import statsmodels.api as sm
from statsmodels.tsa.api import VAR
from statsmodels.tsa.stattools import adfuller
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

INI, FIN = "2020-12-28", "2021-11-10"
LIMA = ZoneInfo("America/Lima")
MESES = {"Ene": 1, "Feb": 2, "Mar": 3, "Abr": 4, "May": 5, "Jun": 6, "Jul": 7,
         "Ago": 8, "Set": 9, "Sep": 9, "Oct": 10, "Nov": 11, "Dic": 12}
H = 10  # horizonte de impulso-respuesta (días cambiarios)


# ----------------------------------------------------------------------------- datos externos
def bcrp(serie: str, ini: str, fin: str) -> pd.Series:
    r = requests.get(f"https://estadisticas.bcrp.gob.pe/estadisticas/series/api/{serie}/json/{ini}/{fin}",
                     timeout=60)
    datos = json.loads(r.content.decode("latin1"))
    out = {}
    for p in datos["periods"]:
        d, m, y = p["name"].split(".")
        try:
            out[pd.Timestamp(2000 + int(y), MESES[m], int(d))] = float(p["values"][0])
        except (ValueError, IndexError):
            pass
    return pd.Series(out, name=serie).sort_index()


def fred(ids: list[str], ini: str, fin: str) -> pd.DataFrame:
    import io
    import zipfile
    r = requests.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={','.join(ids)}&cosd={ini}&coed={fin}",
                     timeout=60)
    frames = []
    if r.content[:2] == b"PK":  # varias series con distinta frecuencia vienen en un zip
        z = zipfile.ZipFile(io.BytesIO(r.content))
        for n in z.namelist():
            if n.endswith(".csv"):
                frames.append(pd.read_csv(z.open(n), parse_dates=["observation_date"], index_col=0))
    else:
        frames.append(pd.read_csv(io.StringIO(r.text), parse_dates=["observation_date"], index_col=0))
    df = pd.concat(frames, axis=1).apply(pd.to_numeric, errors="coerce")
    return df


# ----------------------------------------------------------------------------- construcción
def construir(repo: Path, ruta_horas: Path | None):
    # Titulares traducidos (tu pipeline original) + VADER
    tit = pd.read_csv(repo / "data" / "data_en.csv")
    tit = tit[(tit.fecha >= "2020-12-26") & (tit.fecha <= FIN)].copy()
    sia = SentimentIntensityAnalyzer()
    tit["vader"] = tit["title"].astype(str).map(lambda s: sia.polarity_scores(s)["compound"])

    interv = pd.read_excel(repo / "data" / "MONTO DE INTERVENCION.xlsx")
    interv["Fecha"] = pd.to_datetime(interv["Fecha"])
    interv = interv.set_index("Fecha")

    # Mercado
    tc = bcrp("PD04646PD", "2020-12-01", FIN).rename("tc")
    cobre = bcrp("PD04701XD", "2020-12-01", FIN).rename("cobre")
    embig = bcrp("PD04709XD", "2020-12-01", FIN).rename("embig")
    fr = fred(["DTWEXBGS", "VIXCLS"], "2020-12-01", FIN).rename(columns={"DTWEXBGS": "dxy", "VIXCLS": "vix"})
    dias = tc.index  # días cambiarios reales

    # ---------------- ORIGINAL: fecha calendario, mismo día
    s_cal = tit.groupby(pd.to_datetime(tit.fecha))["vader"].mean().rename("sent")
    orig = pd.concat([s_cal, interv["Monto de intervención"].rename("interv"),
                      interv["Tipo de Cambio"].rename("tc_nivel")], axis=1, join="inner").dropna()

    # ---------------- CORREGIDO: fecha cambiaria
    horas = {}
    if ruta_horas and ruta_horas.exists():
        h = pd.read_csv(ruta_horas)
        h = h[h.get("estado", 200) == 200]
        horas = dict(zip(h["url"].str.replace("https://gestion.pe", "", regex=False),
                         pd.to_datetime(h["fecha_pub_utc"], utc=True, format="ISO8601")))
    cierres = (pd.Series(dias) + pd.Timedelta(hours=13, minutes=30)).dt.tz_localize(LIMA)

    def fecha_cambiaria(fila):
        ts = horas.get(fila.href)
        if ts is None or pd.isna(ts):
            # Regla validada: el archivo solo mostraba las notas nocturnas → publicadas tras el cierre
            ts = pd.Timestamp(fila.fecha + " 20:00", tz=LIMA)
        i = cierres.searchsorted(ts.tz_convert(LIMA), side="right")
        return dias[i] if i < len(dias) else pd.NaT

    tit["fecha_cambiaria"] = tit.apply(fecha_cambiaria, axis=1)
    s_camb = tit.dropna(subset=["fecha_cambiaria"]).groupby("fecha_cambiaria")["vader"].mean().rename("sent")

    mk = pd.concat([tc, cobre, embig], axis=1).join(fr, how="left").reindex(dias).ffill()
    exo = pd.DataFrame({
        "d_dxy": 100 * np.log(mk["dxy"]).diff(),
        "d_vix": mk["vix"].diff(),
        "d_cobre": 100 * np.log(mk["cobre"]).diff(),
        "d_embig": mk["embig"].diff(),
    })
    exo = pd.concat([exo, exo.shift(1).add_suffix("_l1")], axis=1)
    corr = pd.concat([s_camb, interv["Monto de intervención"].rename("interv"),
                      (100 * np.log(tc).diff()).rename("r")], axis=1).reindex(dias)
    corr["interv"] = corr["interv"].fillna(0)
    datos_c = pd.concat([corr, exo], axis=1).loc[INI:FIN].dropna()

    # Para la prueba de causalidad inversa: sentimiento calendario + retorno del mismo día
    rev = pd.concat([s_cal.rename("sent_noche_t"), (100 * np.log(tc).diff()).rename("r_t")],
                    axis=1, join="inner").loc[INI:FIN]
    rev["r_t1"] = (100 * np.log(tc).diff()).shift(-1).reindex(rev.index)
    return tit, orig, datos_c, rev


# ----------------------------------------------------------------------------- modelos
def var_irf(df, orden, exog=None, maxlags=5, acumular=False, repl=1000, semilla=7):
    modelo = VAR(df[orden], exog=exog)
    p = max(1, modelo.select_order(maxlags).aic)
    res = modelo.fit(p)
    irf = res.irf(H)
    np.random.seed(semilla)
    if acumular:
        centro = irf.orth_cum_effects
        lo, hi = irf.cum_errband_mc(orth=True, repl=repl, signif=0.1, seed=semilla)
    else:
        centro = irf.orth_irfs
        lo, hi = irf.errband_mc(orth=True, repl=repl, signif=0.1, seed=semilla)
    return res, p, centro, lo, hi


def proyecciones_locales(df, choque, controles, hmax=H):
    """Respuesta acumulada de log TC (r_t + ... + r_{t+h}) a 1 d.e. de 'choque'. HAC Newey-West."""
    out = []
    z = df.copy()
    z[choque] = (z[choque] - z[choque].mean()) / z[choque].std()
    for h in range(hmax + 1):
        y = sum(z["r"].shift(-k) for k in range(h + 1))
        X = pd.concat([z[[choque]], z[controles], z["r"].shift(1).rename("r_l1"),
                       z["r"].shift(2).rename("r_l2"), z[choque].shift(1).rename("choque_l1")], axis=1)
        d = pd.concat([y.rename("y"), X], axis=1).dropna()
        m = sm.OLS(d["y"], sm.add_constant(d.drop(columns="y"))).fit(cov_type="HAC",
                                                                    cov_kwds={"maxlags": h + 1})
        b, se = m.params[choque], m.bse[choque]
        out.append({"h": h, "b": b, "lo": b - 1.645 * se, "hi": b + 1.645 * se})
    return pd.DataFrame(out)


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, type=Path)
    ap.add_argument("--horas", type=Path)
    ap.add_argument("--salida", default="resultados", type=Path)
    a = ap.parse_args()
    a.salida.mkdir(parents=True, exist_ok=True)

    tit, orig, dc, rev = construir(a.repo, a.horas)
    txt = []

    # --- diagnóstico de estacionariedad
    for nombre, s in [("TC nivel (original)", orig["tc_nivel"]), ("r = Δlog TC (corregido)", dc["r"]),
                      ("sentimiento", dc["sent"]), ("intervención", dc["interv"])]:
        txt.append(f"ADF {nombre}: p = {adfuller(s.dropna(), autolag='AIC')[1]:.3f}")

    # --- causalidad inversa: titulares nocturnos de t vs r_t (ya ocurrido) y r_{t+1}
    rv = rev.dropna()
    z = (rv - rv.mean()) / rv.std()
    m0 = sm.OLS(z["sent_noche_t"], sm.add_constant(z[["r_t"]])).fit(cov_type="HC1")
    m1 = sm.OLS(z["r_t1"], sm.add_constant(z[["sent_noche_t", "r_t"]])).fit(cov_type="HC1")
    txt += ["", "CAUSALIDAD INVERSA (variables estandarizadas)",
            f"  sent_noche_t ~ r_t      : b = {m0.params['r_t']:+.3f}  (p = {m0.pvalues['r_t']:.3f})",
            f"  r_t+1 ~ sent_noche_t    : b = {m1.params['sent_noche_t']:+.3f}  (p = {m1.pvalues['sent_noche_t']:.3f})"]

    # --- ORIGINAL
    ro, po, ci, li, hi_ = var_irf(orig, ["sent", "interv", "tc_nivel"])
    # --- CORREGIDO (principal y orden alternativo)
    exo_cols = [c for c in dc.columns if c.startswith("d_")]
    rc, pc, cc, lc, hc = var_irf(dc, ["sent", "interv", "r"], exog=dc[exo_cols], acumular=True)
    ra, pa, ca, la, ha = var_irf(dc, ["sent", "r", "interv"], exog=dc[exo_cols], acumular=True)
    lp_s = proyecciones_locales(dc, "sent", ["interv"] + exo_cols)
    lp_i = proyecciones_locales(dc, "interv", exo_cols + ["sent"])

    txt += ["", f"Observaciones: original {ro.nobs} (rezagos {po}) | corregido {rc.nobs} (rezagos {pc})",
            f"Titulares en la ventana: {len(tit)}; días calendario con noticias: {tit.fecha.nunique()}"]
    for nombre, res in [("ORIGINAL", ro), ("CORREGIDO", rc)]:
        try:
            g = res.test_causality(res.names[-1], ["sent"], kind="f")
            txt.append(f"Granger sent → {res.names[-1]} ({nombre}): F = {g.test_statistic:.2f}, p = {g.pvalue:.3f}")
        except Exception:  # noqa: BLE001
            pass

    def fila(nombre, arr, lo, hi, i_resp, i_choque, esc=1.0):
        return {"modelo": nombre, **{f"h{h}": round(esc * arr[h, i_resp, i_choque], 4) for h in (0, 1, 5, 10)},
                "sig90_h1": bool(lo[1, i_resp, i_choque] > 0 or hi[1, i_resp, i_choque] < 0)}

    # Original: respuesta del TC en soles → pasar a % para comparar con el corregido
    esc_o = 100 / orig["tc_nivel"].mean()
    tabla = pd.DataFrame([
        fila("Original: TC(%) ante sentimiento", ci, li, hi_, 2, 0, esc_o),
        fila("Original: TC(%) ante intervención", ci, li, hi_, 2, 1, esc_o),
        fila("Corregido: log TC acum.(%) ante sentimiento", cc, lc, hc, 2, 0),
        fila("Corregido: log TC acum.(%) ante intervención", cc, lc, hc, 2, 1),
        fila("Alt. orden: log TC acum.(%) ante intervención", ca, la, ha, 1, 2),
    ])
    tabla.to_csv(a.salida / "tabla_irf.csv", index=False)
    txt += ["", tabla.to_string(index=False)]

    # --- figura
    hs = np.arange(H + 1)
    fig, ax = plt.subplots(2, 2, figsize=(11, 7.5), sharex=True)
    paneles = [
        (ax[0, 0], "Original: TC (%) ante choque de sentimiento", esc_o * ci[:, 2, 0], esc_o * li[:, 2, 0], esc_o * hi_[:, 2, 0]),
        (ax[0, 1], "Original: TC (%) ante choque de intervención", esc_o * ci[:, 2, 1], esc_o * li[:, 2, 1], esc_o * hi_[:, 2, 1]),
        (ax[1, 0], "Corregido: log TC acumulado (%) ante sentimiento", cc[:, 2, 0], lc[:, 2, 0], hc[:, 2, 0]),
        (ax[1, 1], "Corregido: log TC acumulado (%) ante intervención", cc[:, 2, 1], lc[:, 2, 1], hc[:, 2, 1]),
    ]
    for axx, titulo, c, lo, hi in paneles:
        axx.fill_between(hs, lo, hi, alpha=0.25, color="#4C72B0", label="VAR, banda 90%")
        axx.plot(hs, c, color="#4C72B0", lw=2)
        axx.axhline(0, color="k", lw=0.8)
        axx.set_title(titulo, fontsize=10)
    ax[1, 1].plot(hs, ca[:, 1, 2], color="#55A868", lw=2, label="VAR orden alt. (r antes que intervención)")
    ax[1, 1].fill_between(hs, la[:, 1, 2], ha[:, 1, 2], alpha=0.15, color="#55A868")
    for axx, lp in [(ax[1, 0], lp_s), (ax[1, 1], lp_i)]:
        axx.plot(lp.h, lp.b, color="#DD8452", lw=1.6, ls="--", label="Proyección local")
        axx.fill_between(lp.h, lp.lo, lp.hi, alpha=0.12, color="#DD8452")
        axx.legend(fontsize=8, loc="best")
    for axx in ax[1]:
        axx.set_xlabel("días cambiarios")
    fig.suptitle("VAR de la tesis vs VAR corregido — choque de 1 d.e. (dic-2020 a nov-2021)", fontsize=12)
    fig.tight_layout()
    fig.savefig(a.salida / "irf_original_vs_corregido.png", dpi=160)

    # figura de causalidad inversa
    fig2, ax2 = plt.subplots(1, 2, figsize=(10, 4), sharey=True)
    for axx, col, t in [(ax2[0], "r_t", "Retorno del MISMO día (ya ocurrido)"),
                        (ax2[1], "r_t1", "Retorno del día SIGUIENTE")]:
        axx.scatter(rv[col], rv["sent_noche_t"], s=12, alpha=0.6)
        b = np.polyfit(rv[col], rv["sent_noche_t"], 1)
        xs = np.linspace(rv[col].min(), rv[col].max(), 50)
        axx.plot(xs, np.polyval(b, xs), color="#C44E52")
        axx.set_title(f"{t}\ncorr = {rv[col].corr(rv['sent_noche_t']):+.2f}", fontsize=10)
        axx.set_xlabel("Δlog TC (%)")
    ax2[0].set_ylabel("Sentimiento VADER de titulares nocturnos (t)")
    fig2.tight_layout()
    fig2.savefig(a.salida / "causalidad_inversa.png", dpi=160)

    (a.salida / "resumen.txt").write_text("\n".join(txt), encoding="utf-8")
    print("\n".join(txt))


if __name__ == "__main__":
    main()

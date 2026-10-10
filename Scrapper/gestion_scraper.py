#!/usr/bin/env python3
"""
Scraper v2 de Gestión (gestion.pe) para el paper de sentimiento y tipo de cambio.

Qué resuelve respecto a la versión 2022:
  1. Cobertura completa del día (el archivo /archivo/todas/ solo mostraba las 25 últimas notas).
  2. Hora exacta de publicación (first_publish_date), en UTC y hora Lima.
  3. Asignación de cada nota al día cambiario correcto según el cierre de las 13:30 (BCRP).
  4. Recuperación de horas para tu corpus histórico 2018-2022 a partir de los href.
  5. Reanudable: si se corta, vuelve a correr el mismo comando y continúa donde quedó.

Subcomandos:
  listar     Notas por día desde la API de contenido de Arc (cobertura desde ~dic-2021).
  historico  Recupera hora/bajada/sección de un CSV con columna 'href' (tu data_es.csv).
  articulos  Descarga el texto completo de las notas de un CSV con columna 'url' (opcional).
  alinear    Descarga el TC de cierre del BCRP y asigna cada nota a su día cambiario.

Ejemplos:
  python gestion_scraper.py listar --inicio 2022-01-01 --fin 2026-09-28 --salida data/listado.csv
  python gestion_scraper.py historico --entrada ../data/data_es.csv --salida data/historico.csv --workers 2
  python gestion_scraper.py alinear --entrada data/listado.csv --entrada data/historico.csv --salida data/alineado.csv

Requisitos: pip install requests pandas
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import json
import logging
import math
import re
import threading
import time
import urllib.parse
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE = "https://gestion.pe"
API = BASE + "/pf/api/v3/content/fetch/story-feed-by-section-and-date-v2"
BCRP_API = "https://estadisticas.bcrp.gob.pe/estadisticas/series/api/{serie}/json/{ini}/{fin}"
SERIE_TC_CIERRE = "PD04646PD"  # TC Cierre Venta - 01:30 PM (S/ por US$)
LIMA = ZoneInfo("America/Lima")
UTC = ZoneInfo("UTC")
UA = "Mozilla/5.0 (research scraper; contacto: jesus.soto@pucp.edu.pe)"  # pon tu correo

CAMPOS_API = (
    "&_sourceInclude=_id,canonical_url,websites.gestion.website_url,headlines.basic,"
    "subheadlines.basic,display_date,first_publish_date,content_restrictions.content_code,"
    "taxonomy.sections.path,taxonomy.sections.name,taxonomy.tags.text,"
    "websites.gestion.website_section.path,websites.gestion.website_section.name"
)

COLUMNAS = [
    "id", "url", "titular", "bajada", "seccion_path", "seccion", "tags",
    "fecha_pub_utc", "fecha_display_utc", "restriccion", "fuente",
]

log = logging.getLogger("gestion")


# --------------------------------------------------------------------------- utilidades
class Cliente:
    """Sesión HTTP con reintentos y pausa mínima entre requests (thread-safe)."""

    def __init__(self, pausa: float = 1.0):
        self.pausa = pausa
        self._lock = threading.Lock()
        self._ultimo = 0.0
        self.s = requests.Session()
        self.s.headers["User-Agent"] = UA
        retry = Retry(total=5, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504],
                      allowed_methods=["GET"])
        self.s.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=8))

    def get(self, url: str, **kw) -> requests.Response:
        with self._lock:
            espera = self.pausa - (time.monotonic() - self._ultimo)
            if espera > 0:
                time.sleep(espera)
            self._ultimo = time.monotonic()
        return self.s.get(url, timeout=30, **kw)


class Checkpoint:
    """Escribe resultados en JSONL a medida que avanza y recuerda qué claves ya se hicieron."""

    def __init__(self, ruta_salida: Path, clave: str):
        self.jsonl = ruta_salida.with_suffix(".parcial.jsonl")
        self.hechos_path = ruta_salida.with_suffix(".hechos.txt")
        self.clave = clave
        self._lock = threading.Lock()
        self.hechos = set()
        if self.hechos_path.exists():
            self.hechos = set(self.hechos_path.read_text(encoding="utf-8").split())

    def guardar(self, clave: str, filas: list[dict]):
        with self._lock:
            with self.jsonl.open("a", encoding="utf-8") as f:
                for fila in filas:
                    f.write(json.dumps(fila, ensure_ascii=False) + "\n")
            with self.hechos_path.open("a", encoding="utf-8") as f:
                f.write(clave + "\n")
            self.hechos.add(clave)

    def a_dataframe(self) -> pd.DataFrame:
        if not self.jsonl.exists():
            return pd.DataFrame()
        return pd.read_json(self.jsonl, lines=True, dtype=False)


def fechas(inicio: str, fin: str) -> list[str]:
    d0, d1 = dt.date.fromisoformat(inicio), dt.date.fromisoformat(fin)
    return [(d0 + dt.timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]


def url_absoluta(href: str) -> str:
    href = str(href).strip()
    return href if href.startswith("http") else BASE + (href if href.startswith("/") else "/" + href)


def exportar(df: pd.DataFrame, salida: Path, clave: str):
    if df.empty:
        log.warning("No hay filas para exportar.")
        return
    df = df.drop_duplicates(subset=[clave], keep="last")
    salida.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(salida, index=False, encoding="utf-8-sig")
    log.info("Guardado %s (%d filas)", salida, len(df))


# --------------------------------------------------------------------------- 1) listar
def _fila_api(e: dict) -> dict:
    web = e.get("websites", {}).get("gestion", {})
    sec = web.get("website_section", {}) or {}
    return {
        "id": e.get("_id"),
        "url": url_absoluta(web.get("website_url") or e.get("canonical_url") or ""),
        "titular": (e.get("headlines") or {}).get("basic"),
        "bajada": (e.get("subheadlines") or {}).get("basic"),
        "seccion_path": sec.get("path"),
        "seccion": sec.get("name"),
        "tags": "|".join(t.get("text", "") for t in (e.get("taxonomy") or {}).get("tags", []) or []),
        # first_publish_date es la hora real de primera publicación; display_date puede cambiar.
        "fecha_pub_utc": e.get("first_publish_date") or e.get("display_date"),
        "fecha_display_utc": e.get("display_date"),
        "restriccion": (e.get("content_restrictions") or {}).get("content_code"),
        "fuente": "api",
    }


def listar_dia(cli: Cliente, fecha: str, tam: int = 100) -> list[dict]:
    filas, desde, total = [], 0, None
    while total is None or desde < total:
        q = {"date": fecha, "excludedSections": "", "includedFields": CAMPOS_API,
             "section": "/", "size": str(tam), "from": str(desde)}
        url = f"{API}?query={urllib.parse.quote(json.dumps(q))}&_website=gestion"
        r = cli.get(url)
        r.raise_for_status()
        data = r.json()
        total = int(data.get("count") or 0)
        elementos = data.get("content_elements") or []
        if not elementos:
            break
        filas += [_fila_api(e) for e in elementos]
        desde += len(elementos)
    return filas


def cmd_listar(a):
    cli, salida = Cliente(a.pausa), Path(a.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    ck = Checkpoint(salida, "fecha")
    pendientes = [f for f in fechas(a.inicio, a.fin) if f not in ck.hechos]
    log.info("Días pendientes: %d", len(pendientes))
    vacios = 0
    for i, f in enumerate(pendientes, 1):
        try:
            filas = listar_dia(cli, f)
        except Exception as ex:  # noqa: BLE001
            log.error("%s: %s (se reintentará en la próxima corrida)", f, ex)
            continue
        vacios += not filas
        ck.guardar(f, filas)
        if i % 25 == 0 or i == len(pendientes):
            log.info("%d/%d días | último %s: %d notas", i, len(pendientes), f, len(filas))
    if vacios:
        log.warning("%d días sin notas. La API cubre desde ~dic-2021; antes usa 'historico'.", vacios)
    exportar(ck.a_dataframe(), salida, "url")


# --------------------------------------------------------------------------- 2) historico / articulos
_JSONLD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


def parsear_articulo(html: str, con_texto: bool) -> dict:
    """Extrae metadatos del JSON-LD NewsArticle; usa regex como respaldo."""
    art = {}
    for m in _JSONLD.finditer(html):
        try:
            j = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        for it in j if isinstance(j, list) else [j]:
            if isinstance(it, dict) and "NewsArticle" in str(it.get("@type")):
                art = it
                break
        if art:
            break
    pub = art.get("datePublished")
    if not pub:
        m = re.search(r'"first_publish_date":"([^"]+)"', html) or re.search(r'"display_date":"([^"]+)"', html)
        pub = m.group(1) if m else None
    kw = art.get("keywords")
    if isinstance(kw, list):
        kw = "|".join(map(str, kw))
    fila = {
        "titular": art.get("headline"),
        "bajada": art.get("description"),
        "seccion": art.get("articleSection"),
        "tags": kw,
        "fecha_pub_utc": pub,
        "fecha_mod_utc": art.get("dateModified"),
        "restriccion": None if art.get("isAccessibleForFree") is None
        else ("libre" if str(art.get("isAccessibleForFree")).lower() == "true" else "restringido"),
    }
    if con_texto:
        fila["cuerpo"] = art.get("articleBody")
    return fila


def _procesar_urls(a, df_in: pd.DataFrame, col_url: str, fuente: str, con_texto: bool):
    cli, salida = Cliente(a.pausa), Path(a.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    ck = Checkpoint(salida, "url")
    df_in = df_in.copy()
    df_in["url"] = df_in[col_url].map(url_absoluta)
    df_in = df_in.drop_duplicates("url")
    pendientes = df_in[~df_in["url"].isin(ck.hechos)]
    log.info("URLs pendientes: %d de %d", len(pendientes), len(df_in))
    extra_cols = [c for c in df_in.columns if c not in ("url", col_url)]

    def tarea(fila: dict):
        url = fila["url"]
        try:
            r = cli.get(url)
            if r.status_code in (404, 410):
                return url, [{"url": url, "estado": r.status_code, "fuente": fuente}]
            r.raise_for_status()
            datos = parsear_articulo(r.text, con_texto)
            if fuente == "historico":
                # Columnas originales de tu CSV (categoria, titulo, fecha...) con prefijo orig_
                base = {f"orig_{c}": fila.get(c) for c in extra_cols}
                return url, [base | datos | {"url": url, "estado": 200, "fuente": fuente}]
            # 'articulos': conserva lo que ya venía del listado y solo completa campos vacíos
            base = {c: fila.get(c) for c in extra_cols}
            for k, v in datos.items():
                if k == "cuerpo" or base.get(k) in (None, "") or pd.isna(base.get(k)):
                    base[k] = v
            return url, [base | {"url": url, "estado": 200}]
        except Exception as ex:  # noqa: BLE001
            log.error("%s: %s", url, ex)
            return None, []

    hechos = 0
    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        for url, filas in ex.map(tarea, pendientes.to_dict("records")):
            if url:
                ck.guardar(url, filas)
                hechos += 1
                if hechos % 100 == 0:
                    log.info("%d/%d notas", hechos, len(pendientes))
    exportar(ck.a_dataframe(), salida, "url")


def cmd_historico(a):
    df = pd.read_csv(a.entrada, dtype=str)
    df = df.drop(columns=[c for c in df.columns if c.startswith("Unnamed")])
    if "href" not in df.columns:
        raise SystemExit("El CSV debe tener una columna 'href'.")
    _procesar_urls(a, df, "href", "historico", a.con_texto)


def cmd_articulos(a):
    df = pd.read_csv(a.entrada, dtype=str)
    _procesar_urls(a, df, "url", "articulos", True)


# --------------------------------------------------------------------------- 3) alinear
_MESES = {"Ene": 1, "Feb": 2, "Mar": 3, "Abr": 4, "May": 5, "Jun": 6, "Jul": 7,
          "Ago": 8, "Set": 9, "Sep": 9, "Oct": 10, "Nov": 11, "Dic": 12}


def tc_bcrp(inicio: str, fin: str, serie: str = SERIE_TC_CIERRE) -> pd.DataFrame:
    """TC de cierre (13:30) del BCRP. Solo días con dato = días cambiarios."""
    r = requests.get(BCRP_API.format(serie=serie, ini=inicio, fin=fin), timeout=60,
                     headers={"User-Agent": UA})
    r.raise_for_status()
    filas = []
    for p in r.json().get("periods", []):
        d, m, y = p["name"].split(".")
        try:
            v = float(p["values"][0])
        except (ValueError, IndexError):
            continue  # 'n.d.' = sin cotización (feriado o fin de semana)
        filas.append({"fecha": dt.date(2000 + int(y), _MESES[m], int(d)), "tc_cierre": v})
    tc = pd.DataFrame(filas).sort_values("fecha").reset_index(drop=True)
    tc["r_log"] = (tc["tc_cierre"].apply(math.log)).diff()  # >0 = depreciación del sol
    return tc


def alinear(notas: pd.DataFrame, tc: pd.DataFrame, cierre: str, apertura: str) -> pd.DataFrame:
    """
    Asigna cada nota al primer día cambiario cuyo cierre (13:30 Lima) ocurre DESPUÉS de su publicación.
      ventana = 'pre_apertura' : publicada entre el cierre previo y la apertura (predeterminada para r_t)
      ventana = 'intradia'     : publicada durante la sesión (puede reaccionar al propio movimiento)
    """
    h_c, m_c = map(int, cierre.split(":"))
    h_a, m_a = map(int, apertura.split(":"))
    dias = pd.to_datetime(tc["fecha"])
    cierres = (dias + pd.Timedelta(hours=h_c, minutes=m_c)).dt.tz_localize(LIMA)
    aperturas = (dias + pd.Timedelta(hours=h_a, minutes=m_a)).dt.tz_localize(LIMA)

    n = notas.copy()
    n["ts_utc"] = pd.to_datetime(n["fecha_pub_utc"], utc=True, errors="coerce", format="ISO8601")
    n = n.dropna(subset=["ts_utc"])
    n["ts_lima"] = n["ts_utc"].dt.tz_convert(LIMA)
    idx = cierres.searchsorted(n["ts_lima"], side="right")  # primer cierre estrictamente posterior
    fuera = idx >= len(cierres)
    n = n[~fuera].copy()
    idx = idx[~fuera]
    n["fecha_cambiaria"] = tc["fecha"].values[idx]
    n["ventana"] = ["pre_apertura" if t < aperturas.iloc[i] else "intradia"
                    for t, i in zip(n["ts_lima"], idx)]
    # Notas antiguas que el sitio vuelve a destacar: la API las lista por display_date,
    # pero su información es de su primera publicación. Márcalas para excluirlas si quieres.
    if "fecha_display_utc" in n:
        disp = pd.to_datetime(n["fecha_display_utc"], utc=True, errors="coerce", format="ISO8601")
        n["republicada"] = (disp - n["ts_utc"]).abs() > pd.Timedelta(hours=24)
    n["fecha_lima"] = n["ts_lima"].dt.date
    n["hora_lima"] = n["ts_lima"].dt.strftime("%H:%M")
    n["ts_lima"] = n["ts_lima"].dt.strftime("%Y-%m-%d %H:%M:%S")
    return n.drop(columns=["ts_utc"])


def cmd_alinear(a):
    notas = pd.concat([pd.read_csv(p, dtype=str) for p in a.entrada], ignore_index=True)
    if "estado" in notas:
        notas = notas[notas["estado"].isin([None, "200", "200.0"]) | notas["estado"].isna()]
    notas = notas.drop_duplicates("url", keep="first")
    ts = pd.to_datetime(notas["fecha_pub_utc"], utc=True, errors="coerce", format="ISO8601")
    ini = (ts.min() - pd.Timedelta(days=10)).date().isoformat()
    fin = (ts.max() + pd.Timedelta(days=10)).date().isoformat()
    log.info("Descargando TC cierre BCRP %s → %s", ini, fin)
    tc = tc_bcrp(ini, fin)
    out = alinear(notas, tc, a.cierre, a.apertura)
    salida = Path(a.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(salida, index=False, encoding="utf-8-sig")
    tc.to_csv(salida.with_name("tc_cierre_bcrp.csv"), index=False)
    resumen = out.groupby("ventana").size().to_dict()
    tarde = (pd.to_datetime(out["fecha_cambiaria"]) > pd.to_datetime(out["fecha_lima"])).mean()
    log.info("Guardado %s (%d notas) | por ventana: %s", salida, len(out), resumen)
    log.info("%.1f%% de las notas pasan al día cambiario siguiente a su fecha calendario.", 100 * tarde)


# --------------------------------------------------------------------------- CLI
def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--pausa", type=float, default=1.0, help="segundos mínimos entre requests (default 1.0)")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("listar", help="notas por día desde la API (desde ~dic-2021)")
    s.add_argument("--inicio", required=True)
    s.add_argument("--fin", required=True)
    s.add_argument("--salida", default="data/listado.csv")
    s.set_defaults(func=cmd_listar)

    s = sub.add_parser("historico", help="recupera horas de un CSV con columna 'href'")
    s.add_argument("--entrada", required=True)
    s.add_argument("--salida", default="data/historico.csv")
    s.add_argument("--workers", type=int, default=1)
    s.add_argument("--con-texto", action="store_true", help="también guarda el cuerpo de la nota")
    s.set_defaults(func=cmd_historico)

    s = sub.add_parser("articulos", help="texto completo para un CSV con columna 'url'")
    s.add_argument("--entrada", required=True)
    s.add_argument("--salida", default="data/articulos.csv")
    s.add_argument("--workers", type=int, default=1)
    s.set_defaults(func=cmd_articulos)

    s = sub.add_parser("alinear", help="asigna notas al día cambiario (cierre 13:30)")
    s.add_argument("--entrada", required=True, action="append", help="puede repetirse")
    s.add_argument("--salida", default="data/alineado.csv")
    s.add_argument("--cierre", default="13:30", help="hora de cierre del interbancario (Lima)")
    s.add_argument("--apertura", default="09:00", help="hora de apertura del interbancario (Lima)")
    s.set_defaults(func=cmd_alinear)

    a = p.parse_args()
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    if getattr(a, "workers", 1) > 4:
        log.warning("Más de 4 workers puede sobrecargar el sitio; usando 4.")
        a.workers = 4
    a.func(a)


if __name__ == "__main__":
    main()

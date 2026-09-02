# -*- coding: utf-8 -*-
"""Genera un PDF de ejemplo ATD (zoom + poligono) sin abrir ArcGIS Pro."""
from __future__ import annotations

import glob
import json
import os
import sys

import geopandas as gpd
import pandas as pd
from PIL import Image
from shapely.geometry import mapping

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ATD_LORETO = os.path.normpath(os.path.join(ROOT, "..", "ATD_Loreto"))
TOOLBOX = os.path.join(ROOT, "toolbox")
if TOOLBOX not in sys.path:
    sys.path.insert(0, TOOLBOX)

from atd_imagenes_h3 import aplicar_vector_y_zoom, bounds_imagen_desde_meta
from atd_pdf_build import generar_pdf_atd
from atd_region_config import (
    ACR_GEO,
    ACR_NOMBRES,
    ACR_SIGLAS,
    DEPARTAMENTO_REPORTE,
    GERENCIA_REGIONAL,
    GOBIERNO_REGIONAL,
    SUBGERENCIA_REGIONAL,
    configurar_region,
)


def _gdb_loreto(base):
    pats = glob.glob(os.path.join(base, "GDB", "Linea_base_deforest*Loreto.gdb"))
    pats = [
        p for p in pats
        if "backup" not in p.lower() and "corregido" not in p.lower()
    ]
    return pats[0] if pats else None


def _png(dir_img, oid, suf):
    p = os.path.join(dir_img, f"ATD_OID{int(oid)}_{suf}.png")
    return p if os.path.isfile(p) and os.path.getsize(p) > 8000 else None


def _meta(dir_img, oid, suf):
    jp = os.path.join(dir_img, f"ATD_OID{int(oid)}_{suf}.json")
    if not os.path.isfile(jp):
        return {}
    with open(jp, encoding="utf-8") as f:
        return json.load(f)


def _marcar(ruta, geom_wgs, meta, dest):
    import numpy as np

    bounds, epsg_b = bounds_imagen_desde_meta(meta, geom_wgs, 32718)
    arr = np.array(Image.open(ruta).convert("RGB"))
    arr_m = aplicar_vector_y_zoom(
        arr, bounds, geom_wgs,
        epsg_bounds=epsg_b, epsg_geom=4326,
        estilo="poligono", zoom=True,
    )
    Image.fromarray(arr_m).save(dest, format="PNG", optimize=True)
    return dest


def _mapa(gdf_alerta, gdf_acr, dest, epsg=32718):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    a = gdf_alerta.to_crs(epsg=epsg)
    acr = gdf_acr.to_crs(epsg=epsg)
    xmin, ymin, xmax, ymax = a.total_bounds
    pad = max(xmax - xmin, ymax - ymin, 400) * 8
    fig, ax = plt.subplots(figsize=(6.2, 5.4), dpi=140)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#f4f7f2")
    acr.plot(ax=ax, facecolor="#c5e1a8", edgecolor="#33691e", linewidth=1.2, alpha=0.55)
    a.plot(ax=ax, facecolor="#c41e3a", edgecolor="#8b1528", linewidth=1.6, alpha=0.95)
    cx, cy = a.geometry.iloc[0].centroid.x, a.geometry.iloc[0].centroid.y
    ax.set_xlim(cx - pad, cx + pad)
    ax.set_ylim(cy - pad, cy + pad)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title("Ubicacion de la alerta en el ACR", fontsize=9, pad=6)
    fig.tight_layout()
    fig.savefig(dest, dpi=140, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return dest


def main():
    gdb = _gdb_loreto(ROOT) or _gdb_loreto(ATD_LORETO)
    if not gdb:
        raise SystemExit("No se encontro la GDB de Loreto")
    configurar_region(gdb, force=True)

    dir_img = os.path.join(ATD_LORETO, "imagenes_sentinel")
    if not os.path.isdir(dir_img):
        dir_img = os.path.join(ROOT, "imagenes_sentinel")

    df = gpd.read_file(gdb, layer="MonitoreoDeforestacion", fid_as_index=True)
    df = df.reset_index()
    oid_col = "fid" if "fid" in df.columns else None
    if oid_col is None:
        df["fid"] = range(1, len(df) + 1)
        oid_col = "fid"
    df["md_causa"] = pd.to_numeric(df.get("md_causa"), errors="coerce")
    antrop = df[df["md_causa"].isin([1, 2, 3, 6, 11, 15])].copy()
    if antrop.empty:
        antrop = df.copy()

    png_oids = set()
    for p in glob.glob(os.path.join(dir_img, "ATD_OID*_A.png")):
        base = os.path.basename(p)
        try:
            png_oids.add(int(base.split("OID")[1].split("_")[0]))
        except Exception:
            pass
    print("png A", len(png_oids), "alertas", len(antrop))

    elegido = None
    elegido_ix = None
    for ix, row in antrop.iterrows():
        try:
            oid = int(row[oid_col])
        except Exception:
            continue
        if oid in png_oids and _png(dir_img, oid, "D"):
            elegido = row
            elegido_ix = ix
            break
    if elegido is None:
        raise SystemExit("No hay alerta 2026 con par ANTES/DESPUES en imagenes_sentinel")

    oid = int(elegido[oid_col])
    gdf_one = antrop.loc[[elegido_ix]].copy()
    geom_wgs = gdf_one.to_crs(epsg=4326).geometry.iloc[0]

    tmp = os.path.join(ROOT, "pdfs", "_ejemplo_tmp")
    os.makedirs(tmp, exist_ok=True)
    meta_a = _meta(dir_img, oid, "A")
    meta_d = _meta(dir_img, oid, "D")
    ruta_a = _marcar(_png(dir_img, oid, "A"), geom_wgs, meta_a, os.path.join(tmp, "A_vec.png"))
    ruta_d = _marcar(_png(dir_img, oid, "D"), geom_wgs, meta_d, os.path.join(tmp, "D_vec.png"))

    try:
        acr = gpd.read_file(gdb, layer="gpo_anp_monit")
        cod = str(elegido.get("anp_codi") or "")
        acr["_c"] = acr.get("acr_codi", acr.get("anp_codi", "")).astype(str)
        acr_sub = acr[acr["_c"].str.upper().str.contains(cod.upper(), na=False)]
        if acr_sub.empty:
            acr_sub = acr
        mapa_path = _mapa(gdf_one, acr_sub, os.path.join(tmp, "mapa.png"))
    except Exception:
        mapa_path = None

    cod = str(elegido.get("anp_codi") or "ACR10").strip()
    causa_map = {
        1: "Agricultura", 2: "Ganaderia", 3: "Extraccion Forestal",
        6: "Mineria", 11: "Ocupacion Humana", 14: "Natural",
        15: "Incendio Antropico",
    }
    causa_n = int(elegido.get("md_causa") or 0)
    fec = elegido.get("md_fecimg")
    try:
        fecha_str = pd.to_datetime(fec).strftime("%d/%m/%Y")
    except Exception:
        fecha_str = str(fec or "-")

    geo = ACR_GEO.get(cod, {})
    logos = os.path.join(ATD_LORETO, "logos")
    if not os.path.isdir(logos):
        logos = os.path.join(ROOT, "logos")

    out_informe = os.path.join(ROOT, "pdfs", "EJEMPLO_reporte_ATD_Loreto_2026.pdf")
    out_docs = os.path.join(ATD_LORETO, "docs", "EJEMPLO_reporte_ATD_Loreto.pdf")
    os.makedirs(os.path.dirname(out_informe), exist_ok=True)
    os.makedirs(os.path.dirname(out_docs), exist_ok=True)

    job = {
        "pdf_path": out_informe,
        "mapa_path": mapa_path,
        "ruta_a": ruta_a,
        "ruta_d": ruta_d,
        "idx": 0,
        "cfg": {
            "anno_reporte": 2026,
            "fecha_ini": "01/01/2026",
            "fecha_fin": "23/06/2026",
            "dir_logos": logos,
            "region_key": "loreto",
            "departamento": DEPARTAMENTO_REPORTE or "Loreto",
            "gobierno_regional": GOBIERNO_REGIONAL,
            "gerencia_regional": GERENCIA_REGIONAL,
            "subgerencia_regional": SUBGERENCIA_REGIONAL,
            "responsable": "Equipo ATD GFP Subnacional",
            "cargo": "Monitoreo de deforestacion en ACR",
        },
        "alerta": {
            "objectid": oid,
            "anp_codi": cod,
            "acr_sigla": ACR_SIGLAS.get(cod, cod),
            "acr_nombre": ACR_NOMBRES.get(cod, str(elegido.get("ac_nomb") or cod)),
            "causa_texto": causa_map.get(causa_n, "Otros"),
            "bosque_texto": "Primario",
            "conf_texto": "Alta (prioritaria para revisión)",
            "md_zonif": elegido.get("md_zonif") or "-",
            "md_sup": float(elegido.get("md_sup") or 0),
            "md_este": elegido.get("md_este"),
            "md_norte": elegido.get("md_norte"),
            "md_exa": elegido.get("md_exa") or "-",
            "md_sector": elegido.get("md_sector") or "-",
            "lugar_poblado": "-",
            "sector_reporte": elegido.get("md_sector") or "-",
            "olv_cercano": "-",
            "provincia": geo.get("provincia", "-"),
            "distrito": geo.get("distrito", "-"),
            "fecha_str": fecha_str,
            "md_codigo": elegido.get("md_codigo"),
        },
        "links": {
            "fecha_a": str(meta_a.get("fecha") or "-"),
            "fecha_d": str(meta_d.get("fecha") or fecha_str),
            "sat_a": str(meta_a.get("sat") or "Sentinel-2"),
            "sat_d": str(meta_d.get("sat") or "Sentinel-2"),
            "url_eo": "https://apps.sentinel-hub.com/eo-browser/",
            "url_gee": "https://earth.google.com/web/",
            "link_metodologia": "",
            "link_procedimiento": "",
        },
    }
    generar_pdf_atd(job)
    import shutil
    shutil.copy2(out_informe, out_docs)
    print("OID", oid, "ACR", cod, "causa", causa_n)
    print("PDF", out_informe)
    print("DOCS", out_docs)


if __name__ == "__main__":
    main()

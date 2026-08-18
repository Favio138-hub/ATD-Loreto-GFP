# -*- coding: utf-8 -*-
"""
Quita duplicados superpuestos:

1) MonitoreoDeforestacion (GitHub): borra Geobosques crudos 2026
   (sin clasificar) que quedan debajo de los fotointerpretados.
2) Acumulado GitHub: borra ACR18 residual (MPA ya esta como ACR34).
3) Acumulado (ambas GDB): si un poligono viejo cubre >=60% de uno mas
   reciente del mismo ACR, se elimina el viejo. Se conservan alertas
   nuevas en el mismo lugar (el mas reciente gana).
"""
from __future__ import annotations

import os

import arcpy

GDBS = [
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "GDB", "Linea_base_deforestación_Loreto.gdb",
    ),
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "..", "ATD_Loreto", "GDB", "Linea_base_deforestación_Loreto.gdb",
    ),
]
OVERLAP_PCT = 60.0  # % del area del poligono MAS NUEVO cubierto por el viejo


def _log(msg):
    print(msg, flush=True)


def _norm(p):
    return os.path.normpath(p)


def limpiar_vigente_crudos(gdb: str) -> int:
    fc = os.path.join(gdb, "MonitoreoDeforestacion")
    if not arcpy.Exists(fc):
        return 0
    campos = {f.name.lower(): f.name for f in arcpy.ListFields(fc)}
    f_conf = campos.get("md_conf")
    f_causa = campos.get("md_causa")
    if not f_conf:
        return 0
    oid = arcpy.Describe(fc).OIDFieldName
    borrar = []
    leer = [oid, f_conf] + ([f_causa] if f_causa else [])
    with arcpy.da.SearchCursor(fc, leer) as cur:
        for row in cur:
            conf = row[1]
            causa = row[2] if f_causa else None
            vacio_conf = conf in (None, "", 0)
            vacio_causa = causa in (None, "")
            if vacio_conf and vacio_causa:
                borrar.append(int(row[0]))
    if not borrar:
        n = int(arcpy.management.GetCount(fc)[0])
        _log(f"  vigente: sin crudos. quedan {n}")
        return 0
    lyr = "lyr_vig_crudos"
    if arcpy.Exists(lyr):
        arcpy.management.Delete(lyr)
    ids = ",".join(str(i) for i in borrar)
    arcpy.management.MakeFeatureLayer(fc, lyr, f"{oid} IN ({ids})")
    n_del = int(arcpy.management.GetCount(lyr)[0])
    arcpy.management.DeleteRows(lyr)
    n = int(arcpy.management.GetCount(fc)[0])
    _log(f"  vigente: borrados crudos {n_del} | quedan {n}")
    return n_del


def limpiar_acr18(gdb: str) -> int:
    total = 0
    for name in ("MonitoreoDeforestacion", "MonitoreoDeforestacionAcumulado"):
        fc = os.path.join(gdb, name)
        if not arcpy.Exists(fc):
            continue
        campos = {f.name.lower(): f.name for f in arcpy.ListFields(fc)}
        fcod = campos.get("anp_codi") or campos.get("acr_codi")
        if not fcod:
            continue
        lyr = f"lyr_acr18_{name}"
        if arcpy.Exists(lyr):
            arcpy.management.Delete(lyr)
        arcpy.management.MakeFeatureLayer(
            fc, lyr, f"{fcod} IN ('ACR18','MPA')"
        )
        n = int(arcpy.management.GetCount(lyr)[0])
        if n:
            arcpy.management.DeleteRows(lyr)
            _log(f"  {name}: borrados ACR18/MPA viejos {n}")
            total += n
    return total


def _oid_field(fc):
    return arcpy.Describe(fc).OIDFieldName


def limpiar_viejos_superpuestos(gdb: str, fc_name: str) -> int:
    """Elimina poligonos mas viejos que cubren un mas reciente (>= OVERLAP_PCT)."""
    import numpy as np
    import pandas as pd
    import pyogrio

    fc = os.path.join(gdb, fc_name)
    if not arcpy.Exists(fc):
        return 0
    n_in = int(arcpy.management.GetCount(fc)[0])
    _log(f"  {fc_name}: buscando superpuestos viejos en {n_in}...")
    gdf = pyogrio.read_dataframe(gdb, layer=fc_name)
    if gdf.empty or "md_anno" not in gdf.columns:
        return 0
    oid_col = gdf.columns[0]
    # pyogrio usa el FID como index a veces; asegurar columna OBJECTID
    fid = None
    for c in gdf.columns:
        if str(c).lower() in ("objectid", "objectid_1", "fid"):
            fid = c
            break
    if fid is None:
        gdf = gdf.reset_index(drop=False)
        fid = "index" if "index" in gdf.columns else gdf.columns[0]

    gdf["_anno"] = np.floor(pd.to_numeric(gdf["md_anno"], errors="coerce").fillna(0)).astype(int)
    acr_col = "anp_codi" if "anp_codi" in gdf.columns else "acr_codi"
    gdf["_acr"] = gdf[acr_col].astype(str).str.upper()
    gdf["_fid"] = gdf[fid].astype(int)
    # proyectar a UTM para areas
    try:
        gdf = gdf.to_crs(32718)
    except Exception:
        pass
    gdf["_area"] = gdf.geometry.area

    borrar = set()
    for acr, sub in gdf.groupby("_acr"):
        if not str(acr).startswith("ACR"):
            continue
        if len(sub) < 2:
            continue
        sindex = sub.sindex
        fids = sub["_fid"].to_numpy()
        annos = sub["_anno"].to_numpy()
        geoms = sub.geometry.to_numpy()
        areas = sub["_area"].to_numpy()
        for i, (fid_i, year_i, geom_i, area_i) in enumerate(zip(fids, annos, geoms, areas)):
            if fid_i in borrar or geom_i is None or area_i <= 0:
                continue
            try:
                idxs = list(sindex.query(geom_i, predicate="intersects"))
            except Exception:
                continue
            for j in idxs:
                fid_j = int(fids[j])
                if fid_j == fid_i or fid_j in borrar:
                    continue
                year_j = int(annos[j])
                if year_j >= year_i:
                    continue
                geom_j = geoms[j]
                try:
                    inter = geom_i.intersection(geom_j)
                    if inter.is_empty:
                        continue
                    pct = 100.0 * (inter.area / area_i)
                except Exception:
                    continue
                if pct >= OVERLAP_PCT:
                    borrar.add(fid_j)

    if not borrar:
        _log(f"  {fc_name}: 0 viejos superpuestos")
        return 0

    oid = arcpy.Describe(fc).OIDFieldName
    deleted = 0
    ids_list = sorted(borrar)
    lyr = "lyr_old_ov"
    for i in range(0, len(ids_list), 900):
        part = ",".join(str(x) for x in ids_list[i:i + 900])
        if arcpy.Exists(lyr):
            arcpy.management.Delete(lyr)
        arcpy.management.MakeFeatureLayer(fc, lyr, f"{oid} IN ({part})")
        n = int(arcpy.management.GetCount(lyr)[0])
        if n:
            arcpy.management.DeleteRows(lyr)
            deleted += n
    n_out = int(arcpy.management.GetCount(fc)[0])
    _log(f"  {fc_name}: borrados viejos superpuestos {deleted} | quedan {n_out}")
    return deleted


def main():
    arcpy.env.overwriteOutput = True
    for gdb in GDBS:
        gdb = _norm(gdb)
        if not arcpy.Exists(gdb):
            _log("SKIP " + gdb)
            continue
        _log("=== " + gdb)
        limpiar_vigente_crudos(gdb)
        limpiar_acr18(gdb)
        # vigente: tambien viejos-sobre-nuevos si quedara algo
        try:
            limpiar_viejos_superpuestos(gdb, "MonitoreoDeforestacion")
        except Exception as ex:
            _log("  AVISO vigente overlap: " + str(ex))
        try:
            limpiar_viejos_superpuestos(gdb, "MonitoreoDeforestacionAcumulado")
        except Exception as ex:
            _log("  AVISO acumulado overlap: " + str(ex))
    _log("OK")


if __name__ == "__main__":
    main()

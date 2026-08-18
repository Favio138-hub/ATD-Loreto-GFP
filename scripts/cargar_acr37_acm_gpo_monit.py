# -*- coding: utf-8 -*-
"""Carga ACR37 Aguas Calientes Maquía en gpo_anp_monit y dominio ANP_2_1."""
from __future__ import annotations

import os
import shutil

import arcpy

ACR_CODI = "ACR37"
ACR_NOMB = "Aguas Calientes Maquía"
ACR_NOMB_FULL = "ACR Aguas Calientes Maquía"
SHP = os.path.join(
    r"C:\Users\Favio Campos Rivera\Desktop\GFP-Subnacional\2026",
    "Limite ACR ACM",
    "Limite_Propuesta_ACR_ACM_Noviembre.shp",
)
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GDBS = [
    os.path.join(BASE, "GDB", "Linea_base_deforestación_Loreto.gdb"),
    os.path.join(
        os.path.dirname(BASE), "ATD_Loreto", "GDB",
        "Linea_base_deforestación_Loreto.gdb",
    ),
]


def _log(msg):
    print(msg, flush=True)


def _asegurar_dominio(gdb: str) -> None:
    for d in arcpy.da.ListDomains(gdb) or []:
        if d.name != "ANP_2_1":
            continue
        codes = {str(k) for k in (d.codedValues or {})}
        if ACR_CODI in codes:
            _log(f"  Dominio ANP_2_1 ya tiene {ACR_CODI}")
            return
        arcpy.management.AddCodedValueToDomain(
            gdb, "ANP_2_1", ACR_CODI, ACR_NOMB_FULL,
        )
        _log(f"  + {ACR_CODI} en dominio ANP_2_1")
        return
    _log("  AVISO: no se encontro dominio ANP_2_1")


def _geom_acm_wgs84():
    sr_wgs = arcpy.SpatialReference(4326)
    tmp = os.path.join("in_memory", "acm_src")
    if arcpy.Exists(tmp):
        arcpy.management.Delete(tmp)
    arcpy.conversion.FeatureClassToFeatureClass(
        SHP, "in_memory", "acm_src"
    )
    tmp_proj = os.path.join("in_memory", "acm_wgs")
    if arcpy.Exists(tmp_proj):
        arcpy.management.Delete(tmp_proj)
    arcpy.management.Project(tmp, tmp_proj, sr_wgs)
    diss = os.path.join("in_memory", "acm_diss")
    if arcpy.Exists(diss):
        arcpy.management.Delete(diss)
    arcpy.management.Dissolve(tmp_proj, diss, multi_part="MULTI_PART")
    n = int(arcpy.management.GetCount(diss)[0])
    if n != 1:
        raise SystemExit(f"Dissolve ACM inesperado: {n} features")
    with arcpy.da.SearchCursor(diss, ["SHAPE@", "SHAPE@AREA"]) as cur:
        geom, area = next(cur)
    ha = round(geom.getArea("GEODESIC", "HECTARES"), 2)
    _log(f"  Geometria ACM: {ha:,.2f} ha  parts={geom.partCount}")
    return geom, ha


def _borrar_acr37(fc: str) -> None:
    lyr = "lyr_acr37_old"
    if arcpy.Exists(lyr):
        arcpy.management.Delete(lyr)
    arcpy.management.MakeFeatureLayer(fc, lyr, f"acr_codi = '{ACR_CODI}'")
    n = int(arcpy.management.GetCount(lyr)[0])
    if n:
        arcpy.management.DeleteRows(lyr)
        _log(f"  Eliminados previos {ACR_CODI}: {n}")


def _insertar(fc: str, geom, ha: float) -> None:
    campos = {f.name.lower(): f.name for f in arcpy.ListFields(fc)}
    fila_map = {
        "acr_codi": ACR_CODI,
        "acr_nomb": ACR_NOMB,
        "acr_sect": "Zona Norte / Zona Sur",
        "acr_ubpo": "Loreto",
        "ha": ha,
        "nomobj": ACR_NOMB_FULL,
        "codacr": ACR_CODI,
        "codobj": ACR_CODI,
        "fuente": "ARA - GORELORETO",
        "acr_obs": "Propuesta ACR Aguas Calientes Maquía (límite noviembre; Norte+Sur)",
        "infobj": "Limite_Propuesta_ACR_ACM_Noviembre",
        "promet": "Propuesta",
    }
    insert_names = ["SHAPE@"]
    values = [geom]
    for key, val in fila_map.items():
        if key in campos:
            insert_names.append(campos[key])
            values.append(val)
    with arcpy.da.InsertCursor(fc, insert_names) as ic:
        ic.insertRow(values)
    arcpy.management.RecalculateFeatureClassExtent(fc)
    lyr = "lyr_chk37"
    if arcpy.Exists(lyr):
        arcpy.management.Delete(lyr)
    arcpy.management.MakeFeatureLayer(fc, lyr, f"acr_codi = '{ACR_CODI}'")
    n = int(arcpy.management.GetCount(lyr)[0])
    _log(f"  Insertado {ACR_CODI}: {n} feature(s)")
    if n != 1:
        raise SystemExit("No quedo 1 poligono ACR37 en gpo_anp_monit")


def _ampliar_dominio_monitoreo(gdb: str) -> None:
    """Si el dominio XY del FC de alertas no cubre ACM (~-7.3), lo recrea."""
    sr_wide = arcpy.SpatialReference(4326)
    for name in ("MonitoreoDeforestacion", "MonitoreoDeforestacionAcumulado"):
        fc = os.path.join(gdb, name)
        if not arcpy.Exists(fc):
            continue
        ymin = float(arcpy.Describe(fc).spatialReference.domain.split()[1])
        if ymin <= -8.5:
            _log(f"  {name}: dominio YMin={ymin:.2f} OK para ACM")
            continue
        _log(f"  {name}: dominio estrecho YMin={ymin:.2f} -> ampliando")
        tmp_name = name + "_xywide"
        tmp = os.path.join(gdb, tmp_name)
        if arcpy.Exists(tmp):
            arcpy.management.Delete(tmp)
        arcpy.management.CreateFeatureclass(
            gdb, tmp_name, "POLYGON", template=fc,
            spatial_reference=sr_wide,
        )
        arcpy.management.Append(fc, tmp, "NO_TEST")
        n_src = int(arcpy.management.GetCount(fc)[0])
        n_tmp = int(arcpy.management.GetCount(tmp)[0])
        if n_src != n_tmp:
            _log(f"  AVISO conteos {name}: {n_src} vs {n_tmp}")
        arcpy.management.Delete(fc)
        arcpy.management.Rename(tmp, name)
        _log(f"  {name}: recreado con WGS84 amplio ({n_tmp} filas)")


def main():
    arcpy.env.overwriteOutput = True
    if not arcpy.Exists(SHP):
        raise SystemExit("No existe shapefile ACM: " + SHP)
    geom, ha = _geom_acm_wgs84()
    for gdb in GDBS:
        if not arcpy.Exists(gdb):
            _log("SKIP GDB ausente: " + gdb)
            continue
        _log("=== " + gdb)
        _asegurar_dominio(gdb)
        fc = os.path.join(gdb, "gpo_anp_monit")
        if not arcpy.Exists(fc):
            _log("  SKIP sin gpo_anp_monit")
            continue
        _borrar_acr37(fc)
        _insertar(fc, geom, ha)
        try:
            _ampliar_dominio_monitoreo(gdb)
        except Exception as ex:
            _log("  AVISO dominio monitoreo: " + str(ex))
    _log("OK")


if __name__ == "__main__":
    main()

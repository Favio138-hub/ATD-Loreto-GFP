# -*- coding: utf-8 -*-
"""Copia registros ACR34 (MPA) del acumulado oficial al paquete ATD_Loreto."""
from __future__ import annotations

import os
import sys

import arcpy

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_GDB = os.path.join(BASE, "GDB")
PKG_ROOT = os.path.join(os.path.dirname(BASE), "ATD_Loreto")
DST_GDB = os.path.join(PKG_ROOT, "GDB", "Linea_base_deforestación_Loreto.gdb")
FC = "MonitoreoDeforestacionAcumulado"
WHERE = "anp_codi = 'ACR34'"


def _pick_gdb(folder):
    return next(
        os.path.join(folder, d)
        for d in os.listdir(folder)
        if d.endswith(".gdb")
        and "Loreto" in d
        and "backup" not in d.lower()
        and "BACKUP" not in d
        and "CORREGIDO" not in d
    )


def main():
    arcpy.env.overwriteOutput = True
    src = os.path.join(_pick_gdb(SRC_GDB), FC)
    dst = os.path.join(DST_GDB, FC)
    if not arcpy.Exists(dst):
        raise SystemExit(f"No existe destino: {dst}")

    lyr_old = "lyr_mpa_old"
    if arcpy.Exists(lyr_old):
        arcpy.management.Delete(lyr_old)
    arcpy.management.MakeFeatureLayer(dst, lyr_old, WHERE)
    n_old = int(arcpy.management.GetCount(lyr_old)[0])
    if n_old:
        arcpy.management.DeleteRows(lyr_old)
        print(f"Eliminados previos ACR34 en destino: {n_old}")

    tmp = os.path.join("in_memory", "mpa_src")
    if arcpy.Exists(tmp):
        arcpy.management.Delete(tmp)
    arcpy.conversion.FeatureClassToFeatureClass(src, "in_memory", "mpa_src", WHERE)
    n_src = int(arcpy.management.GetCount(tmp)[0])
    print(f"Origen ACR34: {n_src}")

    arcpy.management.Append(tmp, dst, "NO_TEST")
    arcpy.management.MakeFeatureLayer(dst, "lyr_chk", WHERE)
    n_dst = int(arcpy.management.GetCount("lyr_chk")[0])
    print(f"Destino ACR34: {n_dst}")
    print("OK" if n_dst == n_src else "AVISO: conteos distintos")


if __name__ == "__main__":
    main()

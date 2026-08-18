# -*- coding: utf-8 -*-
"""
Normaliza registros MPA (ACR34) en MonitoreoDeforestacionAcumulado:
- 2025 Geobosques: md_conf, md_bosque y ac_nomb como patron 2024
- 2001-2024: rellena huecos en campos core (md_conf, md_bosque, md_causa, ac_nomb)
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import sys

import arcpy

ACR_CODI = "ACR34"
ACR_NOMB = "ACR Medio Putumayo Algodón"
DEFAULT_CONF = 1
DEFAULT_BOSQUE = 1
DEFAULT_FUENTE = 3


def _gdb_loreto():
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "GDB")
    return next(
        os.path.join(base, d)
        for d in os.listdir(base)
        if d.endswith(".gdb")
        and "Loreto" in d
        and "backup" not in d.lower()
        and "BACKUP" not in d
        and "CORREGIDO" not in d
    )


def _load_h1():
    h1_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "toolbox",
        "ATD_H1_Descargas_Geo_Bosques.pyt",
    )
    loader = importlib.machinery.SourceFileLoader("atd_h1_norm_mpa", h1_path)
    spec = importlib.util.spec_from_loader("atd_h1_norm_mpa", loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["atd_h1_norm_mpa"] = mod
    loader.exec_module(mod)
    return mod


def _vacio(val) -> bool:
    if val is None:
        return True
    s = str(val).strip()
    return s in ("", "None", "nan", "NaN", "<Null>")


def _audit(fc, where, label):
    campos = {f.name.lower(): f.name for f in arcpy.ListFields(fc)}
    cols = [
        "md_causa", "md_conf", "md_bosque", "md_fuente", "ac_nomb",
        "md_exa", "md_zonif", "md_sector", "md_codigo",
    ]
    print(f"\n--- {label} ---")
    n = int(arcpy.management.GetCount(fc)[0])
    print(f"Registros: {n}")
    for col in cols:
        if col not in campos:
            continue
        f = campos[col]
        empty = 0
        with arcpy.da.SearchCursor(fc, [f], where) as cur:
            for (val,) in cur:
                if _vacio(val):
                    empty += 1
        print(f"  {col}: vacios {empty}/{n}")


def main():
    arcpy.env.overwriteOutput = True
    gdb = _gdb_loreto()
    dst = os.path.join(gdb, "MonitoreoDeforestacionAcumulado")
    campos = {f.name.lower(): f.name for f in arcpy.ListFields(dst)}
    oid = arcpy.Describe(dst).OIDFieldName
    where_mpa = f"anp_codi = '{ACR_CODI}'"

    print("GDB:", gdb)
    _audit(dst, where_mpa, "MPA antes")

    upd_fields = [oid]
    idx = {}
    for col in ("ac_nomb", "md_conf", "md_bosque", "md_fuente", "md_causa"):
        if col in campos:
            idx[col] = len(upd_fields)
            upd_fields.append(campos[col])

    n_ac_nomb = n_conf = n_bosque = n_fuente = 0
    with arcpy.da.UpdateCursor(dst, upd_fields, where_mpa) as cur:
        for row in cur:
            changed = False
            if "ac_nomb" in idx:
                actual = row[idx["ac_nomb"]]
                if _vacio(actual) or not str(actual).strip().startswith("ACR "):
                    row[idx["ac_nomb"]] = ACR_NOMB
                    n_ac_nomb += 1
                    changed = True
            if "md_conf" in idx and _vacio(row[idx["md_conf"]]):
                row[idx["md_conf"]] = DEFAULT_CONF
                n_conf += 1
                changed = True
            if "md_bosque" in idx and _vacio(row[idx["md_bosque"]]):
                row[idx["md_bosque"]] = DEFAULT_BOSQUE
                n_bosque += 1
                changed = True
            if "md_fuente" in idx and _vacio(row[idx["md_fuente"]]):
                row[idx["md_fuente"]] = DEFAULT_FUENTE
                n_fuente += 1
                changed = True
            if changed:
                cur.updateRow(row)

    print("\nActualizados:")
    print(f"  ac_nomb: {n_ac_nomb}")
    print(f"  md_conf: {n_conf}")
    print(f"  md_bosque: {n_bosque}")
    print(f"  md_fuente: {n_fuente}")

    # Enriquecimiento espacial sector/zonif/exa (opcional, no estaba en 2024 historico)
    h1 = _load_h1()
    fc_zon = os.path.join(gdb, "gpo_zonif_anp")
    fc_exa = os.path.join(gdb, "gpo_exa")
    fc_sectores = os.path.join(gdb, "gpo_sectores")
    if not arcpy.Exists(fc_sectores):
        fc_sectores = None
    h1_cfg = h1.h1_config_activa()
    col_fi = (
        h1.resolver_campo_h1(
            fc_exa,
            h1_cfg.get("exa_campos", []),
            campos_list=[f.name for f in arcpy.ListFields(fc_exa)],
        )
        if arcpy.Exists(fc_exa)
        else None
    )
    campo_tz = (
        h1.resolver_campo_h1(
            fc_zon,
            h1_cfg.get("zonif_campos", []),
            campos_list=[f.name for f in arcpy.ListFields(fc_zon)],
        )
        if arcpy.Exists(fc_zon)
        else None
    )

    for anno in (2025,):
        lyr = f"lyr_mpa_{anno}"
        if arcpy.Exists(lyr):
            arcpy.management.Delete(lyr)
        arcpy.management.MakeFeatureLayer(
            dst, lyr, f"{where_mpa} AND md_anno = {anno}"
        )
        if int(arcpy.management.GetCount(lyr)[0]) == 0:
            continue
        print(f"\nEnriqueciendo ACR34-{anno} (sector/zonif/exa)...")
        try:
            n_sec, n_zon, n_exa = h1._enriquecer_alertas_batch(
                lyr, gdb, anno, fc_zon, campo_tz, fc_sectores, fc_exa, col_fi, print
            )
            print(f"  sector={n_sec} zonif={n_zon} exa={n_exa}")
        except Exception as ex:
            print("  AVISO enrich:", ex)

    _audit(dst, where_mpa, "MPA despues")
    print("\nOK")


if __name__ == "__main__":
    main()

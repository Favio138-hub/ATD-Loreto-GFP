# -*- coding: utf-8 -*-
"""Descarga alertas Geobosques 2025 de MPA (ACR34) y las inserta en el acumulado."""
from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import sys
import tempfile

import arcpy

ANNO = 2025
FECHA_INI = "01/01/2025"
FECHA_FIN = "31/12/2025"


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
    loader = importlib.machinery.SourceFileLoader("atd_h1_mpa", h1_path)
    spec = importlib.util.spec_from_loader("atd_h1_mpa", loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["atd_h1_mpa"] = mod
    loader.exec_module(mod)
    return mod


def _log(msg):
    print(msg, flush=True)
    try:
        arcpy.AddMessage(msg)
    except Exception:
        pass


def main():
    arcpy.env.overwriteOutput = True
    arcpy.AddMessage = _log
    arcpy.AddWarning = lambda m: _log("AVISO: " + str(m))
    arcpy.AddError = lambda m: _log("ERROR: " + str(m))

    h1 = _load_h1()
    gdb = _gdb_loreto()
    dst = os.path.join(gdb, "MonitoreoDeforestacionAcumulado")
    fc_acr = os.path.join(gdb, "gpo_anp_monit")
    print("GDB", gdb)
    print("DST", dst)

    h1.configurar_region(gdb, force=True)
    fecha_ini = h1._parse_fecha(FECHA_INI)
    fecha_fin = h1._parse_fecha(FECHA_FIN)

    # Poligono MPA
    mpa_tmp = os.path.join("in_memory", "mpa_acr34")
    h1._borrar_fc(mpa_tmp)
    where_mpa = (
        "UPPER(acr_codi) IN ('ACR34','ACR18') OR "
        "UPPER(NOMOBJ) LIKE '%PUTUMAYO%' OR "
        "UPPER(acr_nomb) LIKE '%PUTUMAYO%'"
    )
    arcpy.conversion.FeatureClassToFeatureClass(
        fc_acr, "in_memory", "mpa_acr34", where_clause=where_mpa
    )
    n_mpa = int(arcpy.management.GetCount(mpa_tmp)[0])
    if n_mpa == 0:
        raise SystemExit("No se encontro el poligono MPA (ACR34) en gpo_anp_monit")
    print(f"MPA poligonos: {n_mpa}")
    with arcpy.da.SearchCursor(mpa_tmp, ["SHAPE@", "acr_codi", "acr_nomb"]) as cur:
        geom_mpa, acr_codi, acr_nomb = next(cur)
    acr_codi = "ACR34"
    acr_nomb = "ACR Medio Putumayo Algodón"
    print("ACR", acr_codi, acr_nomb)

    url = h1._URL_BASE.format(anno=ANNO)
    tmp = tempfile.mkdtemp(prefix=f"ATD_MPA_{ANNO}_")
    print("[1] Descargando", url)
    # timeout mas holgado que H1
    h1._URL_BASE  # keep
    zip_path = os.path.join(tmp, "alertas.zip")
    req = __import__("urllib.request").request.Request(
        url, headers={"User-Agent": "ATD-Toolbox/MPA-2025"}
    )
    with __import__("urllib.request").request.urlopen(req, timeout=600) as r:
        with open(zip_path, "wb") as f:
            while True:
                chunk = r.read(1024 * 256)
                if not chunk:
                    break
                f.write(chunk)
    import zipfile
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(tmp)
    raster_alertas = None
    for root, _dirs, files in os.walk(tmp):
        for fn in files:
            if fn.lower().endswith((".tif", ".tiff", ".img")):
                raster_alertas = os.path.join(root, fn)
                break
    if not raster_alertas:
        raise SystemExit("No hay raster en el ZIP Geobosques 2025")
    print("Raster", raster_alertas)

    print("[2] Recortando raster a MPA...")
    sr_ras = arcpy.Describe(raster_alertas).spatialReference
    mpa_proj = os.path.join("in_memory", "mpa_proj")
    h1._borrar_fc(mpa_proj)
    arcpy.management.Project(mpa_tmp, mpa_proj, sr_ras)
    ras_clip = os.path.join(tmp, "alertas_mpa_2025.tif")
    if os.path.isfile(ras_clip):
        os.remove(ras_clip)
    try:
        arcpy.management.Clip(
            raster_alertas,
            "#",
            ras_clip,
            mpa_proj,
            "0",
            "ClippingGeometry",
            "NO_MAINTAIN_EXTENT",
        )
    except Exception as ex:
        print("Clip raster fallo, ExtractByMask:", ex)
        sa = arcpy.sa
        arcpy.CheckOutExtension("Spatial")
        out = sa.ExtractByMask(raster_alertas, mpa_proj)
        out.save(ras_clip)

    print("[3] Raster a poligonos...")
    poly = os.path.join("in_memory", "poly_mpa_2025")
    h1._borrar_fc(poly)
    arcpy.conversion.RasterToPolygon(ras_clip, poly, "NO_SIMPLIFY")
    n_poly = int(arcpy.management.GetCount(poly)[0])
    print(f"   Poligonos recorte: {n_poly:,}")
    if n_poly == 0:
        raise SystemExit("0 alertas 2025 dentro de MPA")

    mapa_fechas = h1._mapa_fechas_geobosques(ras_clip, _log)
    if not mapa_fechas:
        mapa_fechas = h1._mapa_fechas_geobosques(raster_alertas, _log)
    campo_grid = h1._campo_gridcode(poly)
    h1._asignar_fecha_a_poligonos(poly, mapa_fechas, campo_grid, ANNO, _log)
    poly = h1._filtrar_poligonos_por_periodo(poly, fecha_ini, fecha_fin, _log)
    n_poly = int(arcpy.management.GetCount(poly)[0])
    print(f"   Poligonos en 2025: {n_poly:,}")

    print("[4] Borrar ACR34 2025 previo en acumulado...")
    lyr = "lyr_mpa25"
    if arcpy.Exists(lyr):
        arcpy.management.Delete(lyr)
    arcpy.management.MakeFeatureLayer(
        dst, lyr, "anp_codi = 'ACR34' AND md_anno = 2025"
    )
    n_old = int(arcpy.management.GetCount(lyr)[0])
    if n_old:
        arcpy.management.DeleteRows(lyr)
        print(f"   Eliminados previos: {n_old}")
    else:
        print("   Sin previos 2025 MPA")

    h1._asegurar_campos_h1(dst, gdb)
    h1._asegurar_campo_md_sector(dst)
    campos_map = h1._campos_map_fc(dst)
    campos_insert = ["SHAPE@"]
    for nombre in (
        "anp_codi", "ac_nomb", "md_fuente", "md_anno", "md_sup",
        "md_este", "md_norte", "md_mesrep", "md_fecini", "md_fecfin",
        "md_fecimg", "md_causa", "md_conf", "md_bosque",
    ):
        key = nombre.lower()
        if key in campos_map:
            campos_insert.append(h1._nombre_campo_fc(campos_map, nombre))

    def idx(c):
        nom = h1._nombre_campo_fc(campos_map, c)
        try:
            return campos_insert.index(nom)
        except ValueError:
            return -1

    i_acod = idx("anp_codi")
    i_nom = idx("ac_nomb")
    i_fue = idx("md_fuente")
    i_anno = idx("md_anno")
    i_sup = idx("md_sup")
    i_este = idx("md_este")
    i_nor = idx("md_norte")
    i_mes = idx("md_mesrep")
    i_fini = idx("md_fecini")
    i_ffin = idx("md_fecfin")
    i_fecimg = idx("md_fecimg")
    i_causa = idx("md_causa")
    i_conf = idx("md_conf")
    i_bosque = idx("md_bosque")
    cod_md_fuente = h1._resolver_md_fuente_landsat(gdb, dst, _log)

    arcpy.management.AddField(poly, "_area_ha_", "DOUBLE")
    arcpy.management.CalculateField(poly, "_area_ha_", "!SHAPE.AREA@hectares!", "PYTHON3")
    clip_fields = ["SHAPE@", "_area_ha_"]
    names = {f.name.lower(): f.name for f in arcpy.ListFields(poly)}
    idx_grid = idx_fec = None
    if campo_grid and campo_grid.lower() in names:
        clip_fields.append(names[campo_grid.lower()])
        idx_grid = len(clip_fields) - 1
    if getattr(h1, "_CAMPO_FEC_IMG_POLY", "fec_img_atd").lower() in names:
        clip_fields.append(names[h1._CAMPO_FEC_IMG_POLY.lower()])
        idx_fec = len(clip_fields) - 1

    print("[5] Insertando en acumulado...")
    ins = 0
    n_fecha = 0
    with arcpy.da.InsertCursor(dst, campos_insert) as ic:
        with arcpy.da.SearchCursor(poly, clip_fields) as sc:
            for row in sc:
                geom, area_ha = row[0], row[1]
                if geom is None:
                    continue
                grid_val = row[idx_grid] if idx_grid is not None else None
                fec_img = row[idx_fec] if idx_fec is not None else None
                fec_img = h1._parse_fecha(fec_img)
                if not fec_img:
                    fec_img = h1._fecha_desde_gridcode(mapa_fechas, grid_val, ANNO)
                en = h1._fecha_en_periodo(fec_img, fecha_ini, fecha_fin)
                if en is False or (en is None and fecha_ini and fecha_fin):
                    continue
                try:
                    cent = geom.centroid
                    este, norte = round(cent.X, 1), round(cent.Y, 1)
                except Exception:
                    este = norte = None
                fila = [None] * len(campos_insert)
                fila[0] = geom
                if i_acod >= 0:
                    fila[i_acod] = acr_codi
                if i_nom >= 0:
                    fila[i_nom] = str(acr_nomb)[:100]
                if i_fue >= 0:
                    fila[i_fue] = cod_md_fuente
                if i_anno >= 0:
                    fila[i_anno] = ANNO
                if i_sup >= 0:
                    fila[i_sup] = round(float(area_ha), 6) if area_ha else None
                if i_este >= 0:
                    fila[i_este] = este
                if i_nor >= 0:
                    fila[i_nor] = norte
                if i_mes >= 0:
                    fila[i_mes] = 12
                if i_fini >= 0:
                    fila[i_fini] = fecha_ini
                if i_ffin >= 0:
                    fila[i_ffin] = fecha_fin
                if i_fecimg >= 0 and fec_img:
                    fila[i_fecimg] = fec_img
                    n_fecha += 1
                if i_causa >= 0:
                    fila[i_causa] = 99
                if i_conf >= 0:
                    fila[i_conf] = 1
                if i_bosque >= 0:
                    fila[i_bosque] = 1
                ic.insertRow(fila)
                ins += 1

    print(f"Insertadas: {ins:,}  |  con md_fecimg: {n_fecha:,}")

    # Enriquecer solo MPA 2025
    print("[6] Sector / zonif / EXA (solo ACR34 2025)...")
    fc_zon = os.path.join(gdb, "gpo_zonif_anp")
    fc_exa = os.path.join(gdb, "gpo_exa")
    fc_sectores = os.path.join(gdb, "gpo_sectores")
    if not arcpy.Exists(fc_sectores):
        fc_sectores = None
    h1_cfg = h1.h1_config_activa()
    col_fi = h1.resolver_campo_h1(
        fc_exa, h1_cfg.get("exa_campos", []),
        campos_list=[f.name for f in arcpy.ListFields(fc_exa)],
    ) if arcpy.Exists(fc_exa) else None
    campo_tz = h1.resolver_campo_h1(
        fc_zon, h1_cfg.get("zonif_campos", []),
        campos_list=[f.name for f in arcpy.ListFields(fc_zon)],
    ) if arcpy.Exists(fc_zon) else None

    # where original es solo md_anno; hacemos join a una capa filtrada
    sel = os.path.join("in_memory", "mpa25_sel")
    h1._borrar_fc(sel)
    arcpy.conversion.FeatureClassToFeatureClass(
        dst, "in_memory", "mpa25_sel",
        where_clause="anp_codi = 'ACR34' AND md_anno = 2025",
    )
    try:
        h1._enriquecer_alertas_batch(
            sel, gdb, ANNO, fc_zon, campo_tz, fc_sectores, fc_exa, col_fi, _log
        )
        # copiar sector/zonif/exa de sel al destino por OID no sirve (OID nuevo)
        # Spatial join results estan en sel; transferir por centroide/OID del sel
        campos_d = {f.name.lower(): f.name for f in arcpy.ListFields(dst)}
        oid_sel = arcpy.Describe(sel).OIDFieldName
        oid_dst = arcpy.Describe(dst).OIDFieldName
        # sel es copia: OIDs distintos. Update destino con search de sel usando SHAPE
        # Mas simple: Calculate via join on a temp layer of dst
    except Exception as ex:
        print("AVISO enrich copia:", ex)

    lyr_d = "lyr_dst_mpa25"
    if arcpy.Exists(lyr_d):
        arcpy.management.Delete(lyr_d)
    arcpy.management.MakeFeatureLayer(
        dst, lyr_d, "anp_codi = 'ACR34' AND md_anno = 2025"
    )
    try:
        h1._enriquecer_alertas_batch(
            lyr_d, gdb, ANNO, fc_zon, campo_tz, fc_sectores, fc_exa, col_fi, _log
        )
    except Exception as ex:
        print("AVISO enrich lyr:", ex)

    try:
        from atd_codigo_alerta import asegurar_campo_md_codigo, asignar_codigos_faltantes
        asegurar_campo_md_codigo(dst)
        n_cod = asignar_codigos_faltantes(dst, anno=ANNO)
        print(f"md_codigo asignados (año 2025, faltantes): {n_cod}")
    except Exception as ex:
        print("AVISO md_codigo:", ex)

    n_dst = int(arcpy.management.GetCount(dst)[0])
    arcpy.management.MakeFeatureLayer(
        dst, "lyr_cnt", "anp_codi = 'ACR34'"
    )
    n_34 = int(arcpy.management.GetCount("lyr_cnt")[0])
    arcpy.management.SelectLayerByAttribute(
        "lyr_cnt", "NEW_SELECTION", "anp_codi = 'ACR34' AND md_anno = 2025"
    )
    n_34_25 = int(arcpy.management.GetCount("lyr_cnt")[0])
    print(f"Acumulado total: {n_dst:,} | ACR34: {n_34:,} | ACR34-2025: {n_34_25:,}")
    print("OK")


if __name__ == "__main__":
    main()

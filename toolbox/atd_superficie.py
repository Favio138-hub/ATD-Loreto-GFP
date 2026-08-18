# -*- coding: utf-8 -*-
"""Recalcula md_sup (ha geodesic) al editar el poligono. Usado por H2/H3."""
from __future__ import annotations

REGLA_NOMBRE = "ATD_md_sup_geodesica"
ARCADE_SUP = """
var ha = AreaGeodetic($feature, 'hectares');
if (ha == null || ha <= 0) {
    ha = Area($feature, 'hectares');
}
return Round(ha, 6);
"""


def _campos(fc):
    import arcpy
    return {f.name.lower(): f.name for f in arcpy.ListFields(fc)}


def actualizar_md_sup(fc, where=None) -> int:
    """Escribe md_sup (ha geodesic) y centroide md_este/md_norte."""
    import arcpy
    if not fc or not arcpy.Exists(fc):
        return 0
    campos = _campos(fc)
    if "md_sup" not in campos:
        return 0
    oid = arcpy.Describe(fc).OIDFieldName
    upd = [oid, "SHAPE@", campos["md_sup"]]
    i_este = i_norte = None
    if "md_este" in campos:
        i_este = len(upd)
        upd.append(campos["md_este"])
    if "md_norte" in campos:
        i_norte = len(upd)
        upd.append(campos["md_norte"])
    n = 0
    with arcpy.da.UpdateCursor(fc, upd, where) as cur:
        for row in cur:
            geom = row[1]
            if geom is None:
                continue
            try:
                ha = geom.getArea("GEODESIC", "HECTARES")
            except Exception:
                try:
                    ha = geom.getArea("PLANAR", "HECTARES")
                except Exception:
                    continue
            row[2] = round(float(ha or 0), 6)
            try:
                cent = geom.centroid
                if i_este is not None:
                    row[i_este] = round(cent.X, 1)
                if i_norte is not None:
                    row[i_norte] = round(cent.Y, 1)
            except Exception:
                pass
            cur.updateRow(row)
            n += 1
    return n


def asegurar_regla_superficie(fc) -> str:
    """Regla de calculo: al insertar/editar Shape, actualiza md_sup."""
    import arcpy
    if not fc or not arcpy.Exists(fc):
        return "sin FC"
    campos = _campos(fc)
    if "md_sup" not in campos:
        return "sin md_sup"
    existentes = []
    try:
        existentes = [
            r.name for r in (arcpy.Describe(fc).attributeRules or [])
        ]
    except Exception:
        existentes = []
    if REGLA_NOMBRE in existentes:
        return "ya existia"
    try:
        tiene_gid = any(f.type == "GlobalID" for f in arcpy.ListFields(fc))
        if not tiene_gid:
            try:
                arcpy.management.AddGlobalIDs(fc)
            except Exception as ex_gid:
                return "sin GlobalID (" + str(ex_gid) + ")"
        arcpy.management.AddAttributeRule(
            in_table=fc,
            name=REGLA_NOMBRE,
            type="CALCULATION",
            script_expression=ARCADE_SUP,
            is_editable="EDITABLE",
            triggering_events="INSERT;UPDATE",
            description="Superficie ha geodesic al editar el poligono",
            field=campos["md_sup"],
            exclude_from_client_evaluation="false",
            triggering_fields="Shape",
        )
        return "creada"
    except Exception as ex:
        return "error: " + str(ex)

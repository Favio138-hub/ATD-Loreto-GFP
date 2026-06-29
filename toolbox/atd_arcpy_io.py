# -*- coding: utf-8 -*-
"""
Lectura de alertas ATD solo con arcpy (sin GeoPandas / Shapely / pyogrio).
Evita cierres de ArcGIS Pro por conflictos de DLL con librerias en AppData.
"""
from __future__ import annotations

import arcpy
import os
from datetime import datetime

from atd_region_config import (
    ACR_CODIGOS_FC,
    ACR_NOMBRES,
    ACR_SIGLAS,
    FC_ALERTAS_PRIORIDAD,
    normalizar_anp_codi,
    valor_anp_desde_registro,
    configurar_region,
)

DOMINIO_CAUSA = {
    1: "Agricultura", 2: "Ganaderia", 3: "Extraccion Forestal",
    4: "Extraccion de Fauna", 5: "Hidrologicos", 6: "Mineria",
    7: "Hidrocarburos", 8: "Turismo", 9: "Energia",
    10: "Transporte / Infraestructura", 11: "Ocupacion Humana",
    12: "Restos Arqueologicos", 13: "Otros",
    14: "Natural", 15: "Incendio Antropico",
    16: "Falsa Alerta", 99: "Sin Clasificar",
}
CAUSAS_NO_ANTROPICAS = {14, 16}
_CAUSA_TEXTO_A_INT = {
    v.lower().strip(): k for k, v in DOMINIO_CAUSA.items()
}
DOMINIO_BOSQUE = {
    1: "Primario", 2: "Secundario", 3: "Sin Bosque",
    4: "Aguajal", 5: "Varillal", 6: "No determinado",
}


def _etiqueta_confianza(valor):
    try:
        dom = {1: "Alta (prioritaria para revision)", 2: "Media (revisar en campo)",
               3: "Baja (complementar con visita)"}
        return dom.get(int(valor), "Sin clasificar")
    except Exception:
        return "Sin clasificar"


def _parse_fecha(val):
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.replace(tzinfo=None)
    s = str(val).strip()
    if not s:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y"):
        try:
            return datetime.strptime(s[:19], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s[:19])
    except Exception:
        return None


def _parse_fecha_param(texto):
    return _parse_fecha(texto)


def _campo_fecha(fc_path):
    names = [f.name for f in arcpy.ListFields(fc_path)]
    for cand in ("md_fecimg", "MD_FECIMG", "Md_Fecimg", "fecha_imagen", "Fecha_imagen"):
        if cand in names:
            return cand
    for n in names:
        nl = n.lower()
        if "fec" in nl and "img" in nl:
            return n
    return None


def _fin_periodo_inclusivo(fecha_fin):
    ff = _parse_fecha_param(fecha_fin)
    if ff:
        return ff.replace(hour=23, minute=59, second=59, microsecond=0)
    return ff


def _where_sql_periodo(campo_fec, fi, ff, oid_field=None, objectid=None):
    """Solo fecha en SQL; causa/ACR se filtran en Python."""
    wheres = []
    if campo_fec and fi and ff:
        wheres.append(
            f"(({campo_fec} >= timestamp '{fi:%Y-%m-%d} 00:00:00') AND "
            f"({campo_fec} <= timestamp '{ff:%Y-%m-%d} 23:59:59'))"
        )
    if objectid is not None and oid_field:
        wheres.append(f"{oid_field} = {int(objectid)}")
    return " AND ".join(wheres) if wheres else None


def _campos_atributos(fc_path):
    omitir = {"Geometry", "OID", "GlobalID", "GUID"}
    names = []
    for f in arcpy.ListFields(fc_path):
        if f.type in omitir:
            continue
        if f.name.upper() in ("SHAPE", "SHAPE_LENGTH", "SHAPE_AREA"):
            continue
        names.append(f.name)
    return names


def _parse_causa_int(rec):
    """Acepta md_causa numerico o texto ('Agricultura', dominio GeoBosques)."""
    raw = rec.get("md_causa")
    if raw is None or (isinstance(raw, str) and not str(raw).strip()):
        for alt in ("uso_suelo", "md_uso", "Uso_suelo", "USO_SUELO", "causa"):
            v = rec.get(alt)
            if v is not None and str(v).strip():
                raw = v
                break
        if raw is None:
            for k, v in rec.items():
                if v is None or not str(v).strip():
                    continue
                kn = str(k).lower().replace("ó", "o").replace("í", "i")
                if ("uso" in kn and "suelo" in kn) or "causa" in kn:
                    raw = v
                    break
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        s = str(raw).strip().lower()
        if s in _CAUSA_TEXTO_A_INT:
            return _CAUSA_TEXTO_A_INT[s]
        for txt, cod in _CAUSA_TEXTO_A_INT.items():
            if s == txt or s.startswith(txt) or txt.startswith(s):
                return cod
        return None


def _enriquecer_registro(rec):
    cod = normalizar_anp_codi(valor_anp_desde_registro(rec))
    cod = str(cod).strip() if cod else ""
    rec["anp_codi"] = cod
    causa_int = _parse_causa_int(rec)
    rec["_causa_int"] = causa_int
    rec["causa_texto"] = (
        DOMINIO_CAUSA.get(causa_int, f"Codigo {causa_int}")
        if causa_int is not None else "Sin clasificar"
    )
    rec["conf_texto"] = (
        _etiqueta_confianza(rec["md_conf"])
        if rec.get("md_conf") is not None else "Sin clasificar"
    )
    try:
        b = int(rec["md_bosque"]) if rec.get("md_bosque") is not None else None
    except (TypeError, ValueError):
        b = None
    rec["bosque_texto"] = DOMINIO_BOSQUE.get(b, "-") if b is not None else "-"
    rec["acr_nombre"] = ACR_NOMBRES.get(cod, cod)
    rec["acr_sigla"] = ACR_SIGLAS.get(cod, cod)
    rec["lugar_poblado"] = rec.get("lugar_poblado") or "-"
    rec["sector_reporte"] = rec.get("sector_reporte") or "-"
    rec["olv_cercano"] = rec.get("olv_cercano") or "-"

    este = rec.get("md_este")
    norte = rec.get("md_norte")
    try:
        rec["este_utm"] = float(este) if este is not None else None
    except (TypeError, ValueError):
        rec["este_utm"] = None
    try:
        rec["norte_utm"] = float(norte) if norte is not None else None
    except (TypeError, ValueError):
        rec["norte_utm"] = None
    return rec


def _fcs_alertas_lectura(gdb_path, fc_alertas):
    """Capa(s) de alertas a leer. Si se indica fc_alertas, solo esa capa."""
    try:
        arcpy.env.workspace = gdb_path
        avail = set(arcpy.ListFeatureClasses() or [])
    except Exception:
        avail = set()
    if fc_alertas and fc_alertas in avail:
        return [fc_alertas]
    orden = []
    for cand in FC_ALERTAS_PRIORIDAD:
        if cand in avail and cand not in orden:
            orden.append(cand)
    if not orden and fc_alertas:
        orden = [fc_alertas]
    return orden


def _leer_alertas_una_fc(
    gdb_path,
    fc_alertas,
    fecha_ini,
    fecha_fin,
    objectid=None,
    acr_filtro="",
    msg_fn=None,
):
    fn = msg_fn or (lambda _x: None)
    fc_path = os.path.join(gdb_path, fc_alertas)
    if not arcpy.Exists(fc_path):
        return []

    oid_field = arcpy.Describe(fc_path).OIDFieldName
    campo_fec = _campo_fecha(fc_path)
    fi = _parse_fecha_param(fecha_ini)
    ff = _fin_periodo_inclusivo(fecha_fin)
    if not fi or not ff:
        raise ValueError("Fechas de periodo no validas")

    attr_fields = _campos_atributos(fc_path)
    if oid_field not in attr_fields:
        attr_fields = [oid_field] + attr_fields
    cursor_fields = ["SHAPE@"] + attr_fields

    def _procesar_fila(row):
        geom = row[0]
        data = dict(zip(attr_fields, row[1:]))
        data["objectid"] = data.get(oid_field, data.get("OBJECTID"))
        if data["objectid"] is None and oid_field in data:
            data["objectid"] = data[oid_field]
        if geom and (data.get("este_utm") is None or data.get("norte_utm") is None):
            try:
                c = geom.trueCentroid
                if data.get("md_este") is None:
                    data["md_este"] = c.X
                if data.get("md_norte") is None:
                    data["md_norte"] = c.Y
            except Exception:
                pass
        rec = _enriquecer_registro(data)
        rec["_fc_origen"] = fc_alertas
        if rec["anp_codi"] not in ACR_CODIGOS_FC:
            fn(
                f"  AVISO [{fc_alertas}]: OID {rec.get('objectid')} omitido — "
                f"ACR no reconocido: '{valor_anp_desde_registro(data)}' "
                f"-> '{rec['anp_codi']}'"
            )
            return None
        if rec["_causa_int"] in CAUSAS_NO_ANTROPICAS:
            fn(
                f"  AVISO [{fc_alertas}]: OID {rec.get('objectid')} omitido — "
                f"causa no antropica ({rec.get('md_causa')!r})"
            )
            return None
        if rec["_causa_int"] is None:
            try:
                sup = float(rec.get("md_sup") or 0)
            except (TypeError, ValueError):
                sup = 0.0
            if sup > 0:
                rec["_causa_int"] = 99
                rec["causa_texto"] = "Sin clasificar (sin md_causa en GDB)"
                fn(
                    f"  AVISO [{fc_alertas}]: OID {rec.get('objectid')} sin md_causa — "
                    f"incluida como pendiente ({sup:.4f} ha)"
                )
            else:
                fn(
                    f"  AVISO [{fc_alertas}]: OID {rec.get('objectid')} omitido — "
                    f"sin causa ni superficie"
                )
                return None
        fimg = _parse_fecha(
            rec.get("md_fecimg") or rec.get(campo_fec or "") or data.get(campo_fec or "")
        )
        if fimg is None or fimg < fi or fimg > ff:
            fn(
                f"  AVISO [{fc_alertas}]: OID {rec.get('objectid')} omitido — "
                f"fecha fuera de periodo ({rec.get('md_fecimg')!r})"
            )
            return None
        rec["md_fecimg"] = fimg
        if acr_filtro and rec["anp_codi"] != acr_filtro:
            return None
        return rec

    registros = []
    where_opts = []
    ws = _where_sql_periodo(campo_fec, fi, ff, oid_field, objectid)
    if ws:
        where_opts.append(ws)
    if objectid is None:
        where_opts.append(None)

    for where_sql in where_opts:
        n_leidas = 0
        tmp = []
        with arcpy.da.SearchCursor(
            fc_path, cursor_fields, where_clause=where_sql
        ) as cur:
            for row in cur:
                n_leidas += 1
                rec = _procesar_fila(row)
                if rec:
                    tmp.append(rec)
        fn(
            f"  [{fc_alertas}] SQL {'(sin filtro)' if where_sql is None else 'fecha'}: "
            f"{n_leidas:,} filas -> {len(tmp):,} validas"
        )
        if tmp:
            registros = tmp
            break
        if where_sql is not None:
            fn(f"  AVISO [{fc_alertas}]: 0 alertas con filtro SQL; reintentando sin filtro...")
    return registros


def leer_alertas_arcpy(
    gdb_path,
    fc_alertas,
    fecha_ini,
    fecha_fin,
    objectid=None,
    acr_filtro="",
    msg_fn=None,
):
    """
    Devuelve lista de dict (una fila = una alerta) filtrada por periodo y ACR.
    Lee MonitoreoDeforestacion y MonitoreoDeforestacionAcumulado cuando existen.
    """
    fn = msg_fn or (lambda _x: None)
    configurar_region(gdb_path)
    fcs = _fcs_alertas_lectura(gdb_path, fc_alertas)
    if not fcs:
        raise RuntimeError(f"No hay capas de alertas en: {gdb_path}")

    registros = []
    vistos = set()
    for fc in fcs:
        tmp = _leer_alertas_una_fc(
            gdb_path, fc, fecha_ini, fecha_fin, objectid, acr_filtro, fn
        )
        for rec in tmp:
            key = (
                rec.get("_fc_origen"),
                rec.get("objectid"),
                rec.get("md_alert"),
                str(rec.get("md_fecimg")),
            )
            if key in vistos:
                continue
            vistos.add(key)
            registros.append(rec)

    fn(f"  Lectura arcpy total: {len(registros):,} alertas en periodo ({len(fcs)} capa(s))")
    return registros


def etiqueta_alerta(rec):
    oid = rec.get("objectid", "?")
    cod = str(rec.get("anp_codi", "")).strip()
    causa = rec.get("causa_texto", "?")
    sup = float(rec.get("md_sup", 0) or 0)
    fec = rec.get("md_fecimg")
    fec_s = fec.strftime("%d/%m/%Y") if isinstance(fec, datetime) else "sin fecha"
    nom = str(rec.get("acr_nombre", cod))
    if len(nom) > 36:
        nom = nom[:33] + "..."
    return f"OID:{oid}|{nom} — {causa} — {sup:.2f} ha — imagen {fec_s} (ref. {cod})"


def listar_opciones_alertas_arcpy(gdb_path, fc_alertas, fecha_ini, fecha_fin, acr_filtro=""):
    registros = leer_alertas_arcpy(
        gdb_path, fc_alertas, fecha_ini, fecha_fin, acr_filtro=acr_filtro
    )
    if not registros:
        return ["[SIN ALERTAS] Revise fechas en Diagnostico Pre-Vuelo"], []
    opts = [f"[TODAS] Generar las {len(registros)} alertas del periodo"]
    for rec in registros:
        opts.append(etiqueta_alerta(rec))
    return opts, registros


def resumen_diagnostico(registros):
    """Texto de resumen para herramienta 1 (sin pandas)."""
    from collections import defaultdict

    by_acr = defaultdict(list)
    by_causa = defaultdict(int)
    fechas = []
    for r in registros:
        by_acr[r["anp_codi"]].append(r)
        by_causa[r["_causa_int"]] += 1
        if isinstance(r.get("md_fecimg"), datetime):
            fechas.append(r["md_fecimg"])
    return by_acr, by_causa, fechas


def _parse_atributos_etiqueta(texto):
    import re

    t = str(texto or "").strip()
    if not t or t.upper().startswith("[TODAS]") or t.startswith("[SIN"):
        return None
    t = re.sub(r"^OID:\d+\|", "", t)
    m = re.match(
        r"^(.*?) — (.+?) — ([\d.]+) ha — imagen ([\d/]+) \(ref\. ([^)]+)\)$",
        t,
    )
    if not m:
        m = re.match(
            r"^(.*?) — (.+?) — ([\d.]+) ha — imagen ([\d/]+) "
            r"\(ref\. ([^,]+), ID (.+)\)$",
            t,
        )
    if not m:
        return None
    return {
        "causa": m.group(2).strip(),
        "sup": float(m.group(3)),
        "fecha": _parse_fecha(m.group(4)),
        "acr": str(m.group(5)).strip(),
    }


def parse_seleccion_alerta(texto):
    import re

    t = str(texto or "").strip()
    if not t or t.startswith("[SIN") or t.startswith("[Paso 1]"):
        return "sin_alertas"
    if t.upper().startswith("[TODAS]"):
        return None
    m = re.search(r"OID:\s*(\d+)", t, re.I)
    if m:
        return int(m.group(1))
    if "OID:" in t:
        try:
            return int(str(t).split("|")[0].replace("OID:", "").strip())
        except ValueError:
            pass
    m = re.search(r",\s*ID\s+(\d+)\)", t)
    if m:
        return int(m.group(1))
    if _parse_atributos_etiqueta(t):
        return "match_attrs"
    if t and not t.upper().startswith("[TODAS]"):
        return "match_attrs"
    return None


def filtrar_registros_por_etiqueta(registros, texto):
    attrs = _parse_atributos_etiqueta(texto)
    if not attrs or not attrs.get("fecha"):
        return []
    out = []
    for r in registros:
        f = r.get("md_fecimg")
        if isinstance(f, str):
            f = _parse_fecha(f)
        if (
            str(r.get("anp_codi", "")).strip() == attrs["acr"]
            and str(r.get("causa_texto", "")).strip() == attrs["causa"]
            and abs(float(r.get("md_sup") or 0) - attrs["sup"]) < 0.011
            and isinstance(f, datetime)
            and f.date() == attrs["fecha"].date()
        ):
            out.append(r)
    return out


def filtrar_registros_seleccion(registros, alerta_sel):
    sel = parse_seleccion_alerta(alerta_sel)
    if sel == "sin_alertas":
        return None, "sin_alertas"
    if sel is None:
        return registros, "todas"
    if isinstance(sel, int):
        out = [r for r in registros if int(r.get("objectid", -1)) == sel]
        return (out, "una") if out else ([], "no_oid")
    if sel == "match_attrs":
        return filtrar_registros_por_etiqueta(registros, alerta_sel), "match"
    return [], "invalid"

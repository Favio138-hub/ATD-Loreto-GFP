# -*- coding: utf-8 -*-
"""
Nomenclatura institucional de código de alerta ACR:
  ACR## - YYYY - ###   (ej. ACR04 - 2026 - 015)

Usado por H1 (asignación en GDB), H2 (visor) y H3 (PDF).
"""
from __future__ import annotations

import re
from datetime import datetime

_RE_CODIGO = re.compile(
    r"^(ACR\d{2})\s*-\s*(\d{4})\s*-\s*(\d{1,3})$",
    re.IGNORECASE,
)


def normalizar_acr_prefijo(cod: str) -> str:
    """Devuelve ACR## a partir de anp_codi / acr_codi."""
    s = str(cod or "").strip().upper().replace(" ", "").replace("_", "")
    if not s:
        return "ACR00"
    m = re.match(r"ACR(\d+)$", s)
    if m:
        return f"ACR{int(m.group(1)):02d}"
    if s.isdigit():
        return f"ACR{int(s):02d}"
    return s[:10]


def formatear_codigo_alerta(
    acr_codi: str,
    anno,
    correlativo,
    sep: str = " - ",
) -> str:
    """Formato oficial: ACR04 - 2026 - 015."""
    pref = normalizar_acr_prefijo(acr_codi)
    try:
        yr = int(anno)
    except (TypeError, ValueError):
        yr = datetime.now().year
    try:
        n = max(1, int(correlativo))
    except (TypeError, ValueError):
        n = 1
    return f"{pref}{sep}{yr}{sep}{n:03d}"


def parse_codigo_alerta(texto: str) -> tuple[str, int, int] | None:
    """Parsea 'ACR04 - 2026 - 015' -> ('ACR04', 2026, 15)."""
    m = _RE_CODIGO.match(str(texto or "").strip())
    if not m:
        return None
    return m.group(1).upper(), int(m.group(2)), int(m.group(3))


def _anno_valor(val) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return datetime.now().year


def _campo_existe(fc: str, nombre: str) -> bool:
    import arcpy
    return any(
        f.name.lower() == nombre.lower()
        for f in arcpy.ListFields(fc)
    )


def asegurar_campo_md_codigo(fc: str) -> str:
    """Crea md_codigo si no existe. Devuelve nombre del campo."""
    import arcpy
    campos = {f.name.lower(): f.name for f in arcpy.ListFields(fc)}
    if "md_codigo" in campos:
        return campos["md_codigo"]
    arcpy.management.AddField(
        fc, "md_codigo", "TEXT", field_length=25,
        field_alias="Código de alerta",
    )
    return "md_codigo"


def _max_correlativos(fc: str, filtro_anno: int | None = None) -> dict[tuple[str, int], int]:
    """Máximo correlativo por (ACR, año) según md_codigo existente."""
    import arcpy
    campos = {f.name.lower(): f.name for f in arcpy.ListFields(fc)}
    if "md_codigo" not in campos:
        return {}
    f_cod = campos["md_codigo"]
    f_acr = campos.get("anp_codi") or campos.get("acr_codi")
    f_anno = campos.get("md_anno")
    if not f_acr:
        return {}

    leer = [f_cod, f_acr]
    where = None
    if f_anno:
        leer.append(f_anno)
        if filtro_anno is not None:
            where = f"{f_anno} = {int(filtro_anno)}"

    max_map: dict[tuple[str, int], int] = {}
    with arcpy.da.SearchCursor(fc, leer, where) as cur:
        for row in cur:
            parsed = parse_codigo_alerta(row[0])
            acr = normalizar_acr_prefijo(row[1])
            if parsed:
                acr_p, yr_p, n_p = parsed
                acr = acr_p
                yr = yr_p
                max_map[(acr, yr)] = max(max_map.get((acr, yr), 0), n_p)
            elif f_anno and len(row) > 2:
                yr = _anno_valor(row[2])
                max_map.setdefault((acr, yr), 0)
    return max_map


def asignar_codigos_faltantes(fc: str, anno: int | None = None) -> int:
    """
    Asigna md_codigo a registros sin código.
    Correlativo por ACR + año, orden OBJECTID.
    """
    import arcpy

    f_cod = asegurar_campo_md_codigo(fc)
    campos = {f.name.lower(): f.name for f in arcpy.ListFields(fc)}
    f_acr = campos.get("anp_codi") or campos.get("acr_codi")
    f_anno = campos.get("md_anno")
    oid_f = arcpy.Describe(fc).OIDFieldName
    if not f_acr:
        return 0

    leer = [oid_f, f_acr, f_cod]
    if f_anno:
        leer.append(f_anno)
    where = None
    if anno is not None and f_anno:
        where = f"{f_anno} = {int(anno)}"

    pendientes: list[tuple] = []
    max_map = _max_correlativos(fc)

    with arcpy.da.SearchCursor(fc, leer, where) as cur:
        for row in cur:
            oid, acr, cod_ex = row[0], row[1], row[2]
            yr = _anno_valor(row[3]) if f_anno and len(row) > 3 else datetime.now().year
            if cod_ex and str(cod_ex).strip():
                parsed = parse_codigo_alerta(cod_ex)
                if parsed:
                    acr_p, yr_p, n_p = parsed
                    max_map[(acr_p, yr_p)] = max(max_map.get((acr_p, yr_p), 0), n_p)
                continue
            pendientes.append((oid, normalizar_acr_prefijo(acr), yr))

    pendientes.sort(key=lambda x: (x[1], x[2], x[0]))
    asignados: dict[tuple[str, int], list[tuple[int, str]]] = {}
    for oid, acr, yr in pendientes:
        key = (acr, yr)
        n = max_map.get(key, 0) + 1
        max_map[key] = n
        cod = formatear_codigo_alerta(acr, yr, n)
        asignados.setdefault(key, []).append((oid, cod))

    oid_to_cod = {
        oid: cod for pairs in asignados.values() for oid, cod in pairs
    }
    n_ok = 0
    with arcpy.da.UpdateCursor(fc, [oid_f, f_cod]) as cur:
        for row in cur:
            if row[0] in oid_to_cod:
                row[1] = oid_to_cod[row[0]]
                cur.updateRow(row)
                n_ok += 1
    return n_ok


def resolver_codigo_alerta(
    row,
    correlativo: int | None = None,
    anno_fallback: int | None = None,
) -> str:
    """
    Código desde md_codigo en fila (dict/Series) o formato calculado.
    row: dict-like con anp_codi, md_anno, md_codigo (opcional).
    """
    cod_guardado = None
    if hasattr(row, "get"):
        cod_guardado = row.get("md_codigo")
    if cod_guardado and str(cod_guardado).strip():
        parsed = parse_codigo_alerta(cod_guardado)
        if parsed:
            return formatear_codigo_alerta(*parsed[:2], parsed[2])
        return str(cod_guardado).strip()

    acr = ""
    if hasattr(row, "get"):
        acr = row.get("anp_codi") or row.get("acr_codi") or ""
    anno = anno_fallback
    if hasattr(row, "get") and row.get("md_anno") not in (None, "", 0):
        anno = row.get("md_anno")
    if correlativo is None and hasattr(row, "get"):
        correlativo = row.get("_corr_alerta")
    if correlativo is None:
        correlativo = 1
    return formatear_codigo_alerta(acr, anno, correlativo)


def mapa_correlativos_dataframe(df) -> dict:
    """
    OID/objectid -> correlativo estable por (anp_codi, md_anno), orden OBJECTID.
    Para H3 cuando md_codigo aún no está en GDB.
    """
    if df is None or len(df) == 0:
        return {}
    oid_col = "objectid" if "objectid" in df.columns else "OBJECTID"
    out: dict = {}
    grupos = {}
    for idx, row in df.iterrows():
        oid = row.get(oid_col, idx)
        acr = normalizar_acr_prefijo(row.get("anp_codi", ""))
        yr = _anno_valor(row.get("md_anno"))
        grupos.setdefault((acr, yr), []).append(oid)
    for _key, oids in grupos.items():
        for i, oid in enumerate(sorted(oids), start=1):
            out[oid] = i
    return out


def enrich_dataframe_codigos(df, anno_fallback: int | None = None):
    """Añade columna codigo_alerta al DataFrame de H3."""
    if df is None or len(df) == 0:
        return df
    corr_map = mapa_correlativos_dataframe(df)
    oid_col = "objectid" if "objectid" in df.columns else "OBJECTID"

    def _fila_cod(row):
        if row.get("md_codigo") and str(row.get("md_codigo")).strip():
            return resolver_codigo_alerta(row, anno_fallback=anno_fallback)
        oid = row.get(oid_col)
        return resolver_codigo_alerta(
            row,
            correlativo=corr_map.get(oid, 1),
            anno_fallback=anno_fallback,
        )

    df = df.copy()
    df["codigo_alerta"] = df.apply(_fila_cod, axis=1)
    return df

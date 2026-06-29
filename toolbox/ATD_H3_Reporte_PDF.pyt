"""
===============================================================================
REPORTE ATD - ArcGIS Pro Toolbox

GFP Subnacional / Loreto · Cuzco · San Martin
===============================================================================
"""
__version__ = "1.1.4"

import arcpy
import json
import os
import sys
import time
import traceback
import warnings
from datetime import datetime

_toolbox_dir = os.path.dirname(os.path.abspath(__file__))
if _toolbox_dir not in sys.path:
    sys.path.insert(0, _toolbox_dir)


def _sanear_sys_path():
    """Quita paquetes pip en AppData/Roaming que suelen cerrar ArcGIS Pro."""
    roaming = os.path.join(os.environ.get("APPDATA", ""), "Python")
    if not roaming:
        return
    sys.path[:] = [
        p for p in sys.path
        if not p.replace("/", "\\").lower().startswith(roaming.lower())
    ]


_sanear_sys_path()

from atd_arcpy_io import (
    _parse_fecha,
    _parse_causa_int,
    filtrar_registros_por_etiqueta,
    filtrar_registros_seleccion,
    listar_opciones_alertas_arcpy,
    parse_seleccion_alerta,
)
from atd_imagenes_h3 import (
    buscar_imagen_local,
    marcar_png_con_alerta,
    quemar_vector_alerta_en_imagen,
    resolver_oid_imagen,
)
from atd_region_config import (
    REGION_CONFIGS,
    DEFAULT_GDB_LORETO,
    DEFAULT_GESTION_GDB_LORETO,
    configurar_region,
    sincronizar_imports_region,
    acr_opciones_filtro,
    _detectar_region,
    _utm_epsg_region,
    resolver_fc_alertas,
    normalizar_anp_codi,
    valor_anp_desde_registro,
    enriquecer_ubicacion_alertas,
    GESTION_GDB_ACTIVA,
    _REGION_ACTIVA,
    ACR_NOMB_TO_CODI,
    ACR_NOMBRES,
    ACR_SIGLAS,
    ACR_GEO,
    ZI_CODI_TO_ACR,
    SIGLA_TO_ACR,
    ACR_CODIGOS_FC,
    REGION_NOMBRE,
    DEPARTAMENTO_REPORTE,
    GOBIERNO_REGIONAL,
    GERENCIA_REGIONAL,
    SUBGERENCIA_REGIONAL,
    LOGO_REGION_KEY,
    REPORTE_TAG,
    TEXTO_CIERRE,
    URL_DASHBOARD_ACR,
)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_GDB = DEFAULT_GDB_LORETO
DEFAULT_SALIDA = _PROJECT_ROOT

DOMINIO_CAUSA = {
    1: "Agricultura", 2: "Ganaderia", 3: "Extraccion Forestal",
    4: "Extraccion de Fauna", 5: "Hidrologicos", 6: "Mineria",
    7: "Hidrocarburos", 8: "Turismo", 9: "Energia",
    10: "Transporte / Infraestructura", 11: "Ocupacion Humana",
    12: "Restos Arqueologicos", 13: "Otros",
    14: "Natural", 15: "Incendio Antropico",
    16: "Falsa Alerta", 99: "Sin Clasificar",
}
CAUSAS_NO_ANTROPICAS = {14, 16, None}
DOMINIO_CONF = {
    1: "Alta (prioritaria para revisión)",
    2: "Media (revisar en campo)",
    3: "Baja (complementar con visita)",
}
DOMINIO_BOSQUE = {
    1: "Primario", 2: "Secundario", 3: "Sin Bosque",
    4: "Aguajal", 5: "Varillal", 6: "No determinado",
}
try:
    configurar_region(DEFAULT_GDB, force=True)
except Exception:
    pass

# Valores internos (no visibles en Generar Reporte; fechas se ajustan en Diagnostico)
INTERNAL_FECHA_INI = "01/03/2026"
INTERNAL_FECHA_FIN = "01/05/2026"
GEE_DIAS_DEFAULT = 45
GEE_NUBES_DEFAULT = 35
GEE_PROJECT_EJEMPLO = "ee-favio"

# Zona de influencia en gpo_anp_monit (acr_codi tipo ZI ...)

LIBS_REQUERIDAS = [
    ("geopandas", "geopandas"),
    ("fiona", "fiona"),
    ("pandas", "pandas"),
    ("numpy", "numpy"),
    ("matplotlib", "matplotlib"),
    ("PIL", "pillow"),
    ("pyproj", "pyproj"),
    ("reportlab", "reportlab"),
    ("requests", "requests"),
]

# Caché para evitar releer la GDB en cada updateParameters
_CACHE_ALERTAS = {"key": None, "opciones": None, "df": None, "ts": 0}


def _ruta_absoluta(ruta, base=None):
    """Convierte rutas relativas del proyecto a absolutas (validacion ArcGIS)."""
    if not ruta:
        return ruta
    base = base or _PROJECT_ROOT
    ruta = str(ruta).strip()
    if os.path.isdir(ruta) or os.path.isfile(ruta):
        return os.path.normpath(os.path.abspath(ruta))
    cand = os.path.join(base, ruta)
    if os.path.exists(cand):
        return os.path.normpath(os.path.abspath(cand))
    return os.path.normpath(os.path.abspath(os.path.join(base, ruta)))


def _get_logo_path(dir_logos, base_name, cod_acr=None, region_key=None, _cache=None):
    """ACR > región > genérico; admite .png/.jpeg y alias (Logo_GORE_Cuzco, etc.)."""
    from atd_logos import resolve_logo_path

    rk = region_key or LOGO_REGION_KEY or _REGION_ACTIVA or ""
    return resolve_logo_path(dir_logos, base_name, cod_acr, rk, cache=_cache)


def _etiqueta_confianza(valor):
    try:
        return DOMINIO_CONF.get(int(valor), "Sin clasificar")
    except Exception:
        return "Sin clasificar"


def verify_libraries(check_gee=True, check_contextily=True, omit_modulos=None, msg_fn=None):
    fn = msg_fn or arcpy.AddMessage
    omit = {m.lower() for m in (omit_modulos or [])}
    falta = []
    fn("Verificando librerias...")
    fn(f"  Python de ArcGIS Pro: {sys.executable}")
    fn(f"  Version: {sys.version.split()[0]}")
    for mod, pip_name in LIBS_REQUERIDAS:
        if mod.lower() in omit:
            fn(f"  -- {mod} (omitido en modo estable)")
            continue
        try:
            __import__(mod)
            fn(f"  OK {mod}")
        except ImportError as ex:
            falta.append(pip_name)
            fn(f"  FALTA {mod} (pip install {pip_name})")
            fn(f"       detalle: {ex}")
        except Exception as ex:
            falta.append(pip_name)
            fn(f"  ERROR al importar {mod}: {ex}")
            fn(f"       (reinstala con pip en el Python de arriba)")
    if check_contextily:
        try:
            __import__("contextily")
            fn("  OK contextily")
        except ImportError:
            fn("  AVISO: contextily no instalado (mapas sin basemap)")
    if check_gee:
        try:
            __import__("ee")
            fn("  OK ee")
        except ImportError:
            fn("  AVISO: ee no instalado (PDFs sin Sentinel-2)")
    return len(falta) == 0, falta


def normalize_oid_column(gdf):
    for col in list(gdf.columns):
        cl = col.lower()
        if cl in ("objectid", "fid", "ogc_fid") and col != "objectid":
            return gdf.rename(columns={col: "objectid"})
    if "objectid" not in gdf.columns:
        try:
            fc_hint = getattr(gdf, "name", None)
            if fc_hint and arcpy.Exists(str(fc_hint)):
                oid_f = arcpy.Describe(fc_hint).OIDFieldName
                if oid_f in gdf.columns:
                    return gdf.rename(columns={oid_f: "objectid"})
        except Exception:
            pass
    return gdf


def _gdb_absoluta_si_existe(gdb_path):
    """Ruta .gdb absoluta valida (os.path primero; evita cierres en updateParameters)."""
    if not gdb_path:
        return None
    gdb_abs = _ruta_absoluta(str(gdb_path).strip())
    if os.path.isdir(gdb_abs) and gdb_abs.lower().endswith(".gdb"):
        return gdb_abs
    try:
        if arcpy.Exists(gdb_abs):
            return gdb_abs
    except Exception:
        pass
    return None


def _set_param_si_cambia(param, valor):
    """Evita bucles de refresh en ArcGIS Pro al reasignar el mismo valor."""
    if valor is None:
        return
    try:
        if isinstance(valor, str) and (param.valueAsText or "") == valor:
            return
        if not isinstance(valor, str) and param.value == valor:
            return
        param.value = valor
    except Exception:
        try:
            param.value = valor
        except Exception:
            pass


def list_fc_in_gdb(gdb_path):
    gdb_abs = _gdb_absoluta_si_existe(gdb_path)
    if not gdb_abs:
        return []
    try:
        arcpy.env.workspace = gdb_abs
        return sorted(arcpy.ListFeatureClasses() or [])
    except Exception:
        return []


def _aplicar_region_desde_gdb(gdb_path, globals_dict=None, force=False):
    """Detecta region/ACR/FCs al cambiar la GDB en updateParameters o execute."""
    gdb_abs = _gdb_absoluta_si_existe(gdb_path)
    if not gdb_abs:
        return None
    configurar_region(gdb_abs, force=force)
    if globals_dict is not None:
        sincronizar_imports_region(globals_dict)
    return gdb_abs


def _rellenar_params_fc_gdb(parameters, ix, gdb_abs):
    """Actualiza desplegables de FC segun la GDB seleccionada."""
    fcs = list_fc_in_gdb(gdb_abs)
    if not fcs:
        return
    for key in ("fc_alertas", "fc_anp", "fc_zonif"):
        parameters[ix[key]].filter.list = fcs
    cur_al = parameters[ix["fc_alertas"]].valueAsText
    if cur_al not in fcs:
        parameters[ix["fc_alertas"]].value = resolver_fc_alertas(gdb_abs, fcs)
    defaults = {
        "fc_anp": ("gpo_anp_monit",),
        "fc_zonif": ("gpo_zonif_anp",),
    }
    for key, cands in defaults.items():
        cur = parameters[ix[key]].valueAsText
        if cur in fcs:
            continue
        pick = next((c for c in cands if c in fcs), fcs[0])
        parameters[ix[key]].value = pick


def _sql_fecha_campo(fc_path):
    """Devuelve nombre del campo de fecha de imagen si existe."""
    for cand in ("md_fecimg", "MD_FECIMG", "Md_Fecimg"):
        if cand in [f.name for f in arcpy.ListFields(fc_path)]:
            return cand
    return None


def _scratch_gdb_temporal():
    """GDB temporal en disco: GeoPandas/pyogrio no leen capas en in_memory/memory."""
    import tempfile

    scratch = getattr(arcpy.env, "scratchGDB", None) or ""
    if scratch and arcpy.Exists(scratch):
        return scratch

    tmp = os.path.join(tempfile.gettempdir(), f"atd_scratch_{os.getpid()}.gdb")
    if not arcpy.Exists(tmp):
        arcpy.management.CreateFileGDB(os.path.dirname(tmp), os.path.basename(tmp))
    return tmp


def _fc_a_geodataframe_cursor(fc_path):
    """Lee FC de arcpy sin depender de pyogrio/OpenFileGDB."""
    import geopandas as gpd
    from shapely import wkb

    desc = arcpy.Describe(fc_path)
    sr = desc.spatialReference
    crs = f"EPSG:{sr.factoryCode}" if sr and sr.factoryCode else None
    oid_field = desc.OIDFieldName

    omitir = {"Geometry", "OID", "GlobalID", "GUID"}
    fields = [
        f.name
        for f in arcpy.ListFields(fc_path)
        if f.type not in omitir
        and f.name.upper() not in ("SHAPE", "SHAPE_LENGTH", "SHAPE_AREA")
    ]
    if oid_field and oid_field not in fields:
        fields = [oid_field] + fields

    records, geoms = [], []
    with arcpy.da.SearchCursor(fc_path, ["SHAPE@"] + fields) as cur:
        for row in cur:
            geom = row[0]
            geoms.append(wkb.loads(bytes(geom.WKB)) if geom else None)
            records.append(list(row[1:]))
    gdf = gpd.GeoDataFrame(records, columns=fields, geometry=geoms, crs=crs)
    return normalize_oid_column(gdf)


def _fc_a_geodataframe(fc_path, msg_fn=None):
    """Convierte FC de arcpy a GeoDataFrame (SearchCursor; evita pyogrio en GDB)."""
    fn = msg_fn or (lambda _x: None)
    if not arcpy.Exists(fc_path):
        raise RuntimeError(f"Capa temporal no encontrada: {fc_path}")
    try:
        return _fc_a_geodataframe_cursor(fc_path)
    except Exception as ex_cur:
        fn(f"  AVISO: SearchCursor fallo ({ex_cur}); exportando shapefile...")
        import geopandas as gpd
        import tempfile
        import shutil

        tmp_dir = tempfile.mkdtemp(prefix="atd_shp_")
        shp = os.path.join(tmp_dir, "alertas.shp")
        try:
            arcpy.management.CopyFeatures(fc_path, shp)
            gdf = gpd.read_file(shp)
            return normalize_oid_column(gdf)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


def _leer_alerta_por_oid(gdb_path, fc_alertas, objectid, msg_fn=None):
    """Lee una sola alerta por OBJECTID (minima carga de memoria)."""
    fn = msg_fn or arcpy.AddMessage
    fc_path = os.path.join(gdb_path, fc_alertas)
    if not arcpy.Exists(fc_path):
        raise RuntimeError(f"No existe la capa: {fc_path}")

    oid_field = arcpy.Describe(fc_path).OIDFieldName
    scratch = _scratch_gdb_temporal()
    out_name = "ATD_una_alerta"
    out_fc = os.path.join(scratch, out_name)
    if arcpy.Exists(out_fc):
        arcpy.management.Delete(out_fc)

    arcpy.conversion.FeatureClassToFeatureClass(
        in_features=fc_path,
        out_path=scratch,
        out_name=out_name,
        where_clause=f"{oid_field} = {int(objectid)}",
    )
    n = int(arcpy.management.GetCount(out_fc)[0])
    fn(f"  Lectura 1 alerta (OID={objectid}): {n:,} registro(s)")
    if n == 0:
        raise RuntimeError(f"No se encontro OBJECTID={objectid} en {fc_alertas}")

    try:
        return _fc_a_geodataframe(out_fc, msg_fn=fn)
    finally:
        try:
            if arcpy.Exists(out_fc):
                arcpy.management.Delete(out_fc)
        except Exception:
            pass


def _aplicar_filtros_acr_periodo(alertas_gdf, fecha_ini, fecha_fin, msg_fn=None):
    import pandas as pd

    fn = msg_fn or arcpy.AddMessage
    alertas_gdf = normalize_oid_column(alertas_gdf)
    fn(f"  En memoria   : {len(alertas_gdf):,}  |  CRS: {alertas_gdf.crs}")

    alertas_gdf = alertas_gdf.copy()

    def _raw_anp_fila(row):
        rec = row.to_dict()
        return valor_anp_desde_registro(rec)

    alertas_gdf["_anp_norm"] = alertas_gdf.apply(
        lambda r: normalizar_anp_codi(_raw_anp_fila(r)), axis=1
    )
    df_acr = alertas_gdf[
        alertas_gdf["_anp_norm"].astype(str).str.strip().isin(ACR_CODIGOS_FC)
    ].copy()
    fn(f"  Solo ACRs    : {len(df_acr):,}")

    df_acr["_causa_int"] = df_acr.apply(
        lambda r: _parse_causa_int(r.to_dict()), axis=1
    )
    def _causa_ok(row):
        c = row.get("_causa_int")
        if c in CAUSAS_NO_ANTROPICAS:
            return False
        if pd.notna(c):
            return True
        try:
            return float(row.get("md_sup") or 0) > 0
        except (TypeError, ValueError):
            return False

    mask_antrop = df_acr.apply(_causa_ok, axis=1)
    df_antrop = df_acr[mask_antrop].copy()
    sin_causa = df_antrop["_causa_int"].isna()
    if sin_causa.any():
        df_antrop.loc[sin_causa, "_causa_int"] = 99
        df_antrop.loc[sin_causa, "causa_texto"] = "Sin clasificar (sin md_causa en GDB)"
        fn(f"  AVISO: {int(sin_causa.sum())} alerta(s) sin md_causa — incluidas como pendientes")
    fn(f"  Antropicas   : {len(df_antrop):,}")

    fi = pd.to_datetime(fecha_ini, dayfirst=True)
    ff = pd.to_datetime(fecha_fin, dayfirst=True)
    df_antrop["md_fecimg"] = pd.to_datetime(
        df_antrop["md_fecimg"], errors="coerce"
    ).dt.tz_localize(None)
    df_periodo = df_antrop[
        (df_antrop["md_fecimg"] >= fi) & (df_antrop["md_fecimg"] <= ff)
    ].copy()
    fn(f"  En periodo   : {len(df_periodo):,}")
    return df_periodo


def _leer_alertas_gdb_filtrado(gdb_path, fc_alertas, fecha_ini, fecha_fin, msg_fn=None):
    """
    Filtra con arcpy a GDB temporal y luego lee con GeoPandas.
    (in_memory/memory no es visible para pyogrio/fiona.)
    """
    import pandas as pd

    fn = msg_fn or arcpy.AddMessage
    fc_path = os.path.join(gdb_path, fc_alertas)
    if not arcpy.Exists(fc_path):
        raise RuntimeError(f"No existe la capa: {fc_path}")

    fi = pd.to_datetime(fecha_ini, dayfirst=True)
    ff = pd.to_datetime(fecha_fin, dayfirst=True)
    campo_fec = _sql_fecha_campo(fc_path)

    where_sql = None
    if campo_fec:
        f0 = fi.strftime("%Y-%m-%d")
        f1 = ff.strftime("%Y-%m-%d")
        where_sql = (
            f"(({campo_fec} >= timestamp '{f0} 00:00:00') AND "
            f"({campo_fec} <= timestamp '{f1} 23:59:59'))"
        )

    scratch = _scratch_gdb_temporal()
    out_name = "ATD_alertas_tmp"
    out_fc = os.path.join(scratch, out_name)
    if arcpy.Exists(out_fc):
        arcpy.management.Delete(out_fc)

    def _copiar(where):
        arcpy.conversion.FeatureClassToFeatureClass(
            in_features=fc_path,
            out_path=scratch,
            out_name=out_name,
            where_clause=where or None,
        )
        return int(arcpy.management.GetCount(out_fc)[0])

    try:
        n = _copiar(where_sql)
        fn(f"  Lectura arcpy (SQL): {n:,} registros")
    except Exception as ex:
        fn(f"  AVISO: filtro SQL no aplicado ({ex})")
        n = _copiar(None)
        fn(f"  Lectura arcpy (sin SQL fecha): {n:,} registros")

    if n == 0:
        fn("  AVISO: 0 registros tras filtro; leyendo capa completa...")
        if arcpy.Exists(out_fc):
            arcpy.management.Delete(out_fc)
        n = _copiar(None)
        fn(f"  Lectura arcpy (completa): {n:,} registros")

    try:
        gdf = _fc_a_geodataframe(out_fc, msg_fn=fn)
    finally:
        try:
            if arcpy.Exists(out_fc):
                arcpy.management.Delete(out_fc)
        except Exception:
            pass
    return gdf


def filtrar_alertas_periodo(gdb_path, fc_alertas, fecha_ini, fecha_fin, msg_fn=None):
    configurar_region(gdb_path)
    fn = msg_fn or arcpy.AddMessage

    alertas_gdf = _leer_alertas_gdb_filtrado(
        gdb_path, fc_alertas, fecha_ini, fecha_fin, msg_fn=fn
    )
    return _aplicar_filtros_acr_periodo(
        alertas_gdf, fecha_ini, fecha_fin, msg_fn=fn
    ), alertas_gdf


def enriquecer_alertas(df_periodo, modo_ligero=False):
    import pandas as pd
    import geopandas as gpd

    df = df_periodo.copy()
    if "_causa_int" not in df.columns:
        df["_causa_int"] = df.apply(
            lambda r: _parse_causa_int(r.to_dict()), axis=1
        )
    if "_anp_norm" in df.columns:
        df["anp_codi"] = df["_anp_norm"].astype(str).str.strip()
    else:
        df["anp_codi"] = df["anp_codi"].apply(normalizar_anp_codi).astype(str).str.strip()
    df["causa_texto"] = df["_causa_int"].apply(
        lambda v: DOMINIO_CAUSA.get(int(v), f"Codigo {v}")
        if pd.notna(v) else "Sin clasificar"
    )
    df["conf_texto"] = df["md_conf"].apply(
        lambda v: _etiqueta_confianza(v) if pd.notna(v) else "Sin clasificar"
    )
    df["bosque_texto"] = df["md_bosque"].apply(
        lambda v: DOMINIO_BOSQUE.get(int(v), "-") if pd.notna(v) else "-"
    )
    df["acr_nombre"] = df["anp_codi"].map(ACR_NOMBRES).fillna(df["anp_codi"])
    df["acr_sigla"] = df["anp_codi"].map(ACR_SIGLAS).fillna(df["anp_codi"])

    df["este_utm"] = pd.to_numeric(df.get("md_este"), errors="coerce")
    df["norte_utm"] = pd.to_numeric(df.get("md_norte"), errors="coerce")

    if modo_ligero:
        return df

    epsg_utm = _utm_epsg_region()
    try:
        df_utm = (
            df.to_crs(f"EPSG:{epsg_utm}")
            if df.crs and df.crs.to_epsg() != epsg_utm
            else df.copy()
        )
        cents = df_utm.geometry.centroid
        mask_xy = df["este_utm"].isna() | df["norte_utm"].isna()
        if mask_xy.any():
            df.loc[mask_xy, "este_utm"] = cents.x.round(1).values[mask_xy]
            df.loc[mask_xy, "norte_utm"] = cents.y.round(1).values[mask_xy]
    except Exception:
        pass

    for campo, calc in [("md_este", "este_utm"), ("md_norte", "norte_utm")]:
        if campo in df.columns:
            mask = df[campo].isna()
            df.loc[mask, campo] = df.loc[mask, calc]
    return df


def _first_existing_column(df, candidatos):
    lower = {str(c).lower(): c for c in df.columns}
    for cand in candidatos:
        if cand in df.columns:
            return cand
        if str(cand).lower() in lower:
            return lower[str(cand).lower()]
    return None


def _map_zi_codigo_a_acr(cod_raw):
    s = str(cod_raw).strip().upper()
    if s in ACR_NOMBRES:
        return s
    if s in ZI_CODI_TO_ACR:
        return ZI_CODI_TO_ACR[s]
    if s.startswith("ZI"):
        rest = s.replace("ZI", "").strip()
        if rest in ACR_NOMBRES:
            return rest
        if rest in ZI_CODI_TO_ACR:
            return ZI_CODI_TO_ACR[rest]
        if rest in SIGLA_TO_ACR:
            return SIGLA_TO_ACR[rest]
    return None


def cargar_acr_y_zi(gdb_path, fc_anp, msg_fn=None):
    import geopandas as gpd

    configurar_region(gdb_path)
    fn = msg_fn or arcpy.AddMessage
    raw = gpd.read_file(gdb_path, layer=fc_anp)
    campo_cod = _first_existing_column(
        raw, ["acr_codi", "anp_codi", "cod_acr", "codigo", "cod", "CODOBJ"]
    )
    campo_nom = _first_existing_column(
        raw, ["acr_nomb", "anp_nomb", "ANP_NOM", "nombre", "nomobj", "name"]
    )
    if not campo_cod and not campo_nom:
        raise RuntimeError(
            "No se encontro campo de codigo/nombre ACR en la capa seleccionada."
        )
    raw["_cod_raw"] = (
        raw[campo_cod].astype(str).str.strip() if campo_cod
        else raw[campo_nom].astype(str).str.strip()
    )
    raw["_nomb_clean"] = (
        raw[campo_nom].astype(str).str.strip() if campo_nom
        else raw["_cod_raw"]
    )

    is_zi = raw["_cod_raw"].str.upper().str.match(r"^ZI(\s|$)", na=False)
    acr_part = raw[~is_zi].copy()
    acr_part["_cod_clean"] = acr_part["_cod_raw"].apply(
        lambda v: v if str(v).strip() in ACR_NOMBRES else None
    )
    falta_cod = acr_part["_cod_clean"].isna()
    acr_part.loc[falta_cod, "_cod_clean"] = (
        acr_part.loc[falta_cod, "_nomb_clean"].map(ACR_NOMB_TO_CODI)
    )
    acr_gdf = acr_part[acr_part["_cod_clean"].notna()].copy()

    zi_part = raw[is_zi].copy()
    zi_part["_zi_acr"] = zi_part["_cod_raw"].apply(_map_zi_codigo_a_acr)
    zi_gdf = zi_part[zi_part["_zi_acr"].notna()].copy()

    fn(
        f"  ACR: {list(zip(acr_gdf['_cod_clean'].tolist(), acr_gdf['_nomb_clean'].tolist()))}"
    )
    if len(zi_gdf):
        fn(
            f"  ZI : {list(zip(zi_gdf['_zi_acr'].tolist(), zi_gdf['_cod_raw'].tolist()))}"
        )
    return acr_gdf, zi_gdf


def cargar_acr_poligonos(gdb_path, fc_anp, msg_fn=None):
    acr_gdf, _ = cargar_acr_y_zi(gdb_path, fc_anp, msg_fn)
    return acr_gdf


def _etiqueta_alerta(row):
    import pandas as pd
    oid = row.get("objectid", "?")
    cod = str(row.get("anp_codi", "")).strip()
    causa = row.get("causa_texto", row.get("_causa_int", "?"))
    sup = float(row.get("md_sup", 0) or 0)
    fec = row.get("md_fecimg", None)
    fec_s = pd.to_datetime(fec).strftime("%d/%m/%Y") if pd.notna(fec) else "sin fecha"
    nom = str(row.get("acr_nombre", cod))
    if len(nom) > 36:
        nom = nom[:33] + "..."
    return (
        f"OID:{oid}|{nom} — {causa} — {sup:.2f} ha — imagen {fec_s} "
        f"(ref. {cod})"
    )


def _filtrar_df_por_etiqueta(df, texto):
    import pandas as pd

    matched = filtrar_registros_por_etiqueta(df.to_dict("records"), texto)
    if not matched:
        return df.iloc[0:0].copy()
    oids = {m.get("objectid") for m in matched}
    if "objectid" in df.columns:
        return df[df["objectid"].isin(oids)].copy()
    return df.iloc[0:0].copy()


def listar_opciones_alertas(gdb_path, fc_alertas, fecha_ini, fecha_fin, acr_filtro=""):
    key = f"{gdb_path}|{fc_alertas}|{fecha_ini}|{fecha_fin}|{acr_filtro}"
    now = time.time()
    if _CACHE_ALERTAS["key"] == key and (now - _CACHE_ALERTAS["ts"]) < 30:
        return _CACHE_ALERTAS["opciones"], _CACHE_ALERTAS["df"]

    opts, registros = listar_opciones_alertas_arcpy(
        gdb_path, fc_alertas, fecha_ini, fecha_fin, acr_filtro
    )
    _CACHE_ALERTAS.update({"key": key, "opciones": opts, "df": registros, "ts": now})
    return opts, registros


def urls_vista_comparativa(este_utm, norte_utm, fecha_antes=None, fecha_despues=None,
                           img_id_a=None, img_id_b=None, epsg_utm=None):
    import pandas as pd
    import pyproj as _pyproj
    epsg_utm = epsg_utm or _utm_epsg_region()
    try:
        tr = _pyproj.Transformer.from_crs(
            f"EPSG:{epsg_utm}", "EPSG:4326", always_xy=True)
        lon, lat = tr.transform(float(este_utm), float(norte_utm))
    except Exception:
        return (
            "https://apps.sentinel-hub.com/eo-browser/",
            "https://earth.google.com/web/",
            "",
        )
    zoom = 15
    fa = pd.to_datetime(fecha_antes).strftime("%Y-%m-%d") if fecha_antes else ""
    fb = pd.to_datetime(fecha_despues).strftime("%Y-%m-%d") if fecha_despues else ""
    eo_url = (
        f"https://apps.sentinel-hub.com/eo-browser/"
        f"?lat={lat:.6f}&lng={lon:.6f}&zoom={zoom}&theme=dark"
    )
    if fa and fb:
        eo_url += f"&time={fa}/{fb}&layer=s2cloudless-2020"
    gee_url = (
        f"https://earth.google.com/web/@{lat:.6f},{lon:.6f},1200a,500d,35y,0h,0t,0r"
    )
    notas = (
        f"Centro alerta: {lat:.5f}, {lon:.5f} | "
        f"Antes {fecha_antes or '-'} / Después {fecha_despues or '-'}"
    )
    return eo_url, gee_url, notas


def _html_escape(t):
    return (str(t or "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _estilo_html_gfp():
    return """
    body{font-family:'Segoe UI',Arial,sans-serif;margin:24px 32px;color:#1A2B3C;
         line-height:1.45;background:#fff;}
    h1{color:#2F5F8F;font-size:1.35em;border-bottom:3px solid #C41E3A;padding-bottom:8px;}
    h2{color:#2F5F8F;font-size:1.05em;margin-top:1.2em;}
    ol,ul{margin:0.4em 0 0.8em 1.2em;}
    li{margin:0.25em 0;}
    .tag{display:inline-block;background:#E8EEF4;color:#2F5F8F;padding:2px 8px;
         border-radius:4px;font-size:0.85em;margin-bottom:12px;}
    .btn{display:inline-block;margin:8px 12px 8px 0;padding:10px 18px;background:#2F5F8F;
         color:#fff;text-decoration:none;border-radius:6px;font-weight:600;}
    .btn:hover{background:#3A7CA5;}
    .btn.red{background:#C41E3A;}
    .note{background:#F4F6F8;border-left:4px solid #2F5F8F;padding:10px 14px;margin:12px 0;}
    """


def generar_html_metodologia(ruta_html, region_nombre="Loreto"):
    cuerpo = f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"/>
<title>Metodología ATD — GFP Subnacional</title><style>{_estilo_html_gfp()}</style></head>
<body>
<span class="tag">GFP Subnacional · { _html_escape(region_nombre) }</span>
<h1>Metodología — Línea base de deforestación y alertas tempranas</h1>

<h2>1. Marco normativo y conceptual</h2>
<p>Según el <strong>Decreto Supremo N.º 006-2008-MINAM</strong>, se establece el procedimiento
para la aprobación de Áreas de Conservación Regional (ACR). El análisis de línea base de
deforestación es un requisito fundamental para evaluar la efectividad de las medidas de
conservación y planificar la gestión territorial sostenible.</p>
<p>Las ACR son espacios naturales bajo gestión regional que conservan la diversidad biológica,
los servicios ecosistémicos y los valores culturales, integrando a las comunidades locales.</p>

<h2>2. Fuentes de información y datos</h2>
<ul>
<li><strong>Fuente primaria:</strong> Plataforma GeoBosques (MINAM).</li>
<li><strong>Período:</strong> 2001–2024 (serie histórica).</li>
<li><strong>Resolución:</strong> 30 m (Landsat 7/8).</li>
<li><strong>Actualización:</strong> anual, con alertas trimestrales.</li>
<li><strong>Cobertura:</strong> ACR en Loreto, San Martín y Cusco.</li>
</ul>
<p>Detección multitemporal con algoritmos de cambio espectral (estándares Hansen et al., 2013).</p>

<h2>3. Procesamiento y análisis</h2>
<ol>
<li>Descarga de polígonos GeoBosques (shapefile por año).</li>
<li>Normalización a WGS84 (EPSG:4326) y simplificación geométrica.</li>
<li>Intersección con ACR y zona de influencia (buffer 5 km).</li>
<li>Clasificación: antrópico, natural, falsa alerta.</li>
<li>Cálculo de hectáreas por categoría, año y ACR.</li>
</ol>

<h2>4. Zona de influencia</h2>
<p>Buffer de <strong>5 km</strong> alrededor de cada ACR para analizar presión antrópica adyacente,
identificar frentes de deforestación y evaluar la ACR como barrera frente a la pérdida de bosque.</p>

<h2>5. Análisis de tendencias</h2>
<p>Regresión lineal 2001–2024: tasa anual (ha/año), proyección 2025–2029 y R².
Limitaciones: no incluye políticas futuras ni eventos extraordinarios.</p>

<h2>6. Gestión de datos</h2>
<p>Geometrías en RDS simplificadas; estadísticas precomputadas; visualización Plotly/Leaflet.</p>

<h2>7. Control de calidad</h2>
<ul>
<li>Comparación con reportes MINAM y estudios académicos.</li>
<li>Verificación visual en Google Earth y Planet.</li>
<li>Consulta con Gerencias Regionales de Recursos Naturales.</li>
</ul>

<h2>8. Referencias</h2>
<ul>
<li>Hansen, M. C., et al. (2013). Science, 342(6160), 850-853.</li>
<li>MINAM (2024). Metodología monitoreo pérdida de bosque amazónico.</li>
<li>DS N.º 006-2008-MINAM — SERNANP.</li>
<li>Global Forest Watch (2024).</li>
</ul>
</body></html>"""
    with open(ruta_html, "w", encoding="utf-8") as f:
        f.write(cuerpo)


def generar_html_procedimiento(ruta_html, region_nombre="Loreto"):
    cuerpo = f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"/>
<title>Procedimiento fotointerpretación ATD</title><style>{_estilo_html_gfp()}</style></head>
<body>
<span class="tag">GFP Subnacional · { _html_escape(region_nombre) }</span>
<h1>Procedimiento — Fotointerpretación de alertas tempranas</h1>
<div class="note">Mini manual operativo para validar alertas en campo y oficina.</div>

<h2>1. Preparación</h2>
<ol>
<li>Abrir el reporte PDF y, si existen, las imagenes exportadas desde H2.</li>
<li>En el enlace <strong>Visualizacion</strong> del PDF, abrir el
<a href="https://acr-dashboard-5iqz.onrender.com/">Dashboard ACR</a> de monitoreo de deforestacion.</li>
<li>Contrastar con el mapa de ubicación (ACR, zona de influencia y punto de alerta).</li>
</ol>

<h2>2. Criterios de interpretación</h2>
<ul>
<li><strong>Antrópico:</strong> agricultura, ganadería, minería, infraestructura, ocupación humana.</li>
<li><strong>Natural:</strong> inundación, deslizamiento, muerte natural de árboles.</li>
<li><strong>Falsa alerta:</strong> nubes, sombras, cambios espectrales temporales.</li>
</ul>

<h2>3. Pasos de validación</h2>
<ol>
<li>Confirmar que el polígono coincide con pérdida de cobertura forestal visible.</li>
<li>Estimar superficie afectada y comparar con el valor del sistema (ha).</li>
<li>Asignar causa dominante según dominio GeoBosques / GDB.</li>
<li>Registrar nivel de confiabilidad (alta / media / baja).</li>
<li>Documentar observaciones para seguimiento en campo si aplica.</li>
</ol>

<h2>4. Uso de imágenes Sentinel-2</h2>
<ul>
<li>Combinación color natural (B04, B03, B02) para lectura visual.</li>
<li>Comparar fechas de escena antes y después del evento reportado.</li>
<li>Usar swipe en EO Browser para deslizar entre fechas.</li>
</ul>

<h2>5. Entregables</h2>
<p>Reporte PDF firmado, capas en GDB actualizadas y registro en monitoreo acumulado.</p>
</body></html>"""
    with open(ruta_html, "w", encoding="utf-8") as f:
        f.write(cuerpo)


def generar_html_visualizacion(ruta_html, url_eo, url_gee, fecha_antes, fecha_despues,
                               lat, lon, cod_reporte=""):
    cuerpo = f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"/>
<title>Vista dinámica ATD — comparación</title><style>{_estilo_html_gfp()}
iframe{{width:100%;height:480px;border:2px solid #B8C8D8;border-radius:8px;margin-top:12px;}}
</style></head>
<body>
<span class="tag">Alerta { _html_escape(cod_reporte) }</span>
<h1>Vista dinámica — Antes y después (swipe)</h1>
<p><strong>Antes:</strong> { _html_escape(fecha_antes) } &nbsp;|&nbsp;
<strong>Después:</strong> { _html_escape(fecha_despues) }</p>
<p>Coordenadas: {lat:.6f}, {lon:.6f}</p>

<a class="btn" href="{_html_escape(url_eo)}" target="_blank" rel="noopener">
Abrir EO Browser (Swipe Sentinel-2)</a>
<a class="btn red" href="{_html_escape(url_gee)}" target="_blank" rel="noopener">
Abrir Google Earth (vista 3D)</a>

<div class="note">
En EO Browser: active la herramienta <strong>Compare / Swipe</strong>, seleccione
Sentinel-2 L2A y deslice entre las fechas indicadas arriba.
</div>

<iframe src="{_html_escape(url_eo)}" title="EO Browser"></iframe>
</body></html>"""
    with open(ruta_html, "w", encoding="utf-8") as f:
        f.write(cuerpo)


def _uri_archivo_local(ruta):
    try:
        from pathlib import Path
        return Path(ruta).resolve().as_uri()
    except Exception:
        r = os.path.abspath(ruta).replace("\\", "/")
        return f"file:///{r}" if not r.startswith("file:") else r


def preparar_documentacion_html(dir_docs, region_nombre):
    """Genera HTML locales y devuelve URIs file:// para el PDF."""
    os.makedirs(dir_docs, exist_ok=True)
    p_met = os.path.join(dir_docs, "ATD_metodologia.html")
    p_proc = os.path.join(dir_docs, "ATD_procedimiento_fotointerpretacion.html")
    generar_html_metodologia(p_met, region_nombre)
    generar_html_procedimiento(p_proc, region_nombre)
    return _uri_archivo_local(p_met), _uri_archivo_local(p_proc)


def link_visualizacion_alerta(dir_docs, oid, url_eo, url_gee, fecha_a, fecha_d,
                             lat, lon, cod_reporte,
                             ruta_img_a=None, ruta_img_d=None,
                             sat_a="Imagen satelital", sat_d="Imagen satelital"):
    os.makedirs(dir_docs, exist_ok=True)
    p_vis = os.path.join(dir_docs, f"ATD_swipe_OID{oid}.html")
    try:
        from atd_swipe_viewer import generar_html_swipe_local, puede_generar_swipe
        if puede_generar_swipe(ruta_img_a, ruta_img_d):
            generar_html_swipe_local(
                p_vis, ruta_img_a, ruta_img_d,
                fecha_antes=fecha_a, fecha_despues=fecha_d,
                sat_antes=sat_a, sat_despues=sat_d,
                cod_reporte=cod_reporte, oid=oid,
                url_eo_fallback=url_eo,
            )
            try:
                arcpy.AddMessage(
                    f"  Swipe local (imagenes H2): {os.path.basename(p_vis)}"
                )
            except Exception:
                pass
        else:
            p_vis = os.path.join(dir_docs, f"ATD_visualizacion_OID{oid}.html")
            generar_html_visualizacion(
                p_vis, url_eo, url_gee, fecha_a, fecha_d, lat, lon, cod_reporte)
    except Exception:
        p_vis = os.path.join(dir_docs, f"ATD_visualizacion_OID{oid}.html")
        generar_html_visualizacion(
            p_vis, url_eo, url_gee, fecha_a, fecha_d, lat, lon, cod_reporte)
    return _uri_archivo_local(p_vis)


def run_diagnostico_pre_vuelo(gdb_path, fc_alertas, fecha_ini, fecha_fin):
    from atd_ejecutar_estable import run_diagnostico_arcpy
    run_diagnostico_arcpy(gdb_path, fc_alertas, fecha_ini, fecha_fin, DEFAULT_SALIDA)


def _leer_periodo_guardado(base_salida=None):
    import json
    base = base_salida or DEFAULT_SALIDA
    path = os.path.join(base, "periodo_reporte_atd.json")
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            return d.get("fecha_ini"), d.get("fecha_fin")
        except Exception:
            pass
    return None, None


def _update_fc_params(parameters, gdb_idx, fc_indices):
    gdb = parameters[gdb_idx].valueAsText
    if gdb:
        fcs = list_fc_in_gdb(gdb)
        if fcs:
            for i in fc_indices:
                parameters[i].filter.list = fcs


# ═══════════════════════════════════════════════════════════════════
# TOOLBOX
# ═══════════════════════════════════════════════════════════════════
class Toolbox(object):
    def __init__(self):
        self.label = (
            "Geo Presentación 3 — Elaboración de reportes "
            "de deforestación en ACR"
        )
        self.alias = "ReporteATD_v7"
        self.description = (
            "Reportes PDF ATD Loreto / Cuzco / San Martin. "
            "Diagnostico, mapa ESRI, Sentinel-2 GEE, layout oficial."
        )
        self.tools = [DiagnosticoPreVuelo, GenerarReporteATD]


# ═══════════════════════════════════════════════════════════════════
# HERRAMIENTA 1 - DIAGNOSTICO PRE-VUELO
# ═══════════════════════════════════════════════════════════════════
class DiagnosticoPreVuelo(object):

    def __init__(self):
        self.label = "1. Diagnostico Pre-Vuelo"
        self.description = (
            "Resume alertas ACR antropicas en el periodo (Celda 1.5 del notebook)."
        )
        self.canRunInBackground = False

    def getParameterInfo(self):
        p0 = arcpy.Parameter(
            displayName="GDB Linea Base Deforestacion",
            name="gdb_path",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Input",
        )
        p0.filter.list = ["Local Database"]
        _gdb_def = _gdb_absoluta_si_existe(DEFAULT_GDB)
        if _gdb_def:
            p0.value = _gdb_def

        p1 = arcpy.Parameter(
            displayName="Feature Class de Alertas",
            name="fc_alertas",
            datatype="GPString",
            parameterType="Required",
            direction="Input",
        )
        p1.filter.type = "ValueList"
        p1.filter.list = ["MonitoreoDeforestacion"]
        p1.value = "MonitoreoDeforestacion"

        _hoy = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        p2 = arcpy.Parameter(
            displayName="Fecha inicio del periodo monitoreado",
            name="fecha_ini",
            datatype="GPDate",
            parameterType="Required",
            direction="Input",
        )
        p2.value = datetime(_hoy.year, 1, 1)

        p3 = arcpy.Parameter(
            displayName="Fecha fin del periodo monitoreado",
            name="fecha_fin",
            datatype="GPDate",
            parameterType="Required",
            direction="Input",
        )
        p3.value = _hoy

        return [p0, p1, p2, p3]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        try:
            _hoy = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            if not parameters[2].altered:
                _set_param_si_cambia(parameters[2], datetime(_hoy.year, 1, 1))
            if not parameters[3].altered:
                _set_param_si_cambia(parameters[3], _hoy)

            gdb_abs = _gdb_absoluta_si_existe(parameters[0].valueAsText)
            if gdb_abs:
                _set_param_si_cambia(parameters[0], gdb_abs)
                _aplicar_region_desde_gdb(gdb_abs)
                fcs = list_fc_in_gdb(gdb_abs)
                if fcs:
                    parameters[1].filter.list = fcs
                    cur_fc = parameters[1].valueAsText or ""
                    if cur_fc not in fcs:
                        _set_param_si_cambia(
                            parameters[1], resolver_fc_alertas(gdb_abs, fcs)
                        )
        except Exception:
            pass

    def updateMessages(self, parameters):
        try:
            gdb = _gdb_absoluta_si_existe(parameters[0].valueAsText)
            if not gdb:
                parameters[0].setErrorMessage(
                    "Seleccione la GDB de linea base (.gdb) con ruta valida."
                )
            else:
                parameters[0].clearMessage()
        except Exception:
            pass

    def execute(self, parameters, messages):
        try:
            ok, falta = verify_libraries(
                check_gee=False,
                check_contextily=False,
                omit_modulos=["geopandas", "fiona", "numpy", "matplotlib", "requests"],
                msg_fn=arcpy.AddMessage,
            )
            if not ok:
                arcpy.AddError(
                    "Librerias no disponibles en el Python de ArcGIS Pro.\n"
                    f"  Ruta: {sys.executable}\n"
                    "  Abre: Inicio > ArcGIS > Python Command Prompt\n"
                    "  Luego ejecuta:\n"
                    f"    python -m pip install {' '.join(falta)}"
                )
                return
            # GPDate devuelve datetime objects, convertir a dd/mm/yyyy
            fecha_ini_val = parameters[2].value
            fecha_fin_val = parameters[3].value
            _hoy = datetime.now()
            fecha_ini = (
                fecha_ini_val.strftime("%d/%m/%Y")
                if fecha_ini_val
                else f"01/01/{_hoy.year}"
            )
            fecha_fin = (
                fecha_fin_val.strftime("%d/%m/%Y")
                if fecha_fin_val
                else _hoy.strftime("%d/%m/%Y")
            )
            run_diagnostico_pre_vuelo(
                parameters[0].valueAsText,
                parameters[1].valueAsText,
                fecha_ini,
                fecha_fin,
            )
        except Exception as e:
            arcpy.AddError(str(e))
            arcpy.AddError(traceback.format_exc())


# ═══════════════════════════════════════════════════════════════════
# HERRAMIENTA PRINCIPAL
# ═══════════════════════════════════════════════════════════════════
class GenerarReporteATD(object):

    def __init__(self):
        self.label = "2. Elaboración de reportes de deforestación en ACR"
        self.description = (
            "Genera el PDF oficial por alerta (mapa ESRI, Sentinel-2 opcional, tablas). "
            "Seleccione la GDB (Loreto / Cuzco / San Martin): ACRs y capas se cargan solas. "
            "PASO PREVIO: '1. Diagnostico Pre-Vuelo'. Use H2 (Planet) para imagenes_sentinel/."
        )
        # Segundo plano desactivado: en algunos equipos cierra Pro al mezclar arcpy + matplotlib
        self.canRunInBackground = False

    _IX = {
        "gdb": 0, "fc_alertas": 1, "fc_anp": 2,
        "fecha_ini": 3, "fecha_fin": 4,
        "base_salida": 5, "dir_logos": 6,
        "acr_filtro": 7, "alerta_sel": 8,
        "gee_project": 9,
        "fc_zonif": 10,
        "descargar_gee": 11, "gee_dias": 12, "gee_nubes": 13,
        "responsable": 14, "cargo": 15,
        "modo_estable": 16,
    }
    _HIDDEN = (
        "fecha_ini", "fecha_fin", "fc_zonif", "descargar_gee",
        "gee_dias", "gee_nubes",
    )
    _CAT_DATOS = "1. Datos de la linea base"
    _CAT_SALIDA = "2. Donde se guarda el PDF"
    _CAT_AUTOR = "3. Quien elabora el reporte"
    _CAT_GEE = "4. Imagenes satelitales (avanzado)"
    _CAT_PROC = "5. Que alerta incluir en el PDF"

    def getParameterInfo(self):
        C = self._CAT_DATOS
        p0 = arcpy.Parameter(
            displayName="GDB Linea Base Deforestacion",
            name="gdb_path",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Input",
            category=C,
        )
        p0.filter.list = ["Local Database"]
        _gdb_def = _gdb_absoluta_si_existe(DEFAULT_GDB)
        if _gdb_def:
            p0.value = _gdb_def

        p1 = arcpy.Parameter(
            displayName="Capa de alertas",
            name="fc_alertas",
            datatype="GPString",
            parameterType="Required",
            direction="Input",
            category=C,
        )
        p1.filter.type = "ValueList"
        p1.filter.list = ["MonitoreoDeforestacion"]
        p1.value = "MonitoreoDeforestacion"

        p2 = arcpy.Parameter(
            displayName="Capa ACR (gpo_anp_monit)",
            name="fc_anp",
            datatype="GPString",
            parameterType="Required",
            direction="Input",
            category=C,
        )
        p2.filter.type = "ValueList"
        p2.filter.list = ["gpo_anp_monit"]
        p2.value = "gpo_anp_monit"

        p3 = arcpy.Parameter(
            displayName="Periodo inicio (automatico tras Diagnostico)",
            name="fecha_ini",
            datatype="GPString",
            parameterType="Required",
            direction="Input",
            category=C,
        )
        p3.value = INTERNAL_FECHA_INI

        p4 = arcpy.Parameter(
            displayName="Periodo fin (automatico tras Diagnostico)",
            name="fecha_fin",
            datatype="GPString",
            parameterType="Required",
            direction="Input",
            category=C,
        )
        p4.value = INTERNAL_FECHA_FIN

        C = self._CAT_SALIDA
        p5 = arcpy.Parameter(
            displayName="Carpeta base de salida",
            name="base_salida",
            datatype="DEFolder",
            parameterType="Required",
            direction="Input",
            category=C,
        )
        p5.value = _ruta_absoluta(DEFAULT_SALIDA)

        p6 = arcpy.Parameter(
            displayName="Carpeta de logos (PNG)",
            name="dir_logos",
            datatype="DEFolder",
            parameterType="Optional",
            direction="Input",
            category=C,
        )
        p6.value = _ruta_absoluta(os.path.join(DEFAULT_SALIDA, "logos"))

        C = self._CAT_AUTOR
        p14 = arcpy.Parameter(
            displayName="Nombre del responsable (ej.: Juan Pérez)",
            name="responsable",
            datatype="GPString",
            parameterType="Required",
            direction="Input",
            category=C,
        )

        p15 = arcpy.Parameter(
            displayName="Cargo o funcion (ej.: Especialista SIG)",
            name="cargo",
            datatype="GPString",
            parameterType="Required",
            direction="Input",
            category=C,
        )

        C = self._CAT_PROC
        p7 = arcpy.Parameter(
            displayName="Area de conservacion (filtro opcional)",
            name="acr_filtro",
            datatype="GPString",
            parameterType="Optional",
            direction="Input",
            category=C,
        )
        p7.filter.type = "ValueList"
        p7.filter.list = acr_opciones_filtro()
        p7.value = "TODAS"

        p8 = arcpy.Parameter(
            displayName="Alerta para el reporte PDF",
            name="alerta_sel",
            datatype="GPString",
            parameterType="Required",
            direction="Input",
            category=C,
        )
        p8.filter.type = "ValueList"
        p8.filter.list = [
            "[Paso 1] Ejecute Diagnostico Pre-Vuelo para cargar alertas"
        ]
        p8.value = p8.filter.list[0]

        C = self._CAT_GEE
        p9 = arcpy.Parameter(
            displayName="Proyecto Google Earth Engine (ej.: ee-favio)",
            name="gee_project",
            datatype="GPString",
            parameterType="Optional",
            direction="Input",
            category=C,
        )

        p10 = arcpy.Parameter(
            displayName="Capa zonificacion (interno)",
            name="fc_zonif",
            datatype="GPString",
            parameterType="Required",
            direction="Input",
            category=C,
        )
        p10.filter.type = "ValueList"
        p10.value = "gpo_zonif_anp"

        p11 = arcpy.Parameter(
            displayName="Descargar Sentinel-2 GEE (interno)",
            name="descargar_gee",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input",
            category=C,
        )
        p11.value = False

        p12 = arcpy.Parameter(
            displayName="Dias busqueda S2 (interno)",
            name="gee_dias",
            datatype="GPLong",
            parameterType="Optional",
            direction="Input",
            category=C,
        )
        p12.value = GEE_DIAS_DEFAULT

        p13 = arcpy.Parameter(
            displayName="Nubes max S2 (interno)",
            name="gee_nubes",
            datatype="GPLong",
            parameterType="Optional",
            direction="Input",
            category=C,
        )
        p13.value = GEE_NUBES_DEFAULT

        p16 = arcpy.Parameter(
            displayName="Modo estable (sin mapa/GEE; si Pro se cierra)",
            name="modo_estable",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input",
            category=self._CAT_GEE,
        )
        p16.value = False

        return [p0, p1, p2, p3, p4, p5, p6, p7, p8, p9, p10, p11, p12, p13, p14, p15, p16]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        ix = self._IX
        try:
            self._update_parameters_impl(parameters, ix)
        except Exception:
            pass

    def _update_parameters_impl(self, parameters, ix):
        for key in self._HIDDEN:
            parameters[ix[key]].enabled = False

        gdb_abs = _gdb_absoluta_si_existe(parameters[ix["gdb"]].valueAsText)
        if gdb_abs:
            _set_param_si_cambia(parameters[ix["gdb"]], gdb_abs)
        gdb = parameters[ix["gdb"]].valueAsText or gdb_abs

        base_raw = parameters[ix["base_salida"]].valueAsText
        if base_raw:
            base_abs = _ruta_absoluta(base_raw)
            if os.path.isdir(base_abs):
                parameters[ix["base_salida"]].value = base_abs

        logos_raw = parameters[ix["dir_logos"]].valueAsText
        if logos_raw:
            logos_abs = _ruta_absoluta(logos_raw)
            if os.path.isdir(logos_abs):
                parameters[ix["dir_logos"]].value = logos_abs

        gdb_abs = _aplicar_region_desde_gdb(gdb)
        acr_opts = acr_opciones_filtro()
        parameters[ix["acr_filtro"]].filter.list = acr_opts
        if parameters[ix["acr_filtro"]].valueAsText not in acr_opts:
            parameters[ix["acr_filtro"]].value = "TODAS"
        if gdb_abs:
            _rellenar_params_fc_gdb(parameters, ix, gdb_abs)

        base_tmp = parameters[ix["base_salida"]].valueAsText or DEFAULT_SALIDA
        fi_g, ff_g = _leer_periodo_guardado(base_tmp)
        fi = fi_g or parameters[ix["fecha_ini"]].valueAsText or INTERNAL_FECHA_INI
        ff = ff_g or parameters[ix["fecha_fin"]].valueAsText or INTERNAL_FECHA_FIN
        if fi_g and ff_g:
            parameters[ix["fecha_ini"]].value = fi_g
            parameters[ix["fecha_fin"]].value = ff_g
        acr_f = parameters[ix["acr_filtro"]].valueAsText or "TODAS"
        if acr_f.upper() in ("TODAS", "TODOS", "TODA", "ALL"):
            acr_f = ""

        if not parameters[ix["acr_filtro"]].valueAsText:
            parameters[ix["acr_filtro"]].value = "TODAS"

        if gdb and parameters[ix["fc_alertas"]].valueAsText:
            try:
                opts, _ = listar_opciones_alertas(
                    gdb,
                    parameters[ix["fc_alertas"]].valueAsText,
                    fi,
                    ff,
                    acr_f,
                )
                if opts:
                    parameters[ix["alerta_sel"]].filter.list = opts
                    cur = parameters[ix["alerta_sel"]].valueAsText or ""
                    if cur not in opts:
                        parameters[ix["alerta_sel"]].value = opts[0]
            except Exception:
                fallback = [
                    "[Paso 1] Ejecute Diagnostico Pre-Vuelo para cargar alertas"
                ]
                parameters[ix["alerta_sel"]].filter.list = fallback
                parameters[ix["alerta_sel"]].value = fallback[0]

    def updateMessages(self, parameters):
        """ArcGIS no permite asignar .description en tiempo de ejecucion."""
        ix = self._IX
        for p in parameters:
            try:
                p.clearMessage()
            except Exception:
                pass
        alerta = parameters[ix["alerta_sel"]].valueAsText or ""
        if alerta.startswith("[Paso 1]") or alerta.startswith("[SIN"):
            try:
                parameters[ix["alerta_sel"]].setErrorMessage(
                    "Primero ejecute la herramienta "
                    "'1. Diagnostico Pre-Vuelo' (mismas GDB y fechas)."
                )
            except Exception:
                pass
        gdb = parameters[ix["gdb"]].valueAsText
        if _gdb_absoluta_si_existe(gdb):
            try:
                rk = _detectar_region(gdb)
                reg = REGION_CONFIGS.get(rk, {})
                n_acr = len(acr_opciones_filtro()) - 1
                parameters[ix["gdb"]].setMessage(
                    f"Region: {reg.get('region', rk)} | "
                    f"{n_acr} ACR(s) | FCs segun GDB seleccionada"
                )
            except Exception:
                pass

    # ── Ejecución principal ───────────────────────────────────────
    def execute(self, parameters, messages):

        ix = GenerarReporteATD._IX
        GDB_PATH = parameters[ix["gdb"]].valueAsText
        _aplicar_region_desde_gdb(GDB_PATH, globals(), force=True)
        FC_ALERTAS = parameters[ix["fc_alertas"]].valueAsText
        FC_ANP = parameters[ix["fc_anp"]].valueAsText
        FC_ZONIF = parameters[ix["fc_zonif"]].valueAsText
        FECHA_INI_REPORTE = parameters[ix["fecha_ini"]].valueAsText
        FECHA_FIN_REPORTE = parameters[ix["fecha_fin"]].valueAsText
        BASE_SALIDA = parameters[ix["base_salida"]].valueAsText
        DIR_LOGOS = parameters[ix["dir_logos"]].valueAsText or os.path.join(
            BASE_SALIDA, "logos"
        )
        fi_g, ff_g = _leer_periodo_guardado(BASE_SALIDA)
        FECHA_INI_REPORTE = fi_g or parameters[ix["fecha_ini"]].valueAsText or INTERNAL_FECHA_INI
        FECHA_FIN_REPORTE = ff_g or parameters[ix["fecha_fin"]].valueAsText or INTERNAL_FECHA_FIN
        if fi_g and ff_g:
            arcpy.AddMessage(
                f"  Periodo desde Diagnostico Pre-Vuelo: {FECHA_INI_REPORTE} - {FECHA_FIN_REPORTE}"
            )
        ALERTA_SEL = parameters[ix["alerta_sel"]].valueAsText or ""
        MODO_ESTABLE = bool(
            parameters[ix["modo_estable"]].value
            if parameters[ix["modo_estable"]].value is not None
            else False
        )
        DESCARGAR_GEE = bool(
            parameters[ix["descargar_gee"]].value
            if parameters[ix["descargar_gee"]].value is not None
            else False
        )
        # GEE dentro del flujo H3 suele ser inestable en ArcGIS Pro (crash sin traceback).
        # Por defecto se prioriza H2->imagenes_sentinel y se desactiva GEE en H3.
        GEE_EN_H3_HABILITADO = os.environ.get("ATD_H3_ENABLE_GEE", "0").strip() in (
            "1", "true", "True", "yes",
        )
        if DESCARGAR_GEE and not GEE_EN_H3_HABILITADO:
            arcpy.AddWarning(
                "  GEE en H3 desactivado por estabilidad. "
                "Use H2 para guardar imagenes en 'imagenes_sentinel'. "
                "Si desea forzar GEE en H3: variable ATD_H3_ENABLE_GEE=1."
            )
            DESCARGAR_GEE = False
        if MODO_ESTABLE:
            DESCARGAR_GEE = False
        OMITIR_GEE = not DESCARGAR_GEE
        GEE_PROJECT = (parameters[ix["gee_project"]].valueAsText or "").strip() or GEE_PROJECT_EJEMPLO
        GEE_DIAS_BUSQUEDA = int(parameters[ix["gee_dias"]].value or GEE_DIAS_DEFAULT)
        GEE_MAX_NUBES = int(parameters[ix["gee_nubes"]].value or GEE_NUBES_DEFAULT)
        ACR_FILTRO = (parameters[ix["acr_filtro"]].valueAsText or "TODAS").strip()
        if ACR_FILTRO.upper() in ("TODAS", "TODOS", "TODA", "ALL", "#"):
            ACR_FILTRO = ""
        RESPONSABLE_NOMBRE = (parameters[ix["responsable"]].valueAsText or "").strip() or "-"
        RESPONSABLE_CARGO = (parameters[ix["cargo"]].valueAsText or "").strip() or "-"

        ANNO_REPORTE = int(FECHA_FIN_REPORTE.split("/")[-1])
        DIR_DOCS = os.path.join(BASE_SALIDA, "documentacion_atd")
        LINK_METODOLOGIA, LINK_PROCEDIMIENTO = preparar_documentacion_html(
            DIR_DOCS, REGION_NOMBRE)
        arcpy.AddMessage(f"  Documentacion HTML: {DIR_DOCS}")

        DIR_IMAGENES = os.path.join(BASE_SALIDA, "imagenes_sentinel")
        DIR_MAPAS = os.path.join(BASE_SALIDA, "mapas")
        DIR_PDFS = os.path.join(BASE_SALIDA, "pdfs")
        for d in [DIR_IMAGENES, DIR_MAPAS, DIR_PDFS, DIR_LOGOS, DIR_DOCS]:
            os.makedirs(d, exist_ok=True)

        try:
            from atd_logos import (
                _archivos_en_carpeta,
                listar_logos_faltantes,
                resolve_logo_path,
            )
            _rk_logos = _REGION_ACTIVA or LOGO_REGION_KEY or "loreto"
            _logo_idx = _archivos_en_carpeta(DIR_LOGOS)
            arcpy.AddMessage(
                f"  Logos: {len(_logo_idx)} archivo(s) | region={_rk_logos}"
            )
            _g = resolve_logo_path(
                DIR_LOGOS, "logo_gore", None, _rk_logos, cache=_logo_idx)
            _gr = resolve_logo_path(
                DIR_LOGOS, "logo_grrnga", None, _rk_logos, cache=_logo_idx)
            if os.path.isfile(_g):
                arcpy.AddMessage(f"    GORE -> {os.path.basename(_g)}")
            if os.path.isfile(_gr):
                arcpy.AddMessage(f"    Gerencia -> {os.path.basename(_gr)}")
            _faltan = listar_logos_faltantes(
                DIR_LOGOS, _rk_logos, list(ACR_NOMBRES.keys()))
            if _faltan:
                arcpy.AddWarning(
                    "  Logos ACR/GORE pendientes: " + ", ".join(_faltan)
                )
            else:
                arcpy.AddMessage(
                    f"  Logos ACR ({len(ACR_NOMBRES)}): todos resueltos"
                )
        except Exception:
            pass

        if MODO_ESTABLE:
            arcpy.AddMessage(
                "  MODO ESTABLE: PDF sin mapa matplotlib ni GEE (respaldo si Pro se cierra)."
            )
            if "ID ?" in str(ALERTA_SEL):
                arcpy.AddWarning(
                    "Lista sin OID. Ejecute Diagnostico Pre-Vuelo y elija OID:123|..."
                )
            ok_libs, falta_libs = verify_libraries(
                check_gee=False,
                check_contextily=False,
                omit_modulos=["geopandas", "fiona", "numpy", "matplotlib", "requests"],
                msg_fn=arcpy.AddMessage,
            )
            if not ok_libs:
                arcpy.AddError(
                    "Librerias minimas no disponibles.\n"
                    f"  pip install {' '.join(falta_libs)}"
                )
                return
            from atd_ejecutar_estable import ejecutar_reporte_modo_estable
            try:
                ejecutar_reporte_modo_estable({
                    "gdb_path": GDB_PATH,
                    "fc_alertas": FC_ALERTAS,
                    "fecha_ini": FECHA_INI_REPORTE,
                    "fecha_fin": FECHA_FIN_REPORTE,
                    "base_salida": BASE_SALIDA,
                    "dir_logos": DIR_LOGOS,
                    "alerta_sel": ALERTA_SEL,
                    "acr_filtro": ACR_FILTRO,
                    "responsable": RESPONSABLE_NOMBRE,
                    "cargo": RESPONSABLE_CARGO,
                    "fn_prep_docs": preparar_documentacion_html,
                    "fn_link_vis": link_visualizacion_alerta,
                    "msg_fn": arcpy.AddMessage,
                })
            except Exception as e:
                arcpy.AddError(str(e))
                arcpy.AddError(traceback.format_exc())
            return

        # PDF completo fuera del proceso UI de Pro (evita cierre al cargar GeoPandas/matplotlib)
        if os.environ.get("ATD_DENTRO_SUBPROCESO") != "1":
            from atd_ejecutar_estable import ejecutar_reporte_subproceso_completo

            arcpy.AddMessage(
                f"  ATD v{__version__}: PDF completo en subproceso "
                "(mapa + imagenes; ArcGIS Pro permanece abierto)."
            )
            if "ID ?" in str(ALERTA_SEL):
                arcpy.AddWarning(
                    "Lista sin OID. Ejecute Diagnostico Pre-Vuelo y elija OID:123|..."
                )
            try:
                ejecutar_reporte_subproceso_completo({
                    "gdb_path": GDB_PATH,
                    "fc_alertas": FC_ALERTAS,
                    "fc_anp": FC_ANP,
                    "fc_zonif": FC_ZONIF,
                    "fecha_ini": FECHA_INI_REPORTE,
                    "fecha_fin": FECHA_FIN_REPORTE,
                    "base_salida": BASE_SALIDA,
                    "dir_logos": DIR_LOGOS,
                    "alerta_sel": ALERTA_SEL,
                    "acr_filtro": ACR_FILTRO,
                    "descargar_gee": DESCARGAR_GEE,
                    "gee_project": GEE_PROJECT,
                    "gee_dias": GEE_DIAS_BUSQUEDA,
                    "gee_nubes": GEE_MAX_NUBES,
                    "responsable": RESPONSABLE_NOMBRE,
                    "cargo": RESPONSABLE_CARGO,
                    "msg_fn": arcpy.AddMessage,
                })
            except Exception as e:
                arcpy.AddError(str(e))
                arcpy.AddError(traceback.format_exc())
            return

        if "ID ?" in str(ALERTA_SEL):
            arcpy.AddWarning(
                "La alerta elegida no tiene OBJECTID en la lista. Ejecute "
                "'1. Diagnostico Pre-Vuelo', actualice la toolbox y vuelva a elegir."
            )

        ok_libs, falta_libs = verify_libraries(
            check_gee=(not OMITIR_GEE) and (not MODO_ESTABLE),
            check_contextily=False,
            omit_modulos=["matplotlib", "numpy"] if MODO_ESTABLE else [],
            msg_fn=arcpy.AddMessage,
        )
        if not ok_libs:
            arcpy.AddError(
                "Librerias no disponibles en el Python de ArcGIS Pro.\n"
                f"  Ruta: {sys.executable}\n"
                "  Abre: Inicio > ArcGIS > Python Command Prompt\n"
                "  Luego ejecuta:\n"
                f"    python -m pip install {' '.join(falta_libs)}"
            )
            return

        warnings.filterwarnings("ignore")
        import gc

        # contextily en el proceso de Pro puede cerrar la app; en subproceso va activo
        _ctx_env = os.environ.get("ATD_USAR_CONTEXTILY", "").strip().lower()
        _en_sub = os.environ.get("ATD_DENTRO_SUBPROCESO", "").strip() in (
            "1", "true", "True", "yes",
        )
        if _ctx_env in ("0", "false", "no"):
            USAR_CTX_BASEMAP = False
        elif _ctx_env in ("1", "true", "yes"):
            USAR_CTX_BASEMAP = True
        else:
            USAR_CTX_BASEMAP = _en_sub

        try:
            import geopandas as gpd
            import pandas as pd
            if not MODO_ESTABLE:
                import numpy as np
            else:
                np = None
        except ImportError as e:
            arcpy.AddError(f"Falta libreria: {e}")
            return

        ctx = None
        plt = mpatches = pe = FuncFormatter = None
        USAR_MATPLOTLIB = not MODO_ESTABLE

        if USAR_MATPLOTLIB and USAR_CTX_BASEMAP:
            try:
                import contextily as ctx
                arcpy.AddMessage("  Mapa base satelital (contextily): ACTIVADO")
            except ImportError:
                arcpy.AddWarning("contextily no instalado — mapas sin fondo satelital")
                ctx = None

        if USAR_MATPLOTLIB:
            try:
                import matplotlib
                matplotlib.use("Agg")
                import matplotlib.pyplot as plt
                plt.ioff()
                import matplotlib.patches as mpatches
                import matplotlib.patheffects as pe
                from matplotlib.ticker import FuncFormatter
            except ImportError as e:
                arcpy.AddError(f"Falta matplotlib: {e}")
                return
        else:
            arcpy.AddMessage("  Mapa contextual: omitido en modo estable")

        try:
            from PIL import Image as PILImage, ImageDraw
            from PIL import ImageEnhance
        except ImportError as e:
            arcpy.AddError(f"Falta Pillow: {e}. Instala con pip install pillow")
            return

        try:
            import pyproj
        except ImportError as e:
            arcpy.AddError(f"Falta pyproj: {e}")
            return

        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib import colors
            from reportlab.lib.units import cm, mm
            from reportlab.lib.styles import ParagraphStyle
            from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
            from reportlab.platypus import (
                SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                Image as RLImage, HRFlowable
            )
        except ImportError as e:
            arcpy.AddError(f"Falta reportlab: {e}. Instala con pip install reportlab")
            return

        # GEE (Celda 3)
        HAS_GEE = False
        _req = None
        io = None
        if not OMITIR_GEE:
            try:
                import ee
                import requests as _req
                import io
                try:
                    ee.Initialize(project=GEE_PROJECT)
                except Exception:
                    ee.Initialize()
                HAS_GEE = True
                arcpy.AddMessage(f"GEE activo (proyecto: {GEE_PROJECT})")
                arcpy.AddMessage(
                    f"  Ventana Sentinel-2: {GEE_DIAS_BUSQUEDA} dias antes/despues | "
                    f"max nubes: {GEE_MAX_NUBES}%"
                )
            except Exception as eg:
                arcpy.AddWarning(
                    f"GEE no disponible: {eg}. PDFs sin imagenes Sentinel-2.\n"
                    "Ejecuta en arcgispro-py3: earthengine authenticate"
                )
        else:
            arcpy.AddMessage(
                "Descarga Sentinel-2 desactivada (solo mapa contextual + PDF)."
            )

        # PASO 2 — Cargar alertas (Celda 2)
        arcpy.AddMessage("=" * 65)
        arcpy.AddMessage(f"CARGANDO ALERTAS  {FECHA_INI_REPORTE} -> {FECHA_FIN_REPORTE}")
        arcpy.AddMessage("=" * 65)

        oid_sel = parse_seleccion_alerta(ALERTA_SEL)
        if oid_sel == "sin_alertas":
            arcpy.AddError(
                "No hay alertas en el periodo. Ejecute '1. Diagnostico Pre-Vuelo' "
                f"({FECHA_INI_REPORTE} - {FECHA_FIN_REPORTE}) y revise la GDB."
            )
            return

        try:
            if isinstance(oid_sel, int):
                arcpy.AddMessage(f"  Modo rapido: 1 alerta por OBJECTID={oid_sel}")
                gdf_una = _leer_alerta_por_oid(
                    GDB_PATH, FC_ALERTAS, oid_sel, msg_fn=arcpy.AddMessage
                )
                df_periodo = _aplicar_filtros_acr_periodo(
                    gdf_una, FECHA_INI_REPORTE, FECHA_FIN_REPORTE
                )
            else:
                df_periodo, _ = filtrar_alertas_periodo(
                    GDB_PATH, FC_ALERTAS, FECHA_INI_REPORTE, FECHA_FIN_REPORTE
                )
        except Exception as e:
            arcpy.AddError(f"Error leyendo {FC_ALERTAS}: {e}")
            return

        if len(df_periodo) == 0:
            arcpy.AddError("Sin alertas en el periodo. Ajusta las fechas.")
            return

        df_periodo = enriquecer_alertas(df_periodo, modo_ligero=MODO_ESTABLE)

        acr_gdf, zi_gdf, zonif_gdf = None, None, None
        if not MODO_ESTABLE:
            try:
                acr_gdf, zi_gdf = cargar_acr_y_zi(GDB_PATH, FC_ANP)
            except Exception as e:
                arcpy.AddWarning(f"No se pudo cargar ACR/ZI: {e}")

            try:
                zonif_gdf = gpd.read_file(GDB_PATH, layer=FC_ZONIF)
                arcpy.AddMessage(f"  Zonificación : {len(zonif_gdf)} registros")
            except Exception as ez:
                arcpy.AddWarning(f"Zonificación no cargada: {ez}")

        if not MODO_ESTABLE:
            gdb_gestion = (
                DEFAULT_GESTION_GDB_LORETO
                if _REGION_ACTIVA == "loreto"
                and os.path.isdir(DEFAULT_GESTION_GDB_LORETO)
                else None
            )
            try:
                df_periodo = enriquecer_ubicacion_alertas(
                    df_periodo, zonif_gdf=zonif_gdf, gdb_gestion=gdb_gestion
                )
                arcpy.AddMessage(
                    "  Ubicacion (gestion/zonif): lugar poblado, sector y OLV cercano"
                )
            except Exception as eu:
                arcpy.AddWarning(f"No se pudo enriquecer ubicacion: {eu}")
        else:
            df_periodo["lugar_poblado"] = "-"
            df_periodo["sector_reporte"] = "-"
            df_periodo["olv_cercano"] = "-"

        # Resumen por ACR
        arcpy.AddMessage("")
        for cod, nom in ACR_NOMBRES.items():
            s = df_periodo[df_periodo["anp_codi"]==cod]
            n = len(s); ha = s["md_sup"].sum() if "md_sup" in s.columns else 0
            flag = "" if n > 0 else "  <- sin alertas"
            arcpy.AddMessage(f"  {cod:<8} {nom:<42} {n:>5,} {ha:>10.4f}{flag}")

        alertas_para_reporte = df_periodo.copy()
        arcpy.AddMessage(f"\nOK {len(alertas_para_reporte):,} alertas listas")

        if ACR_FILTRO and ACR_FILTRO in ACR_CODIGOS_FC:
            alertas_para_reporte = alertas_para_reporte[
                alertas_para_reporte["anp_codi"] == ACR_FILTRO
            ].copy()
            arcpy.AddMessage(f"  Filtro ACR {ACR_FILTRO}: {len(alertas_para_reporte)} alertas")

        oid_sel = parse_seleccion_alerta(ALERTA_SEL)
        if oid_sel == "sin_alertas":
            arcpy.AddError(
                "No hay alertas en el periodo. Ejecute '1. Diagnostico Pre-Vuelo' "
                f"({FECHA_INI_REPORTE} - {FECHA_FIN_REPORTE}) y revise la GDB."
            )
            return
        if oid_sel == "match_attrs":
            df_match = _filtrar_df_por_etiqueta(alertas_para_reporte, ALERTA_SEL)
            if len(df_match) == 1:
                df_procesar = df_match.copy()
                oid_val = df_procesar.iloc[0].get("objectid", "?")
                arcpy.AddMessage(
                    f"  Modo: 1 alerta (coincidencia por atributos, OID={oid_val})"
                )
            elif len(df_match) == 0:
                arcpy.AddError(
                    "No se identifico la alerta seleccionada. Ejecute "
                    "'1. Diagnostico Pre-Vuelo', actualice la lista y elija de nuevo."
                )
                return
            else:
                arcpy.AddError(
                    f"La seleccion coincide con {len(df_match)} alertas. "
                    "Ejecute Diagnostico Pre-Vuelo y elija una con OID visible."
                )
                return
        elif isinstance(oid_sel, int):
            if "objectid" not in alertas_para_reporte.columns:
                alertas_para_reporte = normalize_oid_column(alertas_para_reporte)
            # Comparar como int para evitar fallo int vs int64
            df_procesar = alertas_para_reporte[
                alertas_para_reporte["objectid"].astype(int) == oid_sel
            ].copy()
            if len(df_procesar) == 0:
                # Si solo hay 1 alerta en el DataFrame (ya filtrada por modo rapido),
                # usarla directamente
                if len(alertas_para_reporte) == 1:
                    df_procesar = alertas_para_reporte.copy()
                    arcpy.AddMessage(
                        f"  Modo: 1 alerta (OID recuperado directamente)"
                    )
                else:
                    arcpy.AddError(
                        f"No se encontro la alerta OID={oid_sel} tras filtros de periodo/ACR."
                    )
                    return
            else:
                arcpy.AddMessage(f"  Modo: 1 alerta (OID={oid_sel})")
        elif oid_sel is None:
            df_procesar = alertas_para_reporte.copy()
            arcpy.AddMessage(f"  Modo: TODAS las alertas ({len(df_procesar)})")
        else:
            arcpy.AddError("Seleccion de alerta no valida.")
            return

        EPSG_MAPA = _utm_epsg_region()
        RK_LOGOS = _REGION_ACTIVA or LOGO_REGION_KEY or "loreto"
        arcpy.AddMessage(
            f"  Region activa: {REGION_NOMBRE} | UTM EPSG:{EPSG_MAPA} | logos: {RK_LOGOS}"
        )

        # ══════════════════════════════════════════════════════════
        # FUNCIONES GEE — igual a Celda 3
        # ══════════════════════════════════════════════════════════
        def bbox_wgs(geom_wgs, buffer_m=600):
            gdf = gpd.GeoDataFrame(geometry=[geom_wgs], crs="EPSG:4326").to_crs(
                f"EPSG:{EPSG_MAPA}")
            gdf["geometry"] = gdf.geometry.buffer(buffer_m)
            return gdf.to_crs("EPSG:4326").total_bounds

        def marcar_alerta_en_imagen(arr_rgb, bounds_mapa, geom_wgs):
            """Dibuja poligono rojo de la alerta sobre imagen Sentinel."""
            return quemar_vector_alerta_en_imagen(
                arr_rgb,
                bounds_mapa,
                geom_wgs,
                epsg_bounds=EPSG_MAPA,
                epsg_geom=4326,
            )

        def descargar_sentinel2(geom_wgs, fecha_ref_str, tipo="antes", dias=45, max_nubes=35):
            """Descarga Sentinel-2 SR. Retorna (arr, bounds_utm, fecha, nubes, id) o None."""
            if not HAS_GEE:
                return None
            try:
                from datetime import timedelta
                fd  = pd.to_datetime(fecha_ref_str)
                if tipo == "antes":
                    fi_s = (fd - timedelta(days=dias)).strftime("%Y-%m-%d")
                    ff_s = fd.strftime("%Y-%m-%d")
                else:
                    fi_s = fd.strftime("%Y-%m-%d")
                    ff_s = (fd + timedelta(days=dias)).strftime("%Y-%m-%d")

                b   = bbox_wgs(geom_wgs, buffer_m=600)
                roi = ee.Geometry.Rectangle([b[0], b[1], b[2], b[3]])

                col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                         .filterBounds(roi).filterDate(fi_s, ff_s)
                         .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", max_nubes))
                         .sort("CLOUDY_PIXEL_PERCENTAGE"))

                if col.size().getInfo() == 0:
                    fi_s2 = (fd - timedelta(days=dias*2)).strftime("%Y-%m-%d") if tipo=="antes" else fi_s
                    ff_s2 = ff_s if tipo=="antes" else (fd + timedelta(days=dias*2)).strftime("%Y-%m-%d")
                    col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                             .filterBounds(roi).filterDate(fi_s2, ff_s2)
                             .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 70))
                             .sort("CLOUDY_PIXEL_PERCENTAGE"))
                    if col.size().getInfo() == 0:
                        return None

                img      = col.first()
                fecha_img = ee.Date(img.get("system:time_start")).format("YYYY-MM-dd").getInfo()
                nubes     = img.get("CLOUDY_PIXEL_PERCENTAGE").getInfo()
                id_img    = img.get("system:index").getInfo()

                rgb  = img.select(["B4","B3","B2"]).divide(10000).clamp(0, 0.3)
                url  = rgb.visualize(min=0, max=0.3).getThumbURL(
                    {"region": roi, "dimensions": 800, "format": "png"})
                resp = _req.get(url, timeout=90)
                arr  = np.array(PILImage.open(io.BytesIO(resp.content)).convert("RGB"))

                tr = pyproj.Transformer.from_crs(
                    "EPSG:4326", f"EPSG:{EPSG_MAPA}", always_xy=True)
                xmin, ymin = tr.transform(b[0], b[1])
                xmax, ymax = tr.transform(b[2], b[3])

                return arr, (xmin, xmax, ymin, ymax), fecha_img, round(nubes, 1), id_img

            except Exception as e:
                arcpy.AddWarning(f"    GEE error: {e}")
                return None

        # ══════════════════════════════════════════════════════════
        # FUNCIÓN MAPA — igual a Celda 4
        # ══════════════════════════════════════════════════════════
        def generar_mapa_contextual(i_row, acr_gdf, zi_gdf, idx_alerta, total_alertas):
            if not USAR_MATPLOTLIB:
                return None
            alerta_row = alertas_para_reporte.loc[i_row]
            oid = alerta_row.get("objectid", idx_alerta)
            cod_acr = str(alerta_row.get("anp_codi", "SIN")).strip()
            nombre = alerta_row.get("acr_nombre", cod_acr)
            geom = alerta_row.geometry
            if geom is None or geom.is_empty:
                arcpy.AddWarning(f"  AVISO: geometria vacia OID={oid}")
                return None

            gdf_al = alertas_para_reporte.loc[[i_row]].to_crs(f"EPSG:{EPSG_MAPA}")
            centroide = gdf_al.geometry.centroid.iloc[0]

            acr_sub = None
            if acr_gdf is not None and len(acr_gdf) > 0:
                _match = acr_gdf[acr_gdf["_cod_clean"] == cod_acr]
                if len(_match) > 0:
                    acr_sub = _match.to_crs(f"EPSG:{EPSG_MAPA}")
                    arcpy.AddMessage(f"  ACR OK: {cod_acr} -> {nombre}")
                else:
                    arcpy.AddWarning(f"  AVISO: '{cod_acr}' no encontrado. Disponibles: {acr_gdf['_cod_clean'].tolist()}")

            zi_sub = None
            if zi_gdf is not None and len(zi_gdf) > 0:
                _zmatch = zi_gdf[zi_gdf["_zi_acr"] == cod_acr]
                if len(_zmatch) > 0:
                    zi_sub = _zmatch.to_crs(f"EPSG:{EPSG_MAPA}")

            fig, ax = plt.subplots(figsize=(6.0, 6.0), dpi=160)
            fig.patch.set_facecolor("#0a1a0a")
            ax.set_facecolor("#0a1a0a")
            fig.subplots_adjust(left=0.07, right=0.99, top=0.90, bottom=0.20)

            def _extent_mapa(acr_g, zi_g, al_g, pad=0.14):
                xs, ys = [], []
                for g in (acr_g, zi_g, al_g):
                    if g is not None and not g.empty:
                        b = g.total_bounds
                        xs.extend([b[0], b[2]])
                        ys.extend([b[1], b[3]])
                if not xs:
                    return None
                xmin, xmax = min(xs), max(xs)
                ymin, ymax = min(ys), max(ys)
                cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2
                half = max(xmax - xmin, ymax - ymin) / 2
                half = max(half * (1 + pad), 8000)
                return cx - half, cx + half, cy - half, cy + half

            ext = _extent_mapa(acr_sub, zi_sub, gdf_al)
            if ext is None:
                arcpy.AddWarning(f"  AVISO: sin extent para mapa OID={oid}")
                plt.close(fig)
                return None
            x0, x1, y0, y1 = ext
            ax.set_xlim(x0, x1)
            ax.set_ylim(y0, y1)
            ax.set_aspect("equal", adjustable="box")

            fondo_ok = False
            try:
                from atd_map_basemap import add_esri_world_imagery
                fondo_ok = add_esri_world_imagery(
                    ax, x0, x1, y0, y1, EPSG_MAPA, log_fn=arcpy.AddMessage,
                )
            except Exception:
                fondo_ok = False

            if not fondo_ok and ctx and USAR_CTX_BASEMAP:
                for prv in [ctx.providers.Esri.WorldImagery,
                            ctx.providers.OpenStreetMap.Mapnik]:
                    try:
                        ctx.add_basemap(
                            ax, crs=f"EPSG:{EPSG_MAPA}", source=prv,
                            zoom="auto", attribution=False,
                        )
                        fondo_ok = True
                        arcpy.AddMessage("  Fondo satelital: contextily (Esri)")
                        break
                    except Exception:
                        continue

            if fondo_ok:
                fig.patch.set_facecolor("#252525")
                ax.set_facecolor("#252525")
                _grid_c = "#ffffff"
                _lbl_c = "#ffffff"
                _spine_c = "#888888"
                _zi_alpha = 0.28
            else:
                arcpy.AddWarning(
                    "  Sin basemap satelital (revisar conexion o pyproj/Pillow)."
                )
                _grid_c = "#aaaaaa"
                _lbl_c = "#ffffff"
                _spine_c = "#444444"
                _zi_alpha = 0.22

            ZI_FILL = "#A8E6A1"
            ZI_LINE = "#66BB6A"
            if zi_sub is not None and not zi_sub.empty:
                zi_sub.plot(ax=ax, color=ZI_FILL, alpha=_zi_alpha, zorder=2)
                zi_sub.boundary.plot(
                    ax=ax, color=ZI_LINE, linewidth=2.2,
                    linestyle=(0, (6, 4)), zorder=4,
                )

            if acr_sub is not None and not acr_sub.empty:
                acr_sub.plot(ax=ax, color="#1B5E20", alpha=0.20, zorder=3)
                acr_sub.boundary.plot(ax=ax, color="#1a1a1a", linewidth=2.8, zorder=5)
                acr_sub.boundary.plot(ax=ax, color="#FFD54F", linewidth=1.8, zorder=6)

            ax.scatter([centroide.x], [centroide.y],
                       c="red", s=200, edgecolors="white", linewidths=1.8, zorder=9)
            ax.scatter([centroide.x], [centroide.y],
                       c="none", s=480, edgecolors="red", linewidths=2.2, zorder=8, alpha=0.6)

            ax.grid(True, linestyle="--", alpha=0.28 if fondo_ok else 0.35,
                    color=_grid_c, linewidth=0.5, zorder=2)
            ax.ticklabel_format(style="plain", axis="both")
            ax.tick_params(axis="both", labelsize=5.5, colors=_lbl_c)
            ax.spines[:].set_color(_spine_c)
            fmt_e = FuncFormatter(lambda v, p: f"{v/1000:.0f}K")
            fmt_n = FuncFormatter(lambda v, p: f"{v/1000:.1f}K")
            ax.xaxis.set_major_formatter(fmt_e)
            ax.yaxis.set_major_formatter(fmt_n)
            ax.set_xlabel("Este (m)", fontsize=5.5, color=_lbl_c)
            ax.set_ylabel("Norte (m)", fontsize=5.5, color=_lbl_c)

            ax.annotate("N", xy=(0.06, 0.94), xycoords="axes fraction",
                       fontsize=9, fontweight="bold", ha="center", va="center",
                       color="white",
                       path_effects=[pe.withStroke(linewidth=2, foreground="black")], zorder=12)
            ax.annotate("", xy=(0.06, 0.90), xycoords="axes fraction",
                       xytext=(0.06, 0.84), textcoords="axes fraction",
                       arrowprops=dict(arrowstyle="->", color="white", lw=1.8), zorder=12)

            sup   = alerta_row.get("md_sup", 0) or 0
            causa = alerta_row.get("causa_texto", "-")
            ax.set_title(
                f"{nombre}\nAlerta #{idx_alerta+1}/{total_alertas} — {causa} | {sup:.4f} ha",
                fontsize=6, fontweight="bold", color="white", pad=3,
                path_effects=[pe.withStroke(linewidth=1.2, foreground="black")]
            )

            handles = []
            if zi_sub is not None and not zi_sub.empty:
                handles.append(mpatches.Patch(
                    facecolor=ZI_FILL, edgecolor=ZI_LINE, linewidth=2,
                    linestyle="--", alpha=0.5, label="Zona de Influencia (ZI)",
                ))
            if acr_sub is not None and not acr_sub.empty:
                handles.append(mpatches.Patch(
                    facecolor="none", edgecolor="#FFD54F",
                    linewidth=1.8, label=nombre[:42]))
            handles.append(mpatches.Patch(
                facecolor="red", edgecolor="white",
                label=f"Alerta {idx_alerta+1} | {sup:.4f} ha"))
            ax.legend(
                handles=handles,
                loc="lower center",
                bbox_to_anchor=(0.5, 0.02),
                ncol=3,
                fontsize=4.5,
                framealpha=0.93,
                facecolor="#111111" if fondo_ok else "#111111",
                labelcolor="white",
                edgecolor="#FFD54F" if fondo_ok else "#66BB6A",
                borderpad=0.35,
                columnspacing=0.6,
                handlelength=1.1,
                handleheight=0.85,
            )

            ax.set_xlim(x0, x1)
            ax.set_ylim(y0, y1)
            ruta = os.path.join(DIR_MAPAS, f"mapa_{cod_acr}_{idx_alerta+1:03d}_OID{oid}.png")
            fig.savefig(
                ruta, dpi=140, facecolor=fig.get_facecolor(),
            )
            plt.close(fig)
            plt.close("all")
            gc.collect()
            return ruta

        # ══════════════════════════════════════════════════════════
        # FUNCIÓN PDF — igual a Celda 5
        # ══════════════════════════════════════════════════════════

        # Paleta institucional GFP (alineada al visor satelital)
        C_AZUL_GFP = colors.HexColor("#2F5F8F")
        C_ROJO_GFP = colors.HexColor("#C41E3A")
        C_ROJO     = C_ROJO_GFP
        C_ROJO_D   = colors.HexColor("#8B1528")
        C_VERDE_H  = C_AZUL_GFP
        C_VERDE_S  = colors.HexColor("#E8EEF4")
        C_VERDE_CB = C_AZUL_GFP
        C_AZUL_CB  = colors.HexColor("#3A7CA5")
        C_GRIS_F   = colors.HexColor("#F4F6F8")
        C_BORDE    = colors.HexColor("#B8C8D8")
        C_BORDE_EXT= C_AZUL_GFP
        C_BLANCO   = colors.white
        C_NEGRO    = colors.black
        C_LINK     = colors.HexColor("#2F5F8F")

        def _s(texto, fuente="Helvetica", tam=8, color=None,
               align=TA_LEFT, bold=False, italic=False, leading=10, **kw):
            if color is None:
                color = C_NEGRO
            f = fuente
            if bold and italic: f += "-BoldOblique"
            elif bold:          f += "-Bold"
            elif italic:        f += "-Oblique"
            return Paragraph(str(texto),
                             ParagraphStyle("_x", fontName=f, fontSize=tam,
                                            textColor=color, alignment=align,
                                            leading=leading, **kw))

        def img_rl(ruta, max_w, max_h, label=""):
            """Imagen sin estirar: conserva proporcion dentro del recuadro."""
            if not ruta or not os.path.exists(str(ruta)):
                return _s(f"[ {label} ]", align=TA_CENTER, color=colors.grey, tam=7)
            try:
                iw, ih = PILImage.open(str(ruta)).size
                if iw < 1 or ih < 1:
                    return _s(f"[ {label} ]", align=TA_CENTER, color=colors.grey, tam=7)
                ratio = iw / ih
                mw, mh = float(max_w), float(max_h)
                if mw / mh > ratio:
                    h_use = mh
                    w_use = mh * ratio
                else:
                    w_use = mw
                    h_use = mw / ratio
                return RLImage(str(ruta), width=w_use, height=h_use)
            except Exception:
                return RLImage(str(ruta), width=max_w, height=max_h)

        def celda_centro(flow, ancho, alto):
            t = Table([[flow]], colWidths=[ancho], rowHeights=[alto])
            t.setStyle(TableStyle([
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))
            return t

        def cab(numero, titulo, ancho):
            t = Table([[_s(f"{numero}.  {titulo}", bold=True, tam=7.5, color=C_BLANCO)]],
                      colWidths=[ancho])
            t.setStyle(TableStyle([
                ("BACKGROUND",    (0,0),(-1,-1), C_VERDE_CB),
                ("TOPPADDING",    (0,0),(-1,-1), 3),
                ("BOTTOMPADDING", (0,0),(-1,-1), 3),
                ("LEFTPADDING",   (0,0),(-1,-1), 5),
            ]))
            return t

        def tabla_sec(numero, titulo, filas, w1, w2):
            datos = [[_s(l, bold=True, tam=7.5), _s(str(v) if v else "-", tam=7.5)]
                     for l, v in filas]
            ti = Table(datos, colWidths=[w1, w2])
            ti.setStyle(TableStyle([
                ("FONTSIZE",       (0,0),(-1,-1), 7.5),
                ("VALIGN",         (0,0),(-1,-1), "MIDDLE"),
                ("TOPPADDING",     (0,0),(-1,-1), 2.5),
                ("BOTTOMPADDING",  (0,0),(-1,-1), 2.5),
                ("LEFTPADDING",    (0,0),(-1,-1), 4),
                ("ROWBACKGROUNDS", (0,0),(-1,-1), [C_BLANCO, C_GRIS_F]),
                ("LINEBELOW",      (0,0),(-1,-2), 0.3, C_BORDE),
                ("BOX",            (0,0),(-1,-1), 0.5, C_BORDE),
            ]))
            wrap = Table([[cab(numero, titulo, w1+w2)], [ti]], colWidths=[w1+w2])
            wrap.setStyle(TableStyle([
                ("BOX",           (0,0),(-1,-1), 1.2, C_BORDE_EXT),
                ("TOPPADDING",    (0,0),(-1,-1), 0),
                ("BOTTOMPADDING", (0,0),(-1,-1), 0),
                ("LEFTPADDING",   (0,0),(-1,-1), 0),
                ("RIGHTPADDING",  (0,0),(-1,-1), 0),
            ]))
            return wrap

        def tabla_sec_link(numero, titulo, filas_link, w1, w2):
            textos_cortos = {
                "Metodología:": "Abrir metodología (documento HTML)",
                "Procedimiento:": "Abrir guía de fotointerpretación",
                "Visualización:": "Abrir Dashboard ACR (monitoreo deforestación)",
            }
            datos = []
            for l, url in filas_link:
                txt_link = textos_cortos.get(l, "Abrir enlace")
                datos.append([
                    _s(l, bold=True, tam=7),
                    _s(
                        f'<link href="{url}"><u><font color="{C_LINK.hexval()}">'
                        f"{txt_link}</font></u></link>",
                        tam=6.5, leading=8,
                    ),
                ])
            ti = Table(datos, colWidths=[w1, w2])
            ti.setStyle(TableStyle([
                ("FONTSIZE",       (0,0),(-1,-1), 7.5),
                ("VALIGN",         (0,0),(-1,-1), "MIDDLE"),
                ("TOPPADDING",     (0,0),(-1,-1), 2.5),
                ("BOTTOMPADDING",  (0,0),(-1,-1), 2.5),
                ("LEFTPADDING",    (0,0),(-1,-1), 4),
                ("ROWBACKGROUNDS", (0,0),(-1,-1), [C_BLANCO, C_GRIS_F]),
                ("LINEBELOW",      (0,0),(-1,-2), 0.3, C_BORDE),
                ("BOX",            (0,0),(-1,-1), 0.5, C_BORDE),
            ]))
            wrap = Table([[cab(numero, titulo, w1+w2)], [ti]], colWidths=[w1+w2])
            wrap.setStyle(TableStyle([
                ("BOX",           (0,0),(-1,-1), 1.2, C_BORDE_EXT),
                ("TOPPADDING",    (0,0),(-1,-1), 0),
                ("BOTTOMPADDING", (0,0),(-1,-1), 0),
                ("LEFTPADDING",   (0,0),(-1,-1), 0),
                ("RIGHTPADDING",  (0,0),(-1,-1), 0),
            ]))
            return wrap

        def generar_pdf_alerta(alerta_row, idx, mapa_path, img_antes, img_despues):
            oid_row     = alerta_row.get("objectid", idx)
            oid         = resolver_oid_imagen(ALERTA_SEL, alerta_row) or oid_row
            try:
                oid = int(oid)
            except Exception:
                oid = oid_row
            cod_acr     = str(alerta_row.get("anp_codi", "SIN")).strip()
            sigla       = alerta_row.get("acr_sigla",  cod_acr)
            nombre_acr  = alerta_row.get("acr_nombre", cod_acr)
            causa       = alerta_row.get("causa_texto",  "Sin clasificar")
            bosque      = alerta_row.get("bosque_texto", "-")
            confianza   = alerta_row.get("conf_texto",   "-")
            zonif       = str(alerta_row.get("md_zonif",  "") or "-")
            superficie  = float(alerta_row.get("md_sup",  0) or 0)
            este        = alerta_row.get("md_este",   None)
            norte       = alerta_row.get("md_norte",  None)
            este_utm    = alerta_row.get("este_utm",  este  or 0)
            norte_utm   = alerta_row.get("norte_utm", norte or 0)
            grilla      = str(alerta_row.get("md_exa",    "") or "-")
            editor      = RESPONSABLE_NOMBRE
            md_img_url  = alerta_row.get("md_img", None)

            fecha_val = alerta_row.get("md_fecimg", None)
            fecha_str = "-"
            if pd.notna(fecha_val):
                try: fecha_str = pd.to_datetime(fecha_val).strftime("%d/%m/%Y")
                except Exception: fecha_str = str(fecha_val)

            fecha_emision = pd.Timestamp.today().strftime("%d/%m/%Y")
            cod_reporte   = f"RT-ATD-ACR-{sigla}-{ANNO_REPORTE}-{idx+1:04d}"
            geo           = ACR_GEO.get(cod_acr, {})
            provincia     = geo.get("provincia", "-")
            distrito      = geo.get("distrito",  "-")
            lugar_poblado = str(alerta_row.get("lugar_poblado", "") or "-")
            sector_rep    = str(alerta_row.get("sector_reporte", "") or "-")
            olv_cercano   = str(alerta_row.get("olv_cercano", "") or "-")
            geom_alerta   = alerta_row.geometry

            # Preparar imágenes Sentinel (con marca de alerta)
            def _cargar_local_h3(sufijo):
                ruta_png, meta = buscar_imagen_local(
                    DIR_IMAGENES,
                    sufijo,
                    oid_principal=oid,
                    alerta_sel=ALERTA_SEL,
                    regenerar_si_falta=True,
                )
                if not ruta_png:
                    return None
                fecha_local = "-"
                id_local = "-"
                sat_local = "Imagen satelital"
                if meta:
                    fecha_raw = str(meta.get("fecha", "") or "")
                    if fecha_raw:
                        try:
                            fecha_local = pd.to_datetime(fecha_raw).strftime("%d/%m/%Y")
                        except Exception:
                            fecha_local = fecha_raw
                    id_local = str(meta.get("id", "") or "-")
                    sat_local = str(meta.get("sat", "") or sat_local)
                ruta_marcada = marcar_png_con_alerta(
                    ruta_png, geom_alerta, meta=meta, epsg_utm=EPSG_MAPA)
                arcpy.AddMessage(
                    f"  Img {sufijo} desde archivo: {os.path.basename(ruta_marcada)}"
                )
                return ruta_marcada, fecha_local, id_local, sat_local

            def prep_s2(img_tuple, sufijo):
                if img_tuple is None:
                    return None, "-", "-"
                arr, bounds, fecha_img, nubes, id_img = img_tuple
                arr_m = marcar_alerta_en_imagen(arr, bounds, geom_alerta)
                ruta  = os.path.join(DIR_IMAGENES, f"S2_{sufijo}_{cod_acr}_{idx+1:03d}.png")
                pil = PILImage.fromarray(arr_m)
                try:
                    from PIL import ImageEnhance
                    pil = ImageEnhance.Contrast(pil.convert("RGB")).enhance(1.08)
                    pil = ImageEnhance.Sharpness(pil).enhance(1.05)
                except Exception:
                    pil = pil.convert("RGB")
                pil.save(ruta, format="PNG", optimize=True)
                return ruta, pd.to_datetime(fecha_img).strftime("%d/%m/%Y"), str(id_img or "-")

            sat_a = sat_d = "Imagen satelital"
            local_a = _cargar_local_h3("A")
            local_d = _cargar_local_h3("D")
            if local_a:
                ruta_a, fecha_a, cod_img_a, sat_a = local_a
            else:
                ruta_a, fecha_a, cod_img_a = prep_s2(img_antes, "A")
            if local_d:
                ruta_d, fecha_d, cod_img_d, sat_d = local_d
            else:
                ruta_d, fecha_d, cod_img_d = prep_s2(img_despues, "D")

            # Vista dinamica: comparacion antes/despues (swipe) + GEE
            id_a = cod_img_a if cod_img_a != "-" else (img_antes[4] if img_antes else None)
            id_b = cod_img_d if cod_img_d != "-" else (img_despues[4] if img_despues else None)
            if md_img_url and str(md_img_url).startswith("http"):
                url_eo = str(md_img_url)
                url_gee = str(md_img_url)
                nota_vista = "Enlace desde campo md_img de la alerta."
            else:
                url_eo, url_gee, nota_vista = urls_vista_comparativa(
                    este_utm, norte_utm,
                    fecha_antes=fecha_a if fecha_a != "-" else None,
                    fecha_despues=fecha_d if fecha_d != "-" else None,
                    img_id_a=id_a, img_id_b=id_b,
                    epsg_utm=EPSG_MAPA,
                )

            try:
                import pyproj as _pyproj
                _tr_ll = _pyproj.Transformer.from_crs(
                    f"EPSG:{EPSG_MAPA}", "EPSG:4326", always_xy=True)
                _lon_al, _lat_al = _tr_ll.transform(float(este_utm), float(norte_utm))
            except Exception:
                _lon_al, _lat_al = 0.0, 0.0

            LINK_VISUALIZACION = link_visualizacion_alerta(
                DIR_DOCS, oid, url_eo, url_gee,
                fecha_a if fecha_a != "-" else "—",
                fecha_d if fecha_d != "-" else "—",
                _lat_al, _lon_al, cod_reporte,
                ruta_img_a=ruta_a if ruta_a and os.path.isfile(str(ruta_a)) else None,
                ruta_img_d=ruta_d if ruta_d and os.path.isfile(str(ruta_d)) else None,
                sat_a=sat_a, sat_d=sat_d,
            )
            tiene_swipe_local = bool(
                ruta_a and ruta_d
                and os.path.isfile(str(ruta_a))
                and os.path.isfile(str(ruta_d))
            )

            nombre_pdf = f"ATD_{ANNO_REPORTE}_{cod_acr}_{idx+1:03d}_OID{oid}.pdf"
            pdf_path   = os.path.join(DIR_PDFS, nombre_pdf)
            W          = 18.6 * cm

            doc = SimpleDocTemplate(
                pdf_path, pagesize=A4,
                leftMargin=1.1 * cm, rightMargin=1.1 * cm,
                topMargin=0.7 * cm, bottomMargin=0.6 * cm,
            )
            story = []

            # ── BLOQUE 1: ENCABEZADO ───────────────────────────────
            if RK_LOGOS == "san_martin":
                logo_gore = img_rl(
                    _get_logo_path(DIR_LOGOS, "logo_gore", None, RK_LOGOS),
                    4.6 * cm, 1.6 * cm, "GORE",
                )
                t_liz = Table([[logo_gore]], colWidths=[4.8 * cm])
            else:
                logo_gore = img_rl(
                    _get_logo_path(DIR_LOGOS, "logo_gore", None, RK_LOGOS),
                    2.2 * cm, 1.6 * cm, "GORE",
                )
                logo_grrnga = img_rl(
                    _get_logo_path(DIR_LOGOS, "logo_grrnga", None, RK_LOGOS),
                    2.2 * cm, 1.6 * cm, "GRRNGA",
                )
                t_liz = Table([[logo_gore, logo_grrnga]], colWidths=[2.4 * cm, 2.4 * cm])
            t_liz.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]))
            logo_gfp_h = img_rl(
                _get_logo_path(DIR_LOGOS, "logo_gfp", None, RK_LOGOS), 2.2 * cm, 1.6 * cm, "GFP"
            )
            logo_anp_h = img_rl(
                _get_logo_path(DIR_LOGOS, "logo_anp", cod_acr, RK_LOGOS), 2.2 * cm, 1.6 * cm, "ACR"
            )
            t_lde = Table([[logo_gfp_h, logo_anp_h]], colWidths=[2.4 * cm, 2.4 * cm])
            t_lde.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]))

            t_hdr = Table([[
                t_liz,
                [
                    _s(GOBIERNO_REGIONAL, bold=True, tam=8.5, align=TA_CENTER),
                    _s(GERENCIA_REGIONAL, bold=True, tam=7.5, align=TA_CENTER),
                    _s(SUBGERENCIA_REGIONAL, bold=True, tam=7, align=TA_CENTER),
                ],
                t_lde,
            ]], colWidths=[5.0 * cm, 8.6 * cm, 5.0 * cm])
            t_hdr.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOX", (0, 0), (-1, -1), 1.2, C_BORDE_EXT),
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, C_BORDE_EXT),
            ]))
            story.append(t_hdr)
            story.append(Spacer(1, 1 * mm))

            # ── BLOQUE 2: TÍTULO ──────────────────────────────────
            t_titulo = Table([
                [_s("REPORTE TÉCNICO SOBRE ALERTA TEMPRANA DE DEFORESTACIÓN",
                    bold=True, tam=12, color=C_ROJO, align=TA_CENTER, leading=15)],
                [_s(nombre_acr.upper(),
                    bold=True, tam=10, color=C_BLANCO, align=TA_CENTER)],
            ], colWidths=[W])
            t_titulo.setStyle(TableStyle([
                ("BACKGROUND", (0, 1), (-1, 1), C_ROJO),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("BOX", (0, 0), (-1, -1), 1.2, C_ROJO_D),
                ("LINEBELOW", (0, 0), (-1, 0), 0, C_ROJO),
            ]))
            story.append(t_titulo)
            story.append(Spacer(1, 1 * mm))

            # ── BLOQUE 3: FICHA + MAPA ────────────────────────────
            W1, W2 = 3.4 * cm, 4.2 * cm

            t_s1 = tabla_sec("1", "Ubicacion en circunscripcion", [
                ("Departamento:", DEPARTAMENTO_REPORTE),
                ("Provincia:", provincia),
                ("Distrito:", distrito),
                ("Lugar Poblado Cercano:", lugar_poblado),
            ], W1, W2)

            t_s2 = tabla_sec("2", "Ubicacion en area de conservacion", [
                ("Nombre de ACR:", nombre_acr),
                ("Zonificacion:", zonif),
                ("Sector:", sector_rep),
                ("OLV Cercano:", olv_cercano),
            ], W1, W2)

            t_per = Table([[
                _s("Periodo de Monitoreo:", bold=True, tam=7.5),
                _s(f"{FECHA_INI_REPORTE} - {FECHA_FIN_REPORTE}", tam=7.5),
            ]], colWidths=[W1, W2])
            t_per.setStyle(TableStyle([
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("BOX", (0, 0), (-1, -1), 1.2, C_BORDE_EXT),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, C_BORDE),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ]))

            col_izq = [t_s1, Spacer(1, 1 * mm), t_s2, Spacer(1, 1 * mm), t_per]

            ancho_mapa = 10.6 * cm
            alto_mapa = 7.5 * cm
            mapa_img = celda_centro(
                img_rl(mapa_path, ancho_mapa, alto_mapa, "Mapa ACR"),
                ancho_mapa, alto_mapa,
            )

            t_mapa_wrap = Table([[mapa_img]], colWidths=[ancho_mapa], rowHeights=[alto_mapa])
            t_mapa_wrap.setStyle(TableStyle([
                ("BOX", (0, 0), (-1, -1), 1.2, C_BORDE_EXT),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]))

            t_ficha = Table(
                [[col_izq, t_mapa_wrap]],
                colWidths=[W1 + W2 + 0.3 * cm, ancho_mapa + 0.2 * cm],
            )
            t_ficha.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (1, 0), (1, 0), 3),
            ]))
            story.append(t_ficha)
            story.append(Spacer(1, 1 * mm))

            # ── BLOQUE 4: SENTINEL-2 ANTES/DESPUÉS ───────────────
            t_ve_cab = Table([[
                _s("Vista Estática de la Alerta Temprana de Deforestación",
                   bold=True, tam=8, color=C_BLANCO, align=TA_CENTER),
            ]], colWidths=[W])
            t_ve_cab.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), C_VERDE_H),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("BOX", (0, 0), (-1, -1), 1.2, C_BORDE_EXT),
            ]))
            story.append(t_ve_cab)
            story.append(Spacer(1, 1 * mm))

            AW = (W - 2 * mm) / 2
            AH = 4.2 * cm

            def cab_img(texto):
                t = Table([[_s(texto, bold=True, tam=7.5, color=C_BLANCO, align=TA_CENTER)]],
                          colWidths=[AW])
                t.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), C_AZUL_CB),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]))
                return t

            def meta(fecha, codigo, sat_nombre="Imagen satelital"):
                t = Table([[
                    _s(f"Satélite:  {sat_nombre}", bold=True, tam=6),
                    _s(f"Fecha:  {fecha}", bold=True, tam=6, align=TA_CENTER),
                ], [
                    _s(f"Código:  {str(codigo)[:38]}", tam=5.5, leading=7),
                    _s("", tam=5.5),
                ]], colWidths=[AW * 0.48, AW * 0.52])
                t.setStyle(TableStyle([
                    ("SPAN", (0, 1), (1, 1)),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3),
                    ("BACKGROUND", (0, 0), (-1, -1), C_GRIS_F),
                ]))
                return t

            img_a_rl = img_rl(ruta_a, AW, AH, "Sin imagen Sentinel A")
            img_d_rl = img_rl(ruta_d, AW, AH, "Sin imagen Sentinel B")

            t_s2imgs = Table([
                [cab_img("Imagen Satelital A: Sin Cambios"),
                 cab_img("Imagen Satelital B: Con Cambios")],
                [img_a_rl, img_d_rl],
                [meta(fecha_a, cod_img_a, sat_a),
                 meta(fecha_d, cod_img_d, sat_d)],
            ], colWidths=[AW, AW])
            t_s2imgs.setStyle(TableStyle([
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 1), (-1, 1), "MIDDLE"),
                ("BOX", (0, 0), (-1, -1), 1.2, C_BORDE_EXT),
                ("LINEAFTER", (0, 0), (0, -1), 0.5, C_BORDE),
                ("TOPPADDING", (0, 0), (-1, 0), 0),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 0),
                ("LEFTPADDING", (0, 0), (-1, 0), 0),
                ("RIGHTPADDING", (0, 0), (-1, 0), 0),
            ]))
            story.append(t_s2imgs)
            story.append(Spacer(1, 1.5 * mm))

            # ── BLOQUE 5: VISTA DINAMICA (enlace único en barra) ──
            url_vista = LINK_VISUALIZACION if tiene_swipe_local else url_eo
            if tiene_swipe_local:
                etiq_vista = (
                    f"Comparación swipe antes / después "
                    f"(Antes: {fecha_a} · Después: {fecha_d})"
                )
            else:
                etiq_vista = "Vista dinámica Sentinel-2 (EO Browser)"
            t_din_link = _s(
                f'<link href="{url_vista}"><u><font color="{C_LINK.hexval()}">'
                f"{etiq_vista}</font></u></link>",
                tam=7, leading=10, align=TA_CENTER,
            )
            t_din = Table([
                [_s("Vista Dinámica de la ATD",
                    bold=True, tam=7.5, color=C_NEGRO, align=TA_CENTER)],
                [t_din_link],
            ], colWidths=[W])
            t_din.setStyle(TableStyle([
                ("BOX", (0, 0), (-1, -1), 1.0, C_BORDE_EXT),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, C_BORDE),
                ("BACKGROUND", (0, 0), (-1, 0), C_VERDE_S),
                ("BACKGROUND", (0, 1), (-1, 1), C_BLANCO),
                ("TOPPADDING", (0, 0), (-1, 0), 3),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 3),
                ("TOPPADDING", (0, 1), (-1, 1), 6),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 6),
                ("ALIGN", (0, 1), (-1, 1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))
            story.append(t_din)
            story.append(Spacer(1, 1 * mm))

            # ── BLOQUES 6+7: DATOS MONITOREO | DATOS AFECTACIÓN ──
            WA, WB = 3.8 * cm, 5.1 * cm

            t_s3 = tabla_sec("3", "Datos de Monitoreo", [
                ("Código de Alerta:", cod_reporte),
                ("Período de Monitoreo:", f"{FECHA_INI_REPORTE} - {FECHA_FIN_REPORTE}"),
                ("Nivel de Confianza:", confianza),
                ("Coordenada Este (m):", f"{este:,.1f}" if este else "-"),
                ("Coordenada Norte (m):", f"{norte:,.1f}" if norte else "-"),
            ], WA, WB)

            t_s4 = tabla_sec("4", "Datos de Afectación", [
                ("Causa:", causa),
                ("Efecto:", "Pérdida de Hábitat"),
                ("Tipo de Bosque:", bosque),
                ("Superficie Afectada (ha):", f"{superficie:.2f}"),
                ("Código de Grilla:", grilla),
            ], WA, WB)

            t_34 = Table([[t_s3, t_s4]], colWidths=[WA + WB + 0.3 * cm, WA + WB + 0.3 * cm])
            t_34.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (1, 0), (1, 0), 3),
            ]))
            story.append(t_34)
            story.append(Spacer(1, 1 * mm))

            # ── BLOQUES 8+9: DATOS PRODUCCIÓN | DATOS ELABORACIÓN ─
            t_s5 = tabla_sec("5", "Datos de Producción", [
                ("Responsable:", editor),
                ("Cargo:", RESPONSABLE_CARGO),
                ("Fecha de emisión:", fecha_emision),
            ], WA, WB)

            t_s6 = tabla_sec_link("6", "Datos de Elaboración", [
                ("Metodología:", LINK_METODOLOGIA),
                ("Procedimiento:", LINK_PROCEDIMIENTO),
                ("Visualización:", URL_DASHBOARD_ACR),
            ], WA, WB)

            t_56 = Table([[t_s5, t_s6]], colWidths=[WA + WB + 0.3 * cm, WA + WB + 0.3 * cm])
            t_56.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (1, 0), (1, 0), 3),
            ]))
            story.append(t_56)
            story.append(Spacer(1, 1 * mm))

            # ── FOOTER: LOGOS ─────────────────────────────────────
            logo_gfp2 = img_rl(
                _get_logo_path(DIR_LOGOS, "logo_gfp", None, RK_LOGOS), 3.2 * cm, 1.15 * cm, "GFP"
            )
            logo_seco = img_rl(
                _get_logo_path(DIR_LOGOS, "logo_seco", None, RK_LOGOS),
                4.5 * cm, 1.15 * cm, "SECO",
            )
            logo_basel = img_rl(
                _get_logo_path(DIR_LOGOS, "logo_basel", None, RK_LOGOS),
                4.5 * cm, 1.15 * cm, "Basel",
            )

            t_footer = Table([[
                [_s("Con la asistencia", italic=True, tam=7, bold=True),
                 _s("técnica de:", italic=True, tam=7, bold=True)],
                logo_gfp2,
                logo_seco,
                logo_basel,
            ]], colWidths=[3.2 * cm, 3.8 * cm, 5.8 * cm, 5.8 * cm])
            t_footer.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("BOX", (0, 0), (-1, -1), 1.2, C_BORDE_EXT),
                ("LINEAFTER", (0, 0), (2, -1), 0.4, C_BORDE),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("BACKGROUND", (0, 0), (-1, -1), C_GRIS_F),
            ]))
            story.append(t_footer)

            doc.build(story)
            return pdf_path

        # ══════════════════════════════════════════════════════════
        # PASO 3 — EJECUTAR: MAPA + SENTINEL + PDF por alerta
        # (igual a Celda 6)
        # ══════════════════════════════════════════════════════════
        arcpy.AddMessage("="*65)
        arcpy.AddMessage(f"{REPORTE_TAG} {ANNO_REPORTE}  |  {FECHA_INI_REPORTE} -> {FECHA_FIN_REPORTE}")
        arcpy.AddMessage("="*65)
        arcpy.AddMessage(f"  Total alertas disponibles: {len(alertas_para_reporte)}")
        arcpy.AddMessage(f"  Procesando: {len(df_procesar)} alertas  |  PDFs en: {DIR_PDFS}")
        arcpy.AddMessage("="*65)

        pdfs_generados = []
        errores        = []
        inicio_total   = datetime.now()

        for idx, (i_row, alerta_row) in enumerate(df_procesar.iterrows()):
            oid     = alerta_row.get("objectid", idx)
            cod_acr = str(alerta_row.get("anp_codi", "??")).strip()
            nombre  = alerta_row.get("acr_nombre", cod_acr)
            causa   = alerta_row.get("causa_texto", "??")
            fecha   = alerta_row.get("md_fecimg", None)
            sup     = alerta_row.get("md_sup", 0) or 0

            arcpy.AddMessage(f"\n[{idx+1:02d}/{len(df_procesar)}] {cod_acr} | {nombre} | {causa} | {sup:.4f} ha")

            try:
                # 1. Mapa (omitido en modo estable)
                if USAR_MATPLOTLIB:
                    arcpy.AddMessage("  -> Mapa contextual...")
                else:
                    arcpy.AddMessage("  -> Mapa: omitido (modo estable)")
                mapa_path = generar_mapa_contextual(
                    i_row, acr_gdf, zi_gdf, idx, len(df_procesar))
                arcpy.AddMessage(f"  OK mapa: {os.path.basename(mapa_path) if mapa_path else 'no generado'}")

                # 2. Sentinel-2
                import pandas as pd
                img_antes = img_despues = None
                oid_img = resolver_oid_imagen(ALERTA_SEL, alerta_row) or oid
                pa, _ = buscar_imagen_local(
                    DIR_IMAGENES, "A", oid_img, ALERTA_SEL, regenerar_si_falta=True)
                pd_, _ = buscar_imagen_local(
                    DIR_IMAGENES, "D", oid_img, ALERTA_SEL, regenerar_si_falta=True)
                hay_local = bool(pa or pd_)
                if hay_local:
                    arcpy.AddMessage(
                        f"  -> Imagenes locales en imagenes_sentinel/ (OID imagen={oid_img})."
                    )
                else:
                    arcpy.AddWarning(
                        "  Sin PNG en imagenes_sentinel/. Ejecute H2, exporte ANTES/DESPUES "
                        "al mapa (Export HD) y verifique mensaje 'PNG guardado para H3'."
                    )
                if (not hay_local) and HAS_GEE and DESCARGAR_GEE and pd.notna(fecha):
                    fecha_ref = pd.to_datetime(fecha).strftime("%Y-%m-%d")
                    geom_alerta = alertas_para_reporte.loc[i_row].geometry
                    arcpy.AddMessage(
                        f"  -> S2 ANTES  (ventana {GEE_DIAS_BUSQUEDA}d, max {GEE_MAX_NUBES}% nubes)..."
                    )
                    img_antes = descargar_sentinel2(
                        geom_alerta, fecha_ref, tipo="antes",
                        dias=GEE_DIAS_BUSQUEDA, max_nubes=GEE_MAX_NUBES)
                    if img_antes:
                        arcpy.AddMessage(f"  OK Img A: {img_antes[2]} | {img_antes[3]}% nubes | ID: {str(img_antes[4])[-25:]}")
                    else:
                        arcpy.AddWarning("  AVISO: sin imagen A")

                    arcpy.AddMessage(
                        f"  -> S2 DESPUES (ventana {GEE_DIAS_BUSQUEDA}d desde {fecha_ref})..."
                    )
                    img_despues = descargar_sentinel2(
                        geom_alerta, fecha_ref, tipo="despues",
                        dias=GEE_DIAS_BUSQUEDA, max_nubes=GEE_MAX_NUBES)
                    if img_despues:
                        arcpy.AddMessage(f"  OK Img B: {img_despues[2]} | {img_despues[3]}% nubes | ID: {str(img_despues[4])[-25:]}")
                    else:
                        arcpy.AddWarning("  AVISO: sin imagen B")
                elif (not hay_local) and OMITIR_GEE:
                    arcpy.AddMessage(
                        "  AVISO: Sentinel-2 omitido (desmarca 'Descargar imagenes Sentinel-2')."
                    )
                elif (not hay_local) and (not HAS_GEE):
                    arcpy.AddWarning("  AVISO: GEE no disponible (autenticar o revisar proyecto).")
                elif not hay_local:
                    arcpy.AddWarning("  AVISO: alerta sin fecha de imagen (md_fecimg).")

                # 3. PDF
                arcpy.AddMessage("  -> Generando PDF...")
                pdf_path = generar_pdf_alerta(alerta_row, idx, mapa_path, img_antes, img_despues)
                pdfs_generados.append(pdf_path)
                arcpy.AddMessage(f"  OK PDF: {os.path.basename(pdf_path)}")

            except Exception as e:
                msg = f"ERROR {idx+1} OID={oid}: {e}"
                arcpy.AddWarning(f"  ERROR: {msg}")
                arcpy.AddWarning(traceback.format_exc())
                errores.append(msg)
            finally:
                if USAR_MATPLOTLIB:
                    try:
                        plt.close("all")
                    except Exception:
                        pass
                gc.collect()

        dur = (datetime.now() - inicio_total).total_seconds()
        arcpy.AddMessage(f"\n{'='*65}")
        arcpy.AddMessage(f"LISTO | PDFs: {len(pdfs_generados)} | Errores: {len(errores)} | {dur:.0f}s ({dur/60:.1f} min)")
        arcpy.AddMessage(f"Carpeta: {DIR_PDFS}")
        for pdf in pdfs_generados:
            arcpy.AddMessage(f"  -> {os.path.basename(pdf)}")
        if errores:
            for e in errores:
                arcpy.AddWarning(f"  ERROR: {e}")

        arcpy.AddMessage("="*65)
        arcpy.AddMessage(TEXTO_CIERRE)
        arcpy.AddMessage("="*65)

# -*- coding: utf-8 -*-
"""
Configuración regional compartida — ATD GFP Subnacional.
Usado por H1 (descargas), H2 (visor) y H3 (reporte PDF).
"""
import os
import re

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Dashboard GFP Subnacional (enlace Visualizacion en seccion 6 del PDF)
URL_DASHBOARD_ACR = "https://acr-dashboard-5iqz.onrender.com/"

DEFAULT_GDB_LORETO = os.path.join(
    _PROJECT_ROOT, "GDB", "Linea_base_deforestación_Loreto.gdb"
)
DEFAULT_GDB_CUZCO = os.path.join(
    _PROJECT_ROOT, "GDB", "Linea_base_deforestación_Cuzco.gdb"
)
DEFAULT_GDB_SM = os.path.join(
    _PROJECT_ROOT, "GDB", "Linea_base_deforestación_San_Martin.gdb"
)
DEFAULT_GDB_SM_CE = DEFAULT_GDB_SM
DEFAULT_GDB_SM_BOSHUMI = DEFAULT_GDB_SM
DEFAULT_ZEE_GDB_SM = os.path.join(
    _PROJECT_ROOT, "GDB", "Cartografia Basica ZEE SM - 13.10.2025_Final.gdb"
)
_GESTION_GDB_CANDIDATES_LORETO = [
    os.path.join(_PROJECT_ROOT, "GDB", "GestionACR_16012024.gdb"),
    os.path.join(_PROJECT_ROOT, "GDB", "Gestion_ACR_Loreto.gdb", "GestionACR_16012024.gdb"),
]
DEFAULT_GESTION_GDB_LORETO = next(
    (p for p in _GESTION_GDB_CANDIDATES_LORETO if os.path.isdir(p)),
    _GESTION_GDB_CANDIDATES_LORETO[0],
)

REGION_CONFIGS = {
    "loreto": {
        "region": "Loreto",
        "departamento": "Loreto",
        "gobierno": "GOBIERNO REGIONAL DE LORETO",
        "reporte_tag": "ATD LORETO",
        "cierre": "Reporte ATD v7 - GFP Subnacional | GRRNGA Loreto",
        "gerencia": "GERENCIA REGIONAL DE RECURSOS NATURALES Y GESTIÓN AMBIENTAL",
        "subgerencia": "SUB GERENCIA DE CONSERVACIÓN Y DIVERSIDAD BIOLÓGICA",
        "logo_region": "loreto",
        "gestion_gdb": DEFAULT_GESTION_GDB_LORETO,
        "fc_alertas_prioridad": [
            "MonitoreoDeforestacion",
            "MonitoreoDeforestacionAcumulado",
        ],
        "anp_codi_aliases": {},
        "acr_nomb_to_codi": {
            "Ampiyacu Apayacu": "ACR09",
            "ACR Ampiyacu Apayacu": "ACR09",
            "Comunal Tamshiyacu Tahuayo": "ACR04",
            "ACR Comunal Tamshiyacu Tahuayo": "ACR04",
            "Maijuna Kichwa": "ACR17",
            "ACR Maijuna Kichwa": "ACR17",
            "Alto Nanay- Pintuyacu Chambira": "ACR10",
            "Alto Nanay-Pintuyacu Chambira": "ACR10",
            "Alto Nanay Pintuyacu Chambira": "ACR10",
            "Alto Nanay Pintuyacu": "ACR10",
            "ACR Alto Nanay Pintuyacu": "ACR10",
            "ACR Alto Nanay Pintuyacu Chambira": "ACR10",
        },
        "acr_nombres": {
            "ACR09": "ACR Ampiyacu Apayacu",
            "ACR04": "ACR Comunal Tamshiyacu Tahuayo",
            "ACR17": "ACR Maijuna Kichwa",
            "ACR10": "ACR Alto Nanay Pintuyacu Chambira",
        },
        "acr_siglas": {
            "ACR09": "AA", "ACR04": "CTT", "ACR17": "MK", "ACR10": "ANPCH",
        },
        "acr_geo": {
            "ACR09": {"provincia": "Mariscal Ramon Castilla / Loreto", "distrito": "Ramon Castilla / Pebas"},
            "ACR04": {"provincia": "Loreto / Requena", "distrito": "Parinari / Sapuena"},
            "ACR17": {"provincia": "Putumayo / Maynas", "distrito": "Putumayo / Mazan"},
            "ACR10": {"provincia": "Maynas", "distrito": "Alto Nanay"},
        },
        "zi_codi_to_acr": {
            "ZI ANPCH": "ACR10", "ZI CTT": "ACR04", "ZI MK": "ACR17", "ZI AA": "ACR09",
            "ANPCH": "ACR10", "CTT": "ACR04", "MK": "ACR17", "AA": "ACR09",
        },
        "h1": {
            "fc_anp": "gpo_anp_monit",
            "fc_zonif": "gpo_zonif_anp",
            "fc_exa": "gpo_exa",
            "campo_cod": ["acr_codi", "anp_codi", "cod_acr", "codigo", "cod", "CODOBJ"],
            "campo_nom": ["acr_nomb", "anp_nomb", "ANP_NOM", "nombre", "nomobj", "name"],
            "campo_tipo": ["Influen", "TipZona", "tipo", "anp_clase"],
            "exa_campos": ["columna_fi", "col_fi", "cod_grilla", "g_cofi", "g_grilla", "codigo"],
            "zonif_campos": ["tz_nomb", "zacr_nomb", "tipo_zoni", "z_tipo", "z_sect", "nombre", "nom"],
        },
    },
    "cuzco": {
        "region": "Cuzco",
        "departamento": "Cusco",
        "gobierno": "GOBIERNO REGIONAL DE CUSCO",
        "reporte_tag": "ATD CUZCO",
        "cierre": "Reporte ATD v7 - GFP Subnacional | GORE Cusco",
        "gerencia": "GERENCIA REGIONAL DE DESARROLLO ECONÓMICO",
        "subgerencia": "DIRECCIÓN DE GESTIÓN AMBIENTAL",
        "logo_region": "cuzco",
        "gestion_gdb": None,
        "fc_alertas_prioridad": ["MonitoreoDeforestacionAcumulado"],
        "anp_codi_aliases": {},
        "acr_nomb_to_codi": {
            "Choquequirao": "ACR07",
            "ACR Choquequirao": "ACR07",
            "Area de Conservacion Regional Choquequirao": "ACR07",
            "Chuyapi Urusayhua": "ACR26",
            "ACR Chuyapi Urusayhua": "ACR26",
            "Area de Conservacion Regional Chuyapi Urusayhua": "ACR26",
            "Q'eros Kosñipata": "ACR30",
            "Q'eros Kosnipata": "ACR30",
            "Qeros Kosnipata": "ACR30",
            "ACR Q'eros Kosñipata": "ACR30",
            "ACR Q'eros Kosnipata": "ACR30",
            "Area de Conservacion Regional Q'eros Kosñipata": "ACR30",
            "Area de Conservacion Regional Q'eros Kosnipata": "ACR30",
        },
        "acr_nombres": {
            "ACR07": "ACR Choquequirao",
            "ACR26": "ACR Chuyapi Urusayhua",
            "ACR30": "ACR Q'eros Kosñipata",
        },
        "acr_siglas": {
            "ACR07": "CHQ", "ACR26": "CU", "ACR30": "QK",
        },
        "acr_geo": {
            "ACR07": {"provincia": "Anta / La Convencion", "distrito": "Mollepata / Santa Teresa"},
            "ACR26": {"provincia": "La Convencion", "distrito": "-"},
            "ACR30": {"provincia": "Paucartambo", "distrito": "Kosñipata"},
        },
        "zi_codi_to_acr": {
            "ZI CHQ": "ACR07", "ZI CU": "ACR26", "ZI QK": "ACR30",
            "CHQ": "ACR07", "CU": "ACR26", "QK": "ACR30",
            "ZI ACR07": "ACR07", "ZI ACR26": "ACR26", "ZI ACR30": "ACR30",
        },
        "h1": {
            "fc_anp": "gpo_anp_monit",
            "fc_zonif": "gpo_zonif_anp",
            "fc_exa": "gpo_exa",
            "campo_cod": ["anp_codi", "acr_codi", "cod_acr", "codigo", "cod", "CODOBJ"],
            "campo_nom": ["anp_nomb", "acr_nomb", "ANP_NOM", "nombre", "nomobj", "name"],
            "campo_tipo": ["anp_clase", "Influen", "TipZona", "tipo"],
            "exa_campos": ["g_cofi", "g_grilla", "columna_fi", "col_fi", "cod_grilla", "codigo"],
            "zonif_campos": ["z_tipo", "z_sect", "tz_nomb", "zacr_nomb", "tipo_zoni", "nombre", "nom"],
        },
    },
    "san_martin": {
        "region": "San Martin",
        "departamento": "San Martin",
        "gobierno": "GOBIERNO REGIONAL DE SAN MARTIN",
        "reporte_tag": "ATD SAN MARTIN",
        "cierre": "Reporte ATD v7 - GFP Subnacional | GORE San Martin",
        "gerencia": "GERENCIA REGIONAL DE RECURSOS NATURALES Y GESTIÓN AMBIENTAL",
        "subgerencia": "SUB GERENCIA DE CONSERVACIÓN Y DIVERSIDAD BIOLÓGICA",
        "logo_region": "san_martin",
        "gestion_gdb": None,
        "zee_gdb": DEFAULT_ZEE_GDB_SM,
        "fc_alertas_prioridad": [
            "MonitoreoDeforestacion",
            "MonitoreoDeforestacionAcumulado",
        ],
        "anp_codi_aliases": {
            "ACR BOSQUES DE SHUNTE Y MISHOLLO": "ACR21",
            "ACR BOSQUES DE SHUNTÉ Y MISHOLLO": "ACR21",
        },
        "acr_nomb_to_codi": {
            "Cordillera Escalera": "ACR01",
            "ACR Cordillera Escalera": "ACR01",
            "Area de Conservacion Regional Cordillera Escalera": "ACR01",
            "Bosques de Shunte y Mishollo": "ACR21",
            "Bosques de Shunté y Mishollo": "ACR21",
            "ACR Bosques de Shunte y Mishollo": "ACR21",
            "ACR Bosques de Shunté y Mishollo": "ACR21",
        },
        "acr_nombres": {
            "ACR01": "ACR Cordillera Escalera",
            "ACR21": "ACR Bosques de Shunté y Mishollo",
        },
        "acr_siglas": {
            "ACR01": "CE", "ACR21": "BOSHUMI",
        },
        "acr_geo": {
            "ACR01": {"provincia": "San Martin / Rioja / Picota", "distrito": "Segun sector ACR"},
            "ACR21": {"provincia": "Mariscal Caceres", "distrito": "Huicungo / Pachiza"},
        },
        "zi_codi_to_acr": {
            "ZI CE": "ACR01", "CE": "ACR01",
            "ZI BOSHUMI": "ACR21", "BOSHUMI": "ACR21",
        },
        "h1": {
            "fc_anp": "gpo_anp_monit",
            "fc_zonif": "gpo_zonif_anp",
            "fc_exa": "gpo_exa",
            "campo_cod": ["anp_codi", "acr_codi", "cod_acr", "codigo", "cod", "CODOBJ"],
            "campo_nom": ["anp_nomb", "acr_nomb", "ANP_NOM", "nombre", "nomobj", "name"],
            "campo_tipo": ["anp_clase", "Influen", "TipZona", "tipo"],
            "exa_campos": ["g_cofi", "g_grilla", "columna_fi", "col_fi", "cod_grilla", "codigo"],
            "zonif_campos": ["z_tipo", "z_sect", "tz_nomb", "zacr_nomb", "tipo_zoni", "nombre", "nom"],
        },
    },
}

_REGION_ACTIVA = None
_LAST_GDB_PATH = ""
ACR_NOMB_TO_CODI = {}
ACR_NOMBRES = {}
ACR_SIGLAS = {}
ACR_GEO = {}
ZI_CODI_TO_ACR = {}
SIGLA_TO_ACR = {}
ACR_CODIGOS_FC = []
ANP_CODI_ALIASES = {}
REGION_NOMBRE = ""
DEPARTAMENTO_REPORTE = ""
GOBIERNO_REGIONAL = ""
GERENCIA_REGIONAL = ""
SUBGERENCIA_REGIONAL = ""
LOGO_REGION_KEY = ""
REPORTE_TAG = ""
TEXTO_CIERRE = ""
GESTION_GDB_ACTIVA = None
FC_ALERTAS_PRIORIDAD = []


def _mutate_dict(dest, src):
    """Actualiza dict in-place para que `from m import X` siga vigente."""
    dest.clear()
    dest.update(src or {})


def _mutate_list(dest, src):
    dest[:] = list(src or [])


def _acr_catalogo_para_gdb(gdb_path, cfg):
    """San Martin: una GDB por ACR (CE o BOSHUMI); otras regiones: catálogo completo."""
    nombres = dict(cfg.get("acr_nombres", {}))
    s = os.path.basename(str(gdb_path or "")).lower()
    if "boshumi" in s or "shunt" in s or "misholl" in s:
        filtrado = {k: v for k, v in nombres.items() if k == "ACR21"}
        return filtrado or nombres
    if "ce.gdb" in s or ("_ce" in s and "acr" in s) or "escalera" in s:
        filtrado = {k: v for k, v in nombres.items() if k == "ACR01"}
        return filtrado or nombres
    return nombres


def acr_opciones_filtro():
    """Opciones para el desplegable 'Area de conservacion' en H3."""
    return ["TODAS"] + sorted(ACR_NOMBRES.keys())


def _catalogo_nombres_acr(cfg, acr_nombres_activos):
    """
    Alias nombre -> codigo para la region activa (Loreto / Cuzco / San Martin).
    Genera variantes con y sin prefijo 'ACR' desde el catalogo oficial.
    """
    mapping = dict(cfg.get("acr_nomb_to_codi", {}))
    for cod, etiqueta in (acr_nombres_activos or {}).items():
        if not etiqueta:
            continue
        et = str(etiqueta).strip()
        rest = _sin_prefijo_acr(et)
        for variant in {et, rest, f"ACR {rest}" if rest else ""}:
            if variant:
                mapping.setdefault(variant, cod)
    return mapping


def _detectar_region(gdb_path=None):
    s = os.path.basename(str(gdb_path or "")).lower()
    parent = os.path.basename(os.path.dirname(str(gdb_path or ""))).lower()
    combo = f"{parent} {s}"
    if "boshumi" in combo or "shunt" in combo or "misholl" in combo:
        return "san_martin"
    if (
        "ce.gdb" in s
        or ("_ce" in s and "acr" in s)
        or "escalera" in combo
        or "monitoreodeforestacionacumulado_ce" in combo
        or "monitoreodeforestacionacumulado_boshumi" in combo
    ):
        return "san_martin"
    if "san martin" in combo or "sanmartin" in combo or "san_martin" in combo:
        return "san_martin"
    if "cuzco" in combo or "cusco" in combo:
        return "cuzco"
    if "loreto" in combo:
        return "loreto"
    return "loreto"


def _utm_epsg_region(region_key=None):
    if (region_key or _REGION_ACTIVA) == "cuzco":
        return 32719
    return 32718


def configurar_region(gdb_path=None, force=False):
    global _REGION_ACTIVA, _LAST_GDB_PATH
    global REGION_NOMBRE, DEPARTAMENTO_REPORTE, GOBIERNO_REGIONAL
    global GERENCIA_REGIONAL, SUBGERENCIA_REGIONAL, LOGO_REGION_KEY
    global REPORTE_TAG, TEXTO_CIERRE, GESTION_GDB_ACTIVA

    key = _detectar_region(gdb_path)
    gdb_norm = ""
    if gdb_path and os.path.isdir(str(gdb_path)):
        gdb_norm = os.path.normcase(os.path.abspath(str(gdb_path)))

    if (
        not force
        and _REGION_ACTIVA == key
        and _LAST_GDB_PATH == gdb_norm
        and gdb_norm
    ):
        return REGION_CONFIGS[key]

    cfg = REGION_CONFIGS[key]
    _REGION_ACTIVA = key
    _LAST_GDB_PATH = gdb_norm

    acr_nombres = _acr_catalogo_para_gdb(gdb_path, cfg)
    acr_siglas = {
        k: cfg["acr_siglas"][k]
        for k in acr_nombres
        if k in cfg.get("acr_siglas", {})
    }
    acr_geo = {
        k: cfg["acr_geo"][k]
        for k in acr_nombres
        if k in cfg.get("acr_geo", {})
    }

    _mutate_dict(ACR_NOMB_TO_CODI, _catalogo_nombres_acr(cfg, acr_nombres))
    _mutate_dict(ACR_NOMBRES, acr_nombres)
    _mutate_dict(ACR_SIGLAS, acr_siglas)
    _mutate_dict(ACR_GEO, acr_geo)
    _mutate_dict(ZI_CODI_TO_ACR, cfg["zi_codi_to_acr"])
    _mutate_dict(SIGLA_TO_ACR, {v: k for k, v in acr_siglas.items()})
    _mutate_list(ACR_CODIGOS_FC, acr_nombres.keys())
    _mutate_dict(ANP_CODI_ALIASES, cfg.get("anp_codi_aliases", {}))

    REGION_NOMBRE = cfg["region"]
    DEPARTAMENTO_REPORTE = cfg["departamento"]
    GOBIERNO_REGIONAL = cfg["gobierno"]
    GERENCIA_REGIONAL = cfg.get("gerencia", "")
    SUBGERENCIA_REGIONAL = cfg.get("subgerencia", "")
    LOGO_REGION_KEY = cfg.get("logo_region", key)
    REPORTE_TAG = cfg["reporte_tag"]
    TEXTO_CIERRE = cfg["cierre"]
    GESTION_GDB_ACTIVA = cfg.get("gestion_gdb")
    _mutate_list(
        FC_ALERTAS_PRIORIDAD,
        _fc_alertas_prioridad_para_gdb(gdb_path, cfg.get("fc_alertas_prioridad", [])),
    )
    return cfg


def sincronizar_imports_region(globals_dict):
    """
    Re-sincroniza escalares importados con `from atd_region_config import ...`
    en el modulo que llama (p. ej. toolbox .pyt).
    Los dict/list se actualizan solos via _mutate_*.
    """
    import sys

    mod = sys.modules[__name__]
    for name in (
        "REGION_NOMBRE", "DEPARTAMENTO_REPORTE", "GOBIERNO_REGIONAL",
        "GERENCIA_REGIONAL", "SUBGERENCIA_REGIONAL", "LOGO_REGION_KEY",
        "REPORTE_TAG", "TEXTO_CIERRE", "GESTION_GDB_ACTIVA", "_REGION_ACTIVA",
    ):
        if name in globals_dict:
            globals_dict[name] = getattr(mod, name)


def _fc_alertas_prioridad_para_gdb(gdb_path, default_list):
    s = os.path.basename(str(gdb_path or "")).lower()
    if "linea_base_deforestación_san_martin" in s or "gdb_monit_template_acr_san_martin" in s:
        return [
            "MonitoreoDeforestacion",
            "MonitoreoDeforestacionAcumulado",
        ]
    if "boshumi" in s or "shunt" in s:
        return [
            "MonitoreoDeforestacionAcumulado_BOSHUMI",
            "MonitoreoDeforestacionAcumulado",
        ]
    if "ce.gdb" in s or "cordillera" in s or "_ce" in s or "escalera" in s:
        return [
            "MonitoreoDeforestacionAcumulado_CE",
            "MonitoreoDeforestacionAcumulado",
        ]
    return default_list


def normalizar_cod_acr(cod):
    s = re.sub(r"\s+", "", str(cod or "").strip().upper())
    if not s:
        return ""
    if s.startswith("ACR"):
        num = re.sub(r"^ACR", "", s)
        if num.isdigit():
            return f"ACR{int(num):02d}" if len(num) <= 2 else f"ACR{num}"
    return s


def _sin_prefijo_acr(texto):
    return re.sub(r"^ACR\s*", "", str(texto or "").strip(), flags=re.I).strip()


def normalizar_anp_codi(cod):
    c = str(cod or "").strip()
    if not c:
        return ""
    u = c.upper()
    if u in ACR_NOMBRES:
        return u
    if u in ZI_CODI_TO_ACR:
        return ZI_CODI_TO_ACR[u]
    alias = ANP_CODI_ALIASES.get(u)
    if alias:
        return alias
    n = normalizar_cod_acr(c)
    if n in ACR_NOMBRES:
        return n
    if c in ACR_NOMB_TO_CODI:
        return ACR_NOMB_TO_CODI[c]
    rest = _sin_prefijo_acr(c)
    if rest in ACR_NOMB_TO_CODI:
        return ACR_NOMB_TO_CODI[rest]
    c_low, rest_low = c.lower(), rest.lower()
    for nom, codi in ACR_NOMB_TO_CODI.items():
        nl = nom.lower()
        if c_low == nl or rest_low == nl:
            return codi
    for codigo, etiqueta in ACR_NOMBRES.items():
        et = _sin_prefijo_acr(etiqueta).lower()
        if c_low == etiqueta.lower() or rest_low == et or rest_low in et or et in rest_low:
            return codigo
    return c


def valor_anp_desde_registro(rec):
    """Lee codigo/nombre ACR desde distintos nombres de campo del FC de alertas."""
    if not rec:
        return ""
    candidatos = (
        "anp_codi", "ANP_CODI", "acr_codi", "ACR_CODI",
        "Codigo_ANP", "codigo_anp", "COD_ANP", "CODACR",
    )
    for k in candidatos:
        v = rec.get(k)
        if v is not None and str(v).strip():
            return v
    for k, v in rec.items():
        if v is None or not str(v).strip():
            continue
        kn = (
            str(k).lower()
            .replace("ó", "o").replace("í", "i").replace("é", "e").replace("ú", "u")
        )
        if ("cod" in kn and "anp" in kn) or kn in ("codigo anp", "cod_anp"):
            return v
    for nk in ("ac_nomb", "acr_nomb", "anp_nomb", "ANP_NOM", "nombre"):
        v = rec.get(nk)
        if v is not None and str(v).strip():
            return v
    for zk in ("zi_codi", "ZI_CODI"):
        v = rec.get(zk)
        if v is not None and str(v).strip():
            return v
    return rec.get("anp_codi") or ""


def gdb_absoluta_si_existe(gdb_path):
    """Ruta .gdb absoluta si el directorio existe."""
    if not gdb_path:
        return None
    p = os.path.abspath(os.path.normpath(str(gdb_path)))
    return p if os.path.isdir(p) else None


def h1_config_activa():
    """Parametros por defecto de H1 para la region activa."""
    key = _REGION_ACTIVA or "loreto"
    return dict(REGION_CONFIGS.get(key, {}).get("h1", {}))


def _first_field_match(campos_list, candidatos):
    """Primer candidato presente en la lista de campos del FC."""
    if not campos_list:
        return None
    lower = {str(c).lower(): c for c in campos_list}
    for cand in candidatos or []:
        if cand in campos_list:
            return cand
        lc = str(cand).lower()
        if lc in lower:
            return lower[lc]
    return campos_list[0]


def resolver_campo_h1(fc_path, candidatos, campos_list=None):
    """Resuelve nombre de campo en un FC segun candidatos regionales."""
    if campos_list is None:
        try:
            import arcpy
            if not arcpy.Exists(fc_path):
                return None
            campos_list = [
                f.name for f in arcpy.ListFields(fc_path)
                if f.type not in ("OID", "Geometry", "GlobalID")
            ]
        except Exception:
            return None
    return _first_field_match(campos_list, candidatos)


def resolver_fc_h1(gdb_path, fcs, clave):
    """Elige FC de H1 (anp/zonif/exa) segun config regional y contenido GDB."""
    h1 = h1_config_activa()
    preferido = h1.get(clave)
    if preferido and preferido in fcs:
        return preferido
    defaults = {
        "fc_anp": ("gpo_anp_monit",),
        "fc_zonif": ("gpo_zonif_anp",),
        "fc_exa": ("gpo_exa",),
    }
    for cand in defaults.get(clave, ()):
        if cand in fcs:
            return cand
    return fcs[0] if fcs else preferido


def es_zi_area(cod, tipo_val=None):
    """True si el registro corresponde a Zona de Influencia (ZI)."""
    cod_up = str(cod or "").strip().upper()
    if cod_up.startswith("ZI"):
        return True
    if "INFLUENCIA" in cod_up:
        return True
    tv = str(tipo_val or "").strip().lower()
    if tv and "influen" in tv:
        return True
    if tv in ("zi", "zona de influencia", "zona influencia"):
        return True
    return False


def resolver_fc_alertas(gdb_path, fcs=None):
    configurar_region(gdb_path)
    if fcs is None:
        try:
            import arcpy
            arcpy.env.workspace = gdb_path
            fcs = sorted(arcpy.ListFeatureClasses() or [])
        except Exception:
            fcs = []
    for cand in FC_ALERTAS_PRIORIDAD:
        if cand in fcs:
            return cand
    for cand in ("MonitoreoDeforestacion", "MonitoreoDeforestacionAcumulado"):
        if cand in fcs:
            return cand
    return fcs[0] if fcs else "MonitoreoDeforestacion"


def _first_existing_column(df, candidatos):
    lower = {str(c).lower(): c for c in df.columns}
    for cand in candidatos:
        if cand in df.columns:
            return cand
        if str(cand).lower() in lower:
            return lower[str(cand).lower()]
    return None


def _valor_util(val):
    if val is None:
        return None
    s = str(val).strip()
    if not s or s in ("-", " ", "Ver Plan Maestro en archivos digitales"):
        return None
    return s


def _sector_desde_zonif(geom, zonif_gdf, cod_acr):
    import geopandas as gpd

    if zonif_gdf is None or len(zonif_gdf) == 0:
        return None
    sec_col = _first_existing_column(
        zonif_gdf, ["z_sect", "zacr_sect", "sector", "SECTOR"]
    )
    if not sec_col:
        return None
    cod_col = _first_existing_column(
        zonif_gdf, ["acr_codi", "anp_codi", "CODACR"]
    )
    zf = zonif_gdf
    if cod_col:
        cod_norm = normalizar_cod_acr(cod_acr)
        mask = zf[cod_col].apply(
            lambda v: normalizar_cod_acr(v) == cod_norm
            or str(v).strip().upper() == str(cod_acr).strip().upper()
        )
        sub = zf[mask]
        if len(sub):
            zf = sub
    pt = gpd.GeoDataFrame(geometry=[geom.centroid], crs=zf.crs)
    joined = gpd.sjoin(pt, zf, how="left", predicate="within")
    if joined.empty:
        joined = gpd.sjoin(pt, zf, how="left", predicate="intersects")
    if joined.empty:
        return None
    val = joined.iloc[0][sec_col]
    return _valor_util(val)


def _cargar_cvc_gestion(gdb_gestion):
    import geopandas as gpd

    if not gdb_gestion or not os.path.isdir(gdb_gestion):
        return None
    try:
        gdf = gpd.read_file(gdb_gestion, layer="CenVigComPunto")
    except Exception:
        return None
    if gdf.empty:
        return None
    col = _first_existing_column(gdf, ["CODACR", "codacr", "acr_codi"])
    if col:
        gdf["_cod_acr"] = gdf[col].apply(normalizar_cod_acr)
    else:
        gdf["_cod_acr"] = ""
    return gdf


def _cargar_cenpoblado_zee(zee_gdb):
    import geopandas as gpd

    if not zee_gdb or not os.path.isdir(zee_gdb):
        return None
    for layer in (
        "CartografiaBasica/CenPoblado",
        "CenPoblado",
    ):
        try:
            gdf = gpd.read_file(zee_gdb, layer=layer)
            if not gdf.empty:
                return gdf
        except Exception:
            continue
    return None


def _cenpoblado_cercano(geom, cp_gdf):
    if cp_gdf is None or cp_gdf.empty:
        return None, None
    pt = geom.centroid
    try:
        idx = cp_gdf.geometry.distance(pt).idxmin()
    except Exception:
        return None, None
    row = cp_gdf.loc[idx]
    lp = _valor_util(row.get("NOMBCP")) or _valor_util(row.get("nombcp"))
    fun = str(row.get("FUNADM") or row.get("funadm") or "").upper()
    cat = str(row.get("CATGCP") or row.get("catgcp") or "").upper()
    olv = lp
    if lp and ("VIGIL" in fun or "CV" in cat or "CONTROL" in fun):
        olv = f"Centro de vigilancia {lp}"
    elif lp:
        olv = f"Puesto de control cercano a {lp}"
    return lp, olv


def _cvc_cercano(geom, cvc_gdf, cod_acr):
    if cvc_gdf is None or cvc_gdf.empty:
        return None, None
    cod_norm = normalizar_cod_acr(cod_acr)
    sub = cvc_gdf[cvc_gdf["_cod_acr"] == cod_norm]
    if sub.empty:
        sub = cvc_gdf
    pt = geom.centroid
    try:
        idx = sub.geometry.distance(pt).idxmin()
    except Exception:
        return None, None
    row = sub.loc[idx]
    lp = _valor_util(row.get("DENOMI")) or _valor_util(row.get("NOMENT"))
    olv = _valor_util(row.get("NOMENT")) or _valor_util(row.get("DENOMI"))
    if olv and lp and olv == lp:
        olv = f"Centro de Vigilancia Comunal {lp}"
    return lp, olv


def extraer_ubicacion_alerta(geom, cod_acr, zonif_gdf=None, gdb_gestion=None, region_key=None):
    """
    Extrae lugar poblado cercano, sector y OLV para una alerta.
    Loreto: GDB gestión (CenVigComPunto) + zonificación línea base.
    Otras regiones: sector desde gpo_zonif_anp si existe.
    """
    region_key = region_key or _REGION_ACTIVA or _detectar_region()
    out = {"lugar_poblado": "-", "sector": "-", "olv_cercano": "-"}

    sector = _sector_desde_zonif(geom, zonif_gdf, cod_acr)
    if sector:
        out["sector"] = sector

    gdb_g = gdb_gestion or GESTION_GDB_ACTIVA
    if region_key == "loreto" and gdb_g and os.path.isdir(gdb_g):
        cvc = _cargar_cvc_gestion(gdb_g)
        lp, olv = _cvc_cercano(geom, cvc, cod_acr)
        if lp:
            out["lugar_poblado"] = lp
        if olv:
            out["olv_cercano"] = olv
    elif region_key == "san_martin":
        zee = DEFAULT_ZEE_GDB_SM
        cp = _cargar_cenpoblado_zee(zee)
        lp, olv = _cenpoblado_cercano(geom, cp)
        if lp:
            out["lugar_poblado"] = lp
        if olv:
            out["olv_cercano"] = olv

    return out


def enriquecer_ubicacion_alertas(df, zonif_gdf=None, gdb_gestion=None, region_key=None):
    """
    Añade lugar_poblado, sector_reporte, olv_cercano.
    Join espacial por lotes (evita miles de sjoin en bucle que congela/cierra ArcGIS Pro).
    """
    import geopandas as gpd

    region_key = region_key or _REGION_ACTIVA
    out = df.copy()
    out["lugar_poblado"] = "-"
    out["sector_reporte"] = "-"
    out["olv_cercano"] = "-"

    if out.empty or out.geometry is None:
        return out

    try:
        pts = out[["geometry"]].copy()
        pts["geometry"] = pts.geometry.centroid
        if zonif_gdf is not None and getattr(zonif_gdf, "crs", None):
            pts = pts.to_crs(zonif_gdf.crs)
        elif pts.crs is None:
            pts = pts.set_crs(epsg=32718)
        pts["_cod_norm"] = out["anp_codi"].apply(normalizar_anp_codi)

        if zonif_gdf is not None and len(zonif_gdf):
            sec_col = _first_existing_column(
                zonif_gdf, ["z_sect", "zacr_sect", "sector", "SECTOR"]
            )
            if sec_col:
                zf = zonif_gdf[[sec_col, "geometry"]].copy()
                try:
                    j = gpd.sjoin(pts, zf, how="left", predicate="intersects")
                    if not j.empty:
                        j = j[~j.index.duplicated(keep="first")]
                        for pt_ix, row in j.iterrows():
                            sec = _valor_util(row.get(sec_col))
                            if sec:
                                out.at[pt_ix, "sector_reporte"] = sec
                except Exception:
                    pass

        if region_key == "loreto":
            gdb_g = gdb_gestion or GESTION_GDB_ACTIVA
            cvc = _cargar_cvc_gestion(gdb_g)
            if cvc is not None and not cvc.empty:
                cvc = cvc.to_crs(pts.crs)
                denom_col = _first_existing_column(cvc, ["DENOMI"]) or "DENOMI"
                nom_col = _first_existing_column(cvc, ["NOMENT"]) or "NOMENT"
                try:
                    j2 = gpd.sjoin_nearest(
                        pts, cvc, how="left", max_distance=250_000
                    )
                    if not j2.empty:
                        j2 = j2[~j2.index.duplicated(keep="first")]
                        for pt_ix, row in j2.iterrows():
                            lp = _valor_util(row.get(denom_col)) or _valor_util(
                                row.get(nom_col)
                            )
                            olv = _valor_util(row.get(nom_col)) or _valor_util(
                                row.get(denom_col)
                            )
                            if olv and lp and olv == lp:
                                olv = f"Centro de Vigilancia Comunal {lp}"
                            if lp:
                                out.at[pt_ix, "lugar_poblado"] = lp
                            if olv:
                                out.at[pt_ix, "olv_cercano"] = olv
                except Exception:
                    for pt_ix, row in pts.iterrows():
                        lp_v, olv_v = _cvc_cercano(
                            row.geometry, cvc, row["_cod_norm"]
                        )
                        if lp_v:
                            out.at[pt_ix, "lugar_poblado"] = lp_v
                        if olv_v:
                            out.at[pt_ix, "olv_cercano"] = olv_v
        elif region_key == "san_martin":
            cp = _cargar_cenpoblado_zee(DEFAULT_ZEE_GDB_SM)
            if cp is not None and not cp.empty:
                cp = cp.to_crs(pts.crs)
                nom_col = _first_existing_column(cp, ["NOMBCP"]) or "NOMBCP"
                fun_col = _first_existing_column(cp, ["FUNADM"]) or "FUNADM"
                try:
                    j3 = gpd.sjoin_nearest(pts, cp, how="left", max_distance=250_000)
                    if not j3.empty:
                        j3 = j3[~j3.index.duplicated(keep="first")]
                        for pt_ix, row in j3.iterrows():
                            lp = _valor_util(row.get(nom_col))
                            fun = str(row.get(fun_col) or "").upper()
                            olv = lp
                            if lp and ("VIGIL" in fun or "CONTROL" in fun):
                                olv = f"Centro de vigilancia {lp}"
                            elif lp:
                                olv = f"Puesto de control cercano a {lp}"
                            if lp:
                                out.at[pt_ix, "lugar_poblado"] = lp
                            if olv:
                                out.at[pt_ix, "olv_cercano"] = olv
                except Exception:
                    for pt_ix, row in pts.iterrows():
                        lp_v, olv_v = _cenpoblado_cercano(row.geometry, cp)
                        if lp_v:
                            out.at[pt_ix, "lugar_poblado"] = lp_v
                        if olv_v:
                            out.at[pt_ix, "olv_cercano"] = olv_v
    except Exception:
        pass

    return out


try:
    configurar_region(DEFAULT_GDB_LORETO, force=True)
except Exception:
    pass

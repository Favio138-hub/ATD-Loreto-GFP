# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════════
ATD TOOLBOX — HERRAMIENTA 1
Descarga alertas Geobosques e inserta en MonitoreoDeforestacion (vigente)
GFP Subnacional - Loreto / Cuzco / San Martin | https://www.gfpsubnacional.pe/
Agrega rango de fechas (inicio/fin) al periodo monitoreado
═══════════════════════════════════════════════════════════════════════════════

CAMBIOS:
  - Parametros GPDate: "Fecha inicio del periodo" y "Fecha fin del periodo"
  - Auto-rellena las fechas al cambiar el año (01/01/año — 31/12/año)
  - Guarda md_fecini y md_fecfin en cada registro (si los campos existen)
  - Indices de parametros actualizados en updateParameters y execute
═══════════════════════════════════════════════════════════════════════════════
"""

import arcpy
import os
import sys
import traceback
import tempfile
import zipfile
import urllib.request
import uuid
import struct
from datetime import datetime as dt, date, timedelta

_toolbox_dir = os.path.dirname(os.path.abspath(__file__))
if _toolbox_dir not in sys.path:
    sys.path.insert(0, _toolbox_dir)
from atd_region_config import (
    configurar_region,
    sincronizar_imports_region,
    resolver_fc_alertas,
    gdb_absoluta_si_existe,
    h1_config_activa,
    resolver_campo_h1,
    resolver_fc_h1,
    es_zi_area,
    REGION_NOMBRE,
    REGION_CONFIGS,
    _REGION_ACTIVA,
)


# ─── URL BASE GEOBOSQUES (interna, no expuesta al usuario) ────────────────────
_URL_BASE = (
    "http://geobosques.minam.gob.pe/geobosque/descargas_geobosque/"
    "alerta/espaciales/Alertas_PNCB_raster_{anno}.zip"
)

ANOS_DISPONIBLES = ["2026", "2025", "2024", "2023", "2022", "2021", "2020"]


# ══════════════════════════════════════════════════════════════════════
# TOOLBOX
# ══════════════════════════════════════════════════════════════════════

class Toolbox(object):
    def __init__(self):
        self.label       = (
            "Geo Herramienta 1 — Descarga automatizada de "
            "Alertas Tempranas de Deforestación"
        )
        self.alias       = "ATD_H1_InsertarAlertas"
        self.description = (
            "ATD TOOLBOX H1 — GFP Subnacional Loreto/Cuzco/San Martin v5.3\n\n"
            "Descarga alertas Geobosques del año seleccionado y las\n"
            "inserta en el FC existente MonitoreoDeforestacion (vigente).\n\n"
            "El historico 2001-2025 permanece en MonitoreoDeforestacionAcumulado.\n\n"
            "NUEVO v5.1: Rango de fechas (inicio/fin) del periodo monitoreado.\n"
            "Las fechas se guardan en md_fecini / md_fecfin si existen.\n\n"
            "Procesa ACRs (anp_codi) y Zonas de Influencia (zona_influencia).\n"
            "zi_codi permanece vacio; la ZI va en zona_influencia.\n\n"
            "Si ya existen registros del año seleccionado en el FC,\n"
            "los elimina primero para evitar duplicados.\n\n"
            "CAMPOS QUE LLENA:\n"
            "  anp_codi, zona_influencia, md_exa, ac_nomb, md_fuente=Landsat,\n"
            "  md_anno, md_sup (HA), md_este, md_norte,\n"
            "  md_exa, md_zonif, md_mesrep,\n"
            "  md_fecini, md_fecfin [si existen en el FC]\n\n"
            "CAMPOS PARA H2 (visor satelital los llena):\n"
            "  md_img, md_fecimg, md_fuente_sat [si existen]"
        )
        self.tools = [InsertarAlertas]


# ══════════════════════════════════════════════════════════════════════
# UTILIDADES
# ══════════════════════════════════════════════════════════════════════

def _descargar_zip(url, dest_dir):
    """Descarga ZIP de Geobosques y extrae el raster."""
    zip_path = os.path.join(dest_dir, "alertas.zip")
    arcpy.AddMessage(f"   Descargando: {url}")
    req = urllib.request.Request(
        url, headers={"User-Agent": "ATD-Toolbox/5.1"})
    with urllib.request.urlopen(req, timeout=180) as r:
        with open(zip_path, "wb") as f:
            while True:
                chunk = r.read(8192)
                if not chunk:
                    break
                f.write(chunk)
    arcpy.AddMessage("   Extrayendo ZIP...")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest_dir)
    for root, dirs, files in os.walk(dest_dir):
        for fn in files:
            if fn.lower().endswith((".tif", ".tiff", ".img")):
                arcpy.AddMessage(f"   Raster encontrado: {fn}")
                return os.path.join(root, fn)
    raise RuntimeError("No se encontro raster en el ZIP.")


def _asegurar_dominios(gdb):
    """Crea dominios en la GDB solo si no existen."""
    existentes = {d.name for d in arcpy.da.ListDomains(gdb)}

    dominios = {
        "md_causa_dom": {
            "desc": "Causa de deforestacion", "tipo": "SHORT",
            "vals": {
                1: "Agricultura", 2: "Ganaderia", 3: "Mineria",
                5: "Infraestructura vial", 6: "Centros poblados",
                7: "Cultivos ilicitos", 8: "Tala",
                10: "Incendios forestales", 11: "Acuicultura",
                13: "Petroleo y gas", 14: "Sin clasificar",
                99: "Natural/Fenologico"
            }
        },
        "md_fuente_dom": {
            "desc": "Fuente de la alerta", "tipo": "SHORT",
            "vals": {
                1: "PNCB-Geobosques", 2: "Global Forest Watch",
                3: "GLAD", 4: "PRODES", 5: "Otro"
            }
        },
        "md_fuente_sat_dom": {
            "desc": "Fuente satelital", "tipo": "SHORT",
            "vals": {
                1: "PNCB Landsat", 2: "Sentinel-2", 3: "Planet",
                4: "PeruSAT-1", 5: "SPOT", 6: "WorldView",
                7: "Sentinel-1", 8: "GLAD S2",
                9: "Global Forest Watch", 10: "CBERS-4"
            }
        },
        "md_conf_dom": {
            "desc": "Nivel de confianza", "tipo": "SHORT",
            "vals": {1: "Alto", 2: "Medio", 3: "Bajo"}
        },
        "md_bosque_dom": {
            "desc": "Tipo de bosque", "tipo": "SHORT",
            "vals": {
                1: "Bosque primario", 2: "Bosque secundario",
                3: "No bosque", 4: "Sin datos"
            }
        },
    }

    for nombre, cfg in dominios.items():
        if nombre not in existentes:
            arcpy.management.CreateDomain(
                gdb, nombre, cfg["desc"], cfg["tipo"], "CODED")
            for code, desc in cfg["vals"].items():
                arcpy.management.AddCodedValueToDomain(
                    gdb, nombre, code, desc)
            arcpy.AddMessage(f"   Dominio creado: {nombre}")


def _dominio_md_zonif(gdb, fc_dest):
    """Nombre del dominio asignado a md_zonif en el FC destino."""
    for f in arcpy.ListFields(fc_dest):
        if f.name.lower() == "md_zonif" and f.domain:
            return f.domain
    return None


def _asegurar_dominio_zonif(gdb, fc_dest, fc_zon, campo_zon):
    """
    Completa el dominio de md_zonif si esta vacio (caso Cuzco/San Martin).
    Sin valores en el dominio, ArcGIS Pro bloquea la edicion en tabla de atributos.
    """
    dom_name = _dominio_md_zonif(gdb, fc_dest)
    if not dom_name:
        return

    dominios = {d.name: d for d in arcpy.da.ListDomains(gdb)}
    dom = dominios.get(dom_name)
    if not dom or dom.domainType != "CodedValue":
        return

    existentes = set((dom.codedValues or {}).keys())
    nuevos = []

    if campo_zon and arcpy.Exists(fc_zon):
        with arcpy.da.SearchCursor(fc_zon, [campo_zon]) as cur:
            for row in cur:
                val = str(row[0] or "").strip()
                if val and val not in existentes:
                    nuevos.append(val)
                    existentes.add(val)

    if arcpy.Exists(fc_dest):
        with arcpy.da.SearchCursor(fc_dest, ["md_zonif"]) as cur:
            for row in cur:
                val = str(row[0] or "").strip()
                if val and val not in existentes:
                    nuevos.append(val)
                    existentes.add(val)

    if not nuevos and existentes:
        return

    if not existentes and not nuevos:
        arcpy.AddWarning(
            f"   Dominio '{dom_name}' sin valores. "
            "Revise gpo_zonif_anp (campo z_tipo).")
        return

    for val in sorted(set(nuevos)):
        try:
            arcpy.management.AddCodedValueToDomain(
                gdb, dom_name, val, val)
            arcpy.AddMessage(
                f"   Dominio zonificacion: agregado '{val}'")
        except Exception as e:
            arcpy.AddWarning(
                f"   No se pudo agregar '{val}' al dominio: {e}")


def _asegurar_valor_zonif_en_dominio(gdb, fc_dest, valor):
    """Agrega un valor de zonificacion al dominio si aun no existe."""
    val = str(valor or "").strip()
    if not val:
        return
    dom_name = _dominio_md_zonif(gdb, fc_dest)
    if not dom_name:
        return
    try:
        for dom in arcpy.da.ListDomains(gdb):
            if dom.name != dom_name or dom.domainType != "CodedValue":
                continue
            existentes = {str(k).strip() for k in (dom.codedValues or {})}
            existentes |= {str(v).strip() for v in (dom.codedValues or {}).values()}
            if val in existentes:
                return
            arcpy.management.AddCodedValueToDomain(
                gdb, dom_name, val, val)
            return
    except Exception:
        pass


def _buscar_espacial(geom, fc_ref, campo_val):
    """Busca valor de campo_val en fc_ref intersectando con geom."""
    lyr = f"__lyr_{campo_val}_tmp__"
    try:
        if arcpy.Exists(lyr):
            arcpy.management.Delete(lyr)
        arcpy.management.MakeFeatureLayer(fc_ref, lyr)
        arcpy.management.SelectLayerByLocation(
            lyr, "INTERSECT", geom, selection_type="NEW_SELECTION")
        with arcpy.da.SearchCursor(lyr, [campo_val]) as sc:
            for r in sc:
                if r[0] is not None:
                    return r[0]
    except Exception:
        pass
    finally:
        try:
            if arcpy.Exists(lyr):
                arcpy.management.Delete(lyr)
        except Exception:
            pass
    return None


def _buscar_zonificacion(geom, fc_zon, cod_acr, campos_candidatos):
    """
    Zonificacion ANP (md_zonif): intersecta alerta con gpo_zonif_anp,
    filtrando por codigo ACR cuando el FC lo permite.
    """
    if not geom or not arcpy.Exists(fc_zon):
        return None

    campos_zon = {
        f.name.lower(): f.name for f in arcpy.ListFields(fc_zon)
    }
    cod_col = None
    for cand in ("anp_codi", "acr_codi", "cod_acr", "codacr", "codigo"):
        if cand in campos_zon:
            cod_col = campos_zon[cand]
            break

    campos_leer = []
    for cand in campos_candidatos or []:
        key = (cand or "").lower()
        if key in campos_zon and campos_zon[key] not in campos_leer:
            campos_leer.append(campos_zon[key])
    if not campos_leer:
        return None

    lyr = "__lyr_zonif_atd__"
    try:
        if arcpy.Exists(lyr):
            arcpy.management.Delete(lyr)
        arcpy.management.MakeFeatureLayer(fc_zon, lyr)

        if cod_col and cod_acr:
            cod_safe = str(cod_acr).replace("'", "''")
            arcpy.management.SelectLayerByAttribute(
                lyr, "NEW_SELECTION",
                f"{arcpy.AddFieldDelimiters(lyr, cod_col)} = '{cod_safe}'")
            sel_tipo = "SUBSET_SELECTION"
        else:
            sel_tipo = "NEW_SELECTION"

        for metodo in ("INTERSECT", "WITHIN", "CONTAINS"):
            arcpy.management.SelectLayerByLocation(
                lyr, metodo, geom, selection_type=sel_tipo)
            if int(arcpy.management.GetCount(lyr)[0]) == 0:
                continue
            with arcpy.da.SearchCursor(lyr, campos_leer) as sc:
                for row in sc:
                    for val in row:
                        txt = str(val or "").strip()
                        if txt and txt.lower() not in ("none", "null", "-"):
                            return txt
    except Exception:
        pass
    finally:
        try:
            if arcpy.Exists(lyr):
                arcpy.management.Delete(lyr)
        except Exception:
            pass
    return None


def _desc_codigo_dominio(gdb, dom_name, code):
    try:
        for dom in arcpy.da.ListDomains(gdb):
            if dom.name != dom_name or dom.domainType != "CodedValue":
                continue
            for c, desc in (dom.codedValues or {}).items():
                try:
                    if int(c) == int(code):
                        return str(desc)
                except (TypeError, ValueError):
                    if str(c) == str(code):
                        return str(desc)
    except Exception:
        pass
    return None


def _info_campo(fc_dest, nombre_campo):
    """Metadatos de un campo del FC destino."""
    key = (nombre_campo or "").lower()
    for f in arcpy.ListFields(fc_dest):
        if f.name.lower() == key:
            return {
                "nombre": f.name,
                "tipo": f.type,
                "dominio": f.domain or "",
                "alias": f.aliasName or f.name,
            }
    return None


def _codigo_landsat_en_dominio(gdb, dom_name, msg_fn=None):
    """Busca codigo Landsat en un dominio codificado (excluye Planet/Sentinel)."""
    fn = msg_fn or (lambda s: None)
    if not dom_name:
        return None
    candidatos = []
    for dom in arcpy.da.ListDomains(gdb):
        if dom.name != dom_name or dom.domainType != "CodedValue":
            continue
        for code, desc in (dom.codedValues or {}).items():
            dl = str(desc).lower().strip()
            fn(f"   Dominio {dom_name}: {code} = {desc}")
            if "planet" in dl or "sentinel" in dl or "glad" in dl:
                continue
            prio = 99
            if "pncb" in dl and "landsat" in dl:
                prio = 0
            elif "landsat" in dl:
                prio = 1
            else:
                continue
            try:
                candidatos.append((prio, int(code), str(desc)))
            except (TypeError, ValueError):
                pass
    if candidatos:
        candidatos.sort(key=lambda x: (x[0], x[1]))
        fn(f"   Landsat en {dom_name}: {candidatos[0][1]} = {candidatos[0][2]}")
        return candidatos[0][1]
    return None


def _resolver_md_fuente_landsat(gdb, fc_dest, msg_fn=None):
    """
    Resuelve codigo Landsat para md_fuente (alias 'Fuente' en tabla).
    Usa el dominio del GDB (ej. FuenteDeforestacion en Cuzco).
    """
    fn = msg_fn or (lambda s: None)
    _asegurar_dominios(gdb)
    info = _info_campo(fc_dest, "md_fuente")
    if not info:
        fn("   AVISO: campo md_fuente no encontrado en FC destino")
        return 1

    campo = info["nombre"]
    dom_name = info["dominio"]

    try:
        arcpy.management.AssignDefaultToField(fc_dest, campo, "")
    except Exception:
        try:
            arcpy.management.AssignDefaultToField(fc_dest, campo, "NONE")
        except Exception:
            pass

    cod = _codigo_landsat_en_dominio(gdb, dom_name, fn)
    if cod is None:
        cod = _codigo_landsat_en_dominio(gdb, "md_fuente_dom", fn)
    if cod is None and dom_name:
        nuevo = 1
        try:
            existentes = []
            for dom in arcpy.da.ListDomains(gdb):
                if dom.name != dom_name:
                    continue
                for c in (dom.codedValues or {}):
                    try:
                        existentes.append(int(c))
                    except (TypeError, ValueError):
                        pass
            if existentes:
                nuevo = max(existentes) + 1
            arcpy.management.AddCodedValueToDomain(
                gdb, dom_name, nuevo, "Landsat")
            cod = nuevo
            fn(f"   Landsat agregado a {dom_name}: codigo {nuevo}")
        except Exception as ex:
            fn(f"   AVISO agregando Landsat a dominio: {ex}")
            cod = 1

    desc = _desc_codigo_dominio(gdb, dom_name, cod) if dom_name else "Landsat"
    fn(f"   md_fuente (Fuente): codigo {cod} = {desc or 'Landsat'}")
    return int(cod)


def _forzar_landsat_md_fuente(fc_dest, gdb, anno, cod_md_fuente, msg_fn=None):
    """Parche post-insercion: md_fuente = Landsat en todos los registros del ano."""
    fn = msg_fn or (lambda s: None)
    info = _info_campo(fc_dest, "md_fuente")
    if not info:
        return 0

    campo = info["nombre"]
    dom_name = info["dominio"]
    campos_map = _campos_map_fc(fc_dest)
    campo_anno = _nombre_campo_fc(campos_map, "md_anno")
    lyr = "__lyr_md_fuente_landsat__"

    try:
        if arcpy.Exists(lyr):
            arcpy.management.Delete(lyr)
        arcpy.management.MakeFeatureLayer(fc_dest, lyr)
        exp = f"{arcpy.AddFieldDelimiters(lyr, campo_anno)} = {int(anno)}"
        arcpy.management.SelectLayerByAttribute(lyr, "NEW_SELECTION", exp)
        n = int(arcpy.management.GetCount(lyr)[0])
        if n == 0:
            return 0

        try:
            arcpy.management.CalculateField(
                lyr, campo, int(cod_md_fuente), "PYTHON3",
                enforce_field_domain="NO_ENFORCE_DOMAINS")
        except TypeError:
            try:
                arcpy.management.CalculateField(
                    lyr, campo, int(cod_md_fuente), "PYTHON3",
                    enforce_domains="NO_ENFORCE_DOMAINS")
            except TypeError:
                arcpy.management.CalculateField(
                    lyr, campo, int(cod_md_fuente), "PYTHON3")
        except Exception as ex_calc:
            fn(f"   CalculateField md_fuente: {ex_calc}")
            oid_f = arcpy.Describe(fc_dest).OIDFieldName
            n_ok = 0
            with arcpy.da.UpdateCursor(
                    fc_dest, [oid_f, campo], where_clause=exp) as cur:
                for row in cur:
                    row[1] = int(cod_md_fuente)
                    cur.updateRow(row)
                    n_ok += 1
            n = n_ok

        desc = _desc_codigo_dominio(gdb, dom_name, cod_md_fuente)
        fn(f"   md_fuente forzado Landsat: {n:,} registros "
           f"(codigo {cod_md_fuente} = {desc or 'Landsat'})")
        return n
    except Exception as ex:
        fn(f"   AVISO parche md_fuente: {ex}")
        return 0
    finally:
        try:
            if arcpy.Exists(lyr):
                arcpy.management.Delete(lyr)
        except Exception:
            pass


def _campos_map_fc(fc):
    """Mapa nombre_campo_minusculas -> nombre real en el FC."""
    return {f.name.lower(): f.name for f in arcpy.ListFields(fc)}


def _campos_del_fc(fc):
    """Retorna set de nombres de campos en minusculas."""
    return set(_campos_map_fc(fc).keys())


def _nombre_campo_fc(campos_map, nombre):
    return campos_map.get((nombre or "").lower(), nombre)


def _parse_fecha(valor):
    """Convierte string o datetime a objeto datetime de Python."""
    if valor is None:
        return None
    if isinstance(valor, dt):
        return valor
    if isinstance(valor, date):
        return dt(valor.year, valor.month, valor.day)
    s = str(valor).strip()
    for fmt in ["%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d",
                "%Y-%m-%dT%H:%M:%S", "%d-%m-%Y"]:
        try:
            return dt.strptime(s, fmt)
        except Exception:
            pass
    return None


# PNCB Landsat — dominio md_fuente_sat_dom (codigo 1 por defecto)
_MD_FUENTE_SAT_PNCB_LANDSAT = 1
_CAMPO_FEC_IMG_POLY = "_fec_img_atd"


def _borrar_fc(ruta):
    if not ruta or not arcpy.Exists(ruta):
        return
    try:
        arcpy.management.Delete(ruta)
    except Exception:
        pass


def _fmt_fecha(val):
    if not val:
        return "—"
    if isinstance(val, dt):
        return val.strftime("%d/%m/%Y")
    return str(val)


def _codigo_fuente_sat_default(gdb, fc_dest, msg_fn=None):
    """Codigo dominio Landsat para md_fuente_sat (nunca Planet por defecto)."""
    fn = msg_fn or (lambda s: None)
    _asegurar_dominios(gdb)
    try:
        dom_name = None
        for f in arcpy.ListFields(fc_dest):
            if f.name.lower() == "md_fuente_sat" and f.domain:
                dom_name = f.domain
                break
        if not dom_name:
            return _MD_FUENTE_SAT_PNCB_LANDSAT

        candidatos = []
        for dom in arcpy.da.ListDomains(gdb):
            if dom.name != dom_name or dom.domainType != "CodedValue":
                continue
            for code, desc in (dom.codedValues or {}).items():
                dl = str(desc).lower().strip()
                fn(f"   Dominio {dom_name}: {code} = {desc}")
                if "planet" in dl or "sentinel" in dl or "glad" in dl:
                    continue
                prio = 99
                if "pncb" in dl and "landsat" in dl:
                    prio = 0
                elif dl.startswith("landsat") or " landsat" in dl:
                    prio = 1
                elif "landsat" in dl:
                    prio = 2
                else:
                    continue
                try:
                    candidatos.append((prio, int(code), desc))
                except (TypeError, ValueError):
                    pass

        if candidatos:
            candidatos.sort(key=lambda x: (x[0], x[1]))
            cod = candidatos[0][1]
            fn(f"   Landsat seleccionado: codigo {cod} = {candidatos[0][2]}")
            return cod

        # Dominio sin Landsat: agregar PNCB Landsat
        nuevo = 1
        for dom in arcpy.da.ListDomains(gdb):
            if dom.name != dom_name or dom.domainType != "CodedValue":
                continue
            existentes = []
            for c in (dom.codedValues or {}).keys():
                try:
                    existentes.append(int(c))
                except (TypeError, ValueError):
                    pass
            if existentes:
                nuevo = max(existentes) + 1
            break
        arcpy.management.AddCodedValueToDomain(
            gdb, dom_name, nuevo, "PNCB Landsat")
        fn(f"   Landsat agregado al dominio {dom_name}: codigo {nuevo}")
        return nuevo
    except Exception as ex:
        fn(f"   AVISO resolviendo Landsat: {ex}")
    return _MD_FUENTE_SAT_PNCB_LANDSAT


def _asegurar_campos_h1(fc_dest, gdb):
  """Crea md_fecimg / md_fuente_sat si faltan en el FC destino."""
  campos = _campos_map_fc(fc_dest)
  if "md_fecimg" not in campos:
    try:
      arcpy.management.AddField(
        fc_dest, "md_fecimg", "DATE",
        field_alias="Fecha imagen", field_is_nullable="NULLABLE")
      arcpy.AddMessage("   Campo md_fecimg creado en FC destino")
      campos["md_fecimg"] = "md_fecimg"
    except Exception as ex:
      arcpy.AddWarning(f"   No se pudo crear md_fecimg: {ex}")
  if "md_fuente_sat" not in campos:
    try:
      dom = "md_fuente_sat_dom"
      existentes = {d.name for d in arcpy.da.ListDomains(gdb)}
      if dom not in existentes:
        _asegurar_dominios(gdb)
      arcpy.management.AddField(
        fc_dest, "md_fuente_sat", "SHORT",
        field_alias="Fuente", field_is_nullable="NULLABLE",
        field_domain=dom)
      arcpy.AddMessage("   Campo md_fuente_sat creado en FC destino")
      campos["md_fuente_sat"] = "md_fuente_sat"
    except Exception as ex:
      arcpy.AddWarning(f"   No se pudo crear md_fuente_sat: {ex}")
  return campos


def _leer_vat_dbf_geobosques(raster_path):
  """
  Lee PNCB_ATD_*.tif.vat.dbf (sin ArcPy).
  Retorna dict {gridcode: datetime} y dict {gridcode: fuente_txt}.
  """
  mapa_fec, mapa_src = {}, {}
  if not raster_path:
    return mapa_fec, mapa_src
  dbf = raster_path + ".vat.dbf"
  if not os.path.isfile(dbf):
    return mapa_fec, mapa_src
  try:
    with open(dbf, "rb") as fh:
      data = fh.read()
    nrec = struct.unpack("<I", data[4:8])[0]
    hlen = struct.unpack("<H", data[8:10])[0]
    rlen = struct.unpack("<H", data[10:12])[0]
    fields = []
    pos = 32
    while pos < hlen - 1:
      name = data[pos:pos + 11].split(b"\x00")[0].decode("latin1", "replace")
      typ = chr(data[pos + 11])
      flen = data[pos + 16]
      fields.append((name, typ, flen))
      pos += 32
    off = hlen
    for i in range(nrec):
      row = data[off + i * rlen:off + (i + 1) * rlen]
      p = 1
      rec = {}
      for name, typ, flen in fields:
        chunk = row[p:p + flen]
        p += flen
        if typ == "N":
          s = chunk.decode("ascii", "replace").strip()
          if not s:
            rec[name] = None
          elif "." in s or "e" in s.lower():
            rec[name] = float(s)
          else:
            rec[name] = int(s)
        elif typ == "C":
          rec[name] = chunk.decode("latin1", "replace").strip()
        else:
          rec[name] = chunk.decode("latin1", "replace").strip()
      val = rec.get("Value")
      if val is None:
        continue
      try:
        key = int(val)
      except (TypeError, ValueError):
        continue
      fec_raw = rec.get("fecha") or rec.get("Fecha")
      fdt = _parse_fecha(fec_raw)
      if fdt:
        mapa_fec[key] = fdt
      src = rec.get("fuente") or rec.get("Fuente")
      if src:
        mapa_src[key] = str(src).strip()
  except Exception:
    pass
  return mapa_fec, mapa_src


def _campo_gridcode(fc):
    """Campo valor raster en poligonos (RasterToPolygon)."""
    for f in arcpy.ListFields(fc):
        if f.name.lower() in ("gridcode", "grid_code", "value"):
            return f.name
    return None


def _mapa_fechas_geobosques(raster_path, msg_fn=None):
    """
    Lee fechas del raster Geobosques.
    Prioridad: .vat.dbf > RasterToTable > VAT ArcPy.
  """
    fn = msg_fn or (lambda s: None)
    mapa = {}
    if not raster_path:
        return mapa

    mapa_dbf, _ = _leer_vat_dbf_geobosques(raster_path)
    if mapa_dbf:
        fn(f"   Fechas raster (.vat.dbf): {len(mapa_dbf)} valores")
        return mapa_dbf

    if not arcpy.Exists(raster_path):
        fn("   AVISO: raster no encontrado para leer fechas")
        return mapa

    tbl = "in_memory/atd_ras_vat_tmp"
    _borrar_fc(tbl)
    try:
        arcpy.conversion.RasterToTable(raster_path, tbl)
        fields = {f.name.lower(): f.name for f in arcpy.ListFields(tbl)}
        campo_val = None
        for cand in ("value", "gridcode", "grid_code"):
            if cand in fields:
                campo_val = fields[cand]
                break
        campo_fecha = None
        for cand in ("fecha", "fechaimagen", "fec_img", "fecimg", "md_fecimg"):
            if cand in fields:
                campo_fecha = fields[cand]
                break
        if campo_val and campo_fecha:
            with arcpy.da.SearchCursor(tbl, [campo_val, campo_fecha]) as cur:
                for row in cur:
                    val, fec_raw = row
                    if val is None:
                        continue
                    fdt = _parse_fecha(fec_raw)
                    if not fdt:
                        continue
                    try:
                        mapa[int(val)] = fdt
                    except (TypeError, ValueError):
                        mapa[str(val).strip()] = fdt
            fn(
                f"   Fechas raster (RasterToTable): {campo_val} -> "
                f"{campo_fecha} ({len(mapa)} valores)"
            )
            return mapa
        fn(f"   AVISO RasterToTable sin Fecha. Campos: {sorted(fields.keys())}")
    except Exception as ex:
        fn(f"   AVISO RasterToTable: {ex}")
    finally:
        _borrar_fc(tbl)

    try:
        arcpy.management.BuildRasterAttributeTable(raster_path, "Overwrite")
    except Exception:
        try:
            arcpy.management.BuildRasterAttributeTable(raster_path, "Skip")
        except Exception:
            pass

    fields = {f.name.lower(): f.name for f in arcpy.ListFields(raster_path)}
    campo_val = None
    for cand in ("value", "gridcode", "grid_code"):
        if cand in fields:
            campo_val = fields[cand]
            break
    campo_fecha = None
    for cand in ("fecha", "fechaimagen", "fec_img", "fecimg", "md_fecimg"):
        if cand in fields:
            campo_fecha = fields[cand]
            break

    if not campo_val or not campo_fecha:
        fn(
            f"   AVISO: raster sin campo Fecha en VAT "
            f"(val={campo_val or '—'}, fecha={campo_fecha or '—'})"
        )
        return mapa

    with arcpy.da.SearchCursor(raster_path, [campo_val, campo_fecha]) as cur:
        for row in cur:
            val, fec_raw = row
            if val is None:
                continue
            fdt = _parse_fecha(fec_raw)
            if not fdt:
                continue
            try:
                mapa[int(val)] = fdt
            except (TypeError, ValueError):
                mapa[str(val).strip()] = fdt

    fn(f"   Fechas raster (VAT): {campo_val} -> {campo_fecha} ({len(mapa)} valores)")
    return mapa


def _fecha_desde_gridcode(mapa_fechas, grid_val, anno=None):
    """Resuelve md_fecimg desde gridcode Geobosques (Value = dias desde 31/12/año-1)."""
    if grid_val is None:
        return None
    try:
        g = int(float(grid_val))
    except (TypeError, ValueError):
        return None
    if mapa_fechas:
        f = mapa_fechas.get(g)
        if f:
            return f
    if anno and 1 <= g <= 366:
        # Misma formula que Geobosques: DateAdd("d", Value, "31-12-(anno-1)")
        return dt(anno - 1, 12, 31) + timedelta(days=g)
    return None


def _asignar_fecha_a_poligonos(poly_fc, mapa_fechas, campo_grid, anno, msg_fn=None):
    """Escribe _fec_img_atd en poligonos raster antes del Clip."""
    fn = msg_fn or (lambda s: None)
    if not campo_grid or not arcpy.Exists(poly_fc):
        return 0
    nombres = {f.name.lower(): f.name for f in arcpy.ListFields(poly_fc)}
    if campo_grid.lower() not in nombres:
        return 0
    campo_grid = nombres[campo_grid.lower()]
    try:
        arcpy.management.DeleteField(poly_fc, _CAMPO_FEC_IMG_POLY)
    except Exception:
        pass
    arcpy.management.AddField(poly_fc, _CAMPO_FEC_IMG_POLY, "DATE")
    n_ok = 0
    with arcpy.da.UpdateCursor(
            poly_fc, [campo_grid, _CAMPO_FEC_IMG_POLY]) as cur:
        for row in cur:
            fec = _fecha_desde_gridcode(mapa_fechas, row[0], anno)
            if fec:
                row[1] = fec
                cur.updateRow(row)
                n_ok += 1
    fn(f"   Fecha imagen en poligonos raster: {n_ok:,} poligonos")
    return n_ok


# ══════════════════════════════════════════════════════════════════════
# HERRAMIENTA 1
# ══════════════════════════════════════════════════════════════════════

class InsertarAlertas(object):

    def __init__(self):
        self.label = (
            "Descarga automatizada de Alertas Tempranas de Deforestación"
        )
        self.description = (
            "Descarga alertas Geobosques del año seleccionado\n"
            "e inserta los polígonos en el FC existente\n"
            "MonitoreoDeforestacion (alertas del año en curso).\n\n"
            "El histórico 2001-2025 permanece en MonitoreoDeforestacionAcumulado.\n\n"
            "Procesa ACRs (anp_codi) y Zonas de Influencia (zona_influencia).\n"
            "Elimina registros previos del mismo año antes de insertar.\n\n"
            "v5.1: Agrega parametros de fecha inicio y fin del periodo."
        )
        self.canRunInBackground = False
        self._h1_last_gdb = ""

    def getParameterInfo(self):

        p0 = arcpy.Parameter(
            displayName="* GDB Linea Base Deforestacion",
            name="gdb_trabajo",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Input")
        p0.filter.list = ["Local Database"]

        p1 = arcpy.Parameter(
            displayName="* Año de alertas a descargar",
            name="anno",
            datatype="GPString",
            parameterType="Required",
            direction="Input")
        p1.filter.type = "ValueList"
        p1.filter.list = ANOS_DISPONIBLES
        p1.value = "2026"

        # ── NUEVO v5.1: Rango de fechas ───────────────────────────────
        p2 = arcpy.Parameter(
            displayName="* Fecha inicio del periodo monitoreado",
            name="fecha_ini",
            datatype="GPDate",
            parameterType="Required",
            direction="Input")
        p2.value = "01/01/2026"

        p3 = arcpy.Parameter(
            displayName="* Fecha fin del periodo monitoreado",
            name="fecha_fin",
            datatype="GPDate",
            parameterType="Required",
            direction="Input")
        today_str = dt.now().strftime("%d/%m/%Y")
        p3.value = today_str
        # ─────────────────────────────────────────────────────────────

        p4 = arcpy.Parameter(
            displayName="* FC destino (MonitoreoDeforestacion)",
            name="fc_destino",
            datatype="GPString",
            parameterType="Required",
            direction="Input")
        p4.value = "MonitoreoDeforestacion"
        p4.filter.type = "ValueList"
        p4.filter.list = ["MonitoreoDeforestacion"]

        p5 = arcpy.Parameter(
            displayName="* FC de ACRs y Zonas de Influencia",
            name="fc_acr",
            datatype="GPString",
            parameterType="Required",
            direction="Input")
        p5.value = "gpo_anp_monit"
        p5.filter.type = "ValueList"
        p5.filter.list = ["gpo_anp_monit"]

        p6 = arcpy.Parameter(
            displayName="* FC de Zonificacion ANP",
            name="fc_zonif",
            datatype="GPString",
            parameterType="Required",
            direction="Input")
        p6.value = "gpo_zonif_anp"
        p6.filter.type = "ValueList"
        p6.filter.list = ["gpo_zonif_anp"]

        p7 = arcpy.Parameter(
            displayName="* FC de EXA (grilla de referencia)",
            name="fc_exa",
            datatype="GPString",
            parameterType="Required",
            direction="Input")
        p7.value = "gpo_exa"
        p7.filter.type = "ValueList"
        p7.filter.list = ["gpo_exa"]

        p8 = arcpy.Parameter(
            displayName="* Campo codigo en FC de areas (ACR/ZI)",
            name="campo_cod",
            datatype="GPString",
            parameterType="Required",
            direction="Input")
        p8.value = "acr_codi"
        p8.filter.type = "ValueList"
        p8.filter.list = ["acr_codi", "anp_codi", "cod_acr", "codigo", "cod", "CODOBJ"]

        p9 = arcpy.Parameter(
            displayName="* Campo nombre en FC de areas (ACR/ZI)",
            name="campo_nom",
            datatype="GPString",
            parameterType="Required",
            direction="Input")
        p9.value = "acr_nomb"
        p9.filter.type = "ValueList"
        p9.filter.list = ["acr_nomb", "anp_nomb", "ANP_NOM", "nombre", "nomobj", "name"]

        p10 = arcpy.Parameter(
            displayName="* Campo tipo/clasificacion (para detectar ZI vs ACR)",
            name="campo_tipo",
            datatype="GPString",
            parameterType="Optional",
            direction="Input")
        p10.value = "Influen"
        p10.filter.type = "ValueList"
        p10.filter.list = ["Influen", "TipZona", "tipo", "anp_clase", "acr_codi", "CODOBJ"]

        p11 = arcpy.Parameter(
            displayName="Eliminar registros previos del mismo año",
            name="eliminar_prev",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        p11.value = True

        return [p0, p1, p2, p3, p4, p5, p6, p7, p8, p9, p10, p11]

    def isLicensed(self):
        return True

    def updateParameters(self, p):
        """Rellena desplegables al seleccionar la GDB; auto-ajusta fechas."""

        # ── Auto-ajustar fechas al cambiar el año ─────────────────────
        anno_val = p[1].valueAsText
        if anno_val:
            if not p[2].altered:
                p[2].value = f"01/01/{anno_val}"
            if not p[3].altered:
                # Fin: 31/12 del año, pero no mayor que hoy
                try:
                    fin_anno = dt(int(anno_val), 12, 31)
                    hoy      = dt.now()
                    fin_uso  = min(fin_anno, hoy)
                    p[3].value = fin_uso.strftime("%d/%m/%Y")
                except Exception:
                    p[3].value = f"31/12/{anno_val}"

        # ── Rellena desplegables con FCs de la GDB ────────────────────
        gdb_abs = gdb_absoluta_si_existe(p[0].valueAsText)
        if not gdb_abs:
            return

        try:
            gdb_cambio = gdb_abs != getattr(self, "_h1_last_gdb", "")
            if gdb_cambio:
                self._h1_last_gdb = gdb_abs
                p[0].value = gdb_abs

            configurar_region(gdb_abs, force=gdb_cambio)
            h1_cfg = h1_config_activa()
            arcpy.env.workspace = gdb_abs
            fcs = sorted(arcpy.ListFeatureClasses() or [])
            if not fcs:
                return

            fc_specs = (
                (4, lambda: resolver_fc_alertas(gdb_abs, fcs)),
                (5, lambda: resolver_fc_h1(gdb_abs, fcs, "fc_anp")),
                (6, lambda: resolver_fc_h1(gdb_abs, fcs, "fc_zonif")),
                (7, lambda: resolver_fc_h1(gdb_abs, fcs, "fc_exa")),
            )
            for idx, pick_fn in fc_specs:
                p[idx].filter.list = fcs
                cur = p[idx].valueAsText or ""
                if gdb_cambio or cur not in fcs:
                    p[idx].value = pick_fn()

            # Campos del FC ACR (p5) → p8, p9, p10
            fc_acr = p[5].valueAsText
            if fc_acr:
                ruta = os.path.join(gdb_abs, fc_acr)
                if arcpy.Exists(ruta):
                    campos = [
                        f.name for f in arcpy.ListFields(ruta)
                        if f.type not in (
                            "OID", "Geometry", "GlobalID")]
                    if campos:
                        campo_specs = (
                            (8, "campo_cod"),
                            (9, "campo_nom"),
                            (10, "campo_tipo"),
                        )
                        for idx, key in campo_specs:
                            candidatos = h1_cfg.get(key, [])
                            p[idx].filter.list = campos
                            cur = p[idx].valueAsText or ""
                            pick = resolver_campo_h1(
                                ruta, candidatos, campos_list=campos)
                            if gdb_cambio or cur not in campos:
                                if pick:
                                    p[idx].value = pick
        except Exception:
            pass

    def updateMessages(self, p):
        """Valida fechas y que los campos existan en el FC de areas."""
        fi = _parse_fecha(p[2].value)
        ff = _parse_fecha(p[3].value)
        if fi and ff and ff < fi:
            p[3].setErrorMessage(
                "La fecha fin no puede ser anterior a la fecha inicio.")
        else:
            p[3].clearMessage()

        gdb_abs = gdb_absoluta_si_existe(p[0].valueAsText)
        if not gdb_abs:
            p[0].setErrorMessage(
                "Seleccione la GDB de linea base (.gdb) con ruta valida.")
            return
        p[0].clearMessage()

        fc_acr = p[5].valueAsText
        if not fc_acr:
            return
        ruta = os.path.join(gdb_abs, fc_acr)
        if not arcpy.Exists(ruta):
            p[5].setErrorMessage(f"FC no encontrado en la GDB: {fc_acr}")
            return
        p[5].clearMessage()

        campos = {
            f.name for f in arcpy.ListFields(ruta)
            if f.type not in ("OID", "Geometry", "GlobalID")
        }
        for idx, etiqueta in (
            (8, "codigo"),
            (9, "nombre"),
            (10, "tipo/clasificacion"),
        ):
            val = p[idx].valueAsText
            if not val:
                continue
            if val not in campos:
                p[idx].setErrorMessage(
                    f"El campo '{val}' no existe en {fc_acr}. "
                    "Seleccione otra GDB o espere la auto-deteccion.")
            else:
                p[idx].clearMessage()

    def execute(self, parameters, messages):
        gdb          = parameters[0].valueAsText
        anno         = int(parameters[1].valueAsText)
        fecha_ini    = _parse_fecha(parameters[2].value)   # NEW v5.1
        fecha_fin    = _parse_fecha(parameters[3].value)   # NEW v5.1
        fc_dest_nom  = parameters[4].valueAsText
        fc_acr_nom   = parameters[5].valueAsText
        fc_zon_nom   = parameters[6].valueAsText
        fc_exa_nom   = parameters[7].valueAsText
        campo_cod    = parameters[8].valueAsText
        campo_nom    = parameters[9].valueAsText
        campo_tipo   = parameters[10].valueAsText
        elim_prev    = parameters[11].value

        arcpy.env.overwriteOutput = True
        arcpy.env.workspace = gdb
        msg = arcpy.AddMessage
        configurar_region(gdb, force=True)
        sincronizar_imports_region(globals())

        try:
            msg("=" * 65)
            msg(f"ATD H1 v5.7 — INSERTAR ALERTAS {anno}")
            msg(f"GFP Subnacional - {REGION_NOMBRE}")
            msg("=" * 65)
            msg(f"   GDB destino  : {gdb}")
            msg(f"   FC destino   : {fc_dest_nom}")
            msg(f"   Año alertas  : {anno}")
            msg(f"   Periodo      : {_fmt_fecha(fecha_ini)} → {_fmt_fecha(fecha_fin)}")
            msg(f"   FC ACR/ZI    : {fc_acr_nom}")
            msg("")

            # ── Rutas ─────────────────────────────────────────────────
            fc_dest = os.path.join(gdb, fc_dest_nom)
            fc_acr  = os.path.join(gdb, fc_acr_nom)
            fc_zon  = os.path.join(gdb, fc_zon_nom)
            fc_exa  = os.path.join(gdb, fc_exa_nom)

            for ruta, nom in [
                (fc_dest, fc_dest_nom),
                (fc_acr,  fc_acr_nom),
                (fc_zon,  fc_zon_nom),
                (fc_exa,  fc_exa_nom),
            ]:
                if not arcpy.Exists(ruta):
                    arcpy.AddError(f"FC no encontrado: {nom}")
                    return

            # ── Campos reales del FC destino ──────────────────────────
            campos_map = _asegurar_campos_h1(fc_dest, gdb)
            campos_dest = set(campos_map.keys())
            msg(f"   Campos en FC destino: {len(campos_dest)}")

            tiene = lambda c: c.lower() in campos_dest
            msg(f"   anp_codi      : {'SI' if tiene('anp_codi') else 'NO'}")
            msg(f"   zi_codi       : {'SI' if tiene('zi_codi') else 'NO'}")
            msg(f"   md_anno       : {'SI' if tiene('md_anno') else 'NO'}")
            msg(f"   md_sup        : {'SI' if tiene('md_sup') else 'NO'}")
            msg(f"   md_fuente     : {'SI' if tiene('md_fuente') else 'NO'}")
            msg(f"   md_fecimg     : {'SI' if tiene('md_fecimg') else 'NO'}")
            msg(f"   md_fuente_sat : {'SI' if tiene('md_fuente_sat') else 'NO'}")
            msg(f"   md_fecini     : {'SI' if tiene('md_fecini') else 'NO (se omitira)'}")
            msg(f"   md_fecfin     : {'SI' if tiene('md_fecfin') else 'NO (se omitira)'}")
            msg("")

            # ── PASO 1: URL Geobosques ─────────────────────────────────
            url = _URL_BASE.format(anno=anno)
            msg(f"[1/7] Descargando alertas Geobosques {anno}...")

            tmp = tempfile.mkdtemp(prefix=f"ATD_H1_{anno}_")
            try:
                raster_alertas = _descargar_zip(url, tmp)
            except Exception as e:
                arcpy.AddError(
                    f"Error descargando alertas {anno}: {e}\n"
                    f"URL intentada: {url}\n"
                    "Verifica tu conexion a internet.")
                return

            # ── PASO 2: Raster → polígonos ───────────────────────────
            msg("")
            msg("[2/7] Convirtiendo raster a poligonos...")
            poly_raw = "in_memory/poly_alertas_raw"
            _borrar_fc(poly_raw)
            arcpy.conversion.RasterToPolygon(
                raster_alertas, poly_raw, "NO_SIMPLIFY")
            total_raw = int(arcpy.management.GetCount(poly_raw)[0])
            msg(f"   Total poligonos raster: {total_raw:,}")
            mapa_fechas = _mapa_fechas_geobosques(raster_alertas, msg)
            campo_grid_poly = _campo_gridcode(poly_raw)
            _asignar_fecha_a_poligonos(
                poly_raw, mapa_fechas, campo_grid_poly, anno, msg)
            cod_md_fuente = _resolver_md_fuente_landsat(gdb, fc_dest, msg)
            info_fue = _info_campo(fc_dest, "md_fuente")
            dom_fue = info_fue["dominio"] if info_fue else ""
            desc_fue = _desc_codigo_dominio(gdb, dom_fue, cod_md_fuente)
            msg(f"   md_fuente (Fuente) insercion: {cod_md_fuente} = "
                f"{desc_fue or 'Landsat'}")
            es_cuzco = (_REGION_ACTIVA or "").lower() == "cuzco"

            # ── PASO 3: Dominios ──────────────────────────────────────
            msg("")
            msg("[3/7] Verificando dominios en GDB...")
            _asegurar_dominios(gdb)

            h1_cfg = h1_config_activa()
            campos_zon_list = [
                f.name for f in arcpy.ListFields(fc_zon)
                if f.type not in ("OID", "Geometry", "GlobalID")]
            campo_tz_pre = resolver_campo_h1(
                fc_zon,
                h1_cfg.get("zonif_campos", []),
                campos_list=campos_zon_list,
            )
            _asegurar_dominio_zonif(gdb, fc_dest, fc_zon, campo_tz_pre)

            # ── PASO 4: Eliminar registros previos del año ────────────
            if elim_prev:
                msg("")
                msg(f"[4/7] Eliminando registros previos del año {anno}...")
                lyr_del = "__lyr_del_anno__"
                try:
                    if arcpy.Exists(lyr_del):
                        arcpy.management.Delete(lyr_del)
                    arcpy.management.MakeFeatureLayer(
                        fc_dest, lyr_del,
                        where_clause=f"md_anno = {anno}")
                    cnt_del = int(arcpy.management.GetCount(lyr_del)[0])
                    if cnt_del > 0:
                        arcpy.management.DeleteFeatures(lyr_del)
                        msg(f"   Eliminados: {cnt_del:,} registros del {anno}")
                    else:
                        msg(f"   Sin registros previos del {anno}")
                except Exception as e:
                    arcpy.AddWarning(f"   No se pudo eliminar previos: {e}")
                finally:
                    try:
                        if arcpy.Exists(lyr_del):
                            arcpy.management.Delete(lyr_del)
                    except Exception:
                        pass
            else:
                msg("")
                msg("[4/7] Manteniendo registros previos (elim_prev=False)")

            # ── PASO 5: Detectar campos auxiliares ────────────────────
            msg("")
            msg("[5/7] Detectando campos auxiliares...")

            campos_exa_list = [
                f.name for f in arcpy.ListFields(fc_exa)
                if f.type not in ("OID", "Geometry", "GlobalID")]
            col_fi = resolver_campo_h1(
                fc_exa,
                h1_cfg.get("exa_campos", []),
                campos_list=campos_exa_list,
            )

            campos_zon_list = [
                f.name for f in arcpy.ListFields(fc_zon)
                if f.type not in ("OID", "Geometry", "GlobalID")]
            campo_tz = resolver_campo_h1(
                fc_zon,
                h1_cfg.get("zonif_campos", []),
                campos_list=campos_zon_list,
            )
            campos_zonif_busqueda = list(h1_cfg.get("zonif_campos", []))
            if campo_tz and campo_tz not in campos_zonif_busqueda:
                campos_zonif_busqueda.insert(0, campo_tz)

            msg(f"   EXA campo   : {col_fi or 'no encontrado'}")
            msg(f"   Zonif campo : {campo_tz or 'no encontrado'}")
            if campo_tz:
                _asegurar_dominio_zonif(gdb, fc_dest, fc_zon, campo_tz)

            # ── PASO 6: Leer áreas (ACR + ZI) ─────────────────────────
            msg("")
            msg("[6/7] Leyendo ACRs y Zonas de Influencia...")

            campos_acr = {
                f.name.lower(): f.name
                for f in arcpy.ListFields(fc_acr)}

            leer_acr = ["OID@", "SHAPE@", campo_cod, campo_nom]
            tiene_tipo = (campo_tipo and
                          campo_tipo.lower() in campos_acr)
            if tiene_tipo:
                leer_acr.append(campo_tipo)

            areas = []
            with arcpy.da.SearchCursor(fc_acr, leer_acr) as cur:
                for row in cur:
                    cod      = str(row[2] or "").strip()
                    nom      = str(row[3] or cod).strip()
                    tipo_val = str(row[4] or "").strip() if tiene_tipo else ""

                    if not cod:
                        continue

                    es_zi = es_zi_area(cod, tipo_val)

                    areas.append({
                        "cod":   cod,
                        "nom":   nom,
                        "geom":  row[1],
                        "es_zi": es_zi,
                    })

            n_acr = sum(1 for a in areas if not a["es_zi"])
            n_zi  = sum(1 for a in areas if a["es_zi"])
            msg(f"   ACRs encontrados         : {n_acr}")
            msg(f"   Zonas de Influencia (ZI) : {n_zi}")
            msg(f"   Total areas              : {len(areas)}")

            if not areas:
                arcpy.AddError(
                    "No se encontraron areas en el FC. "
                    "Revisa el campo codigo.")
                return

            # ── PASO 7: Insertar en FC acumulado ──────────────────────
            msg("")
            msg("[7/7] Procesando areas — Clip + Insercion en FC destino...")
            msg("")

            _campos_cfg = [
                ("SHAPE@",    True),
                ("anp_codi",  True),
                ("zi_codi",   False),
                ("zona_influencia", False),
                ("ac_nomb",   False),
                ("md_fuente", True),
                ("md_anno",   False),
                ("md_sup",    False),
                ("md_este",   False),
                ("md_norte",  False),
                ("md_exa",    False),
                ("md_zonif",  False),
                ("md_mesrep", False),
                ("md_fecini", False),   # NEW v5.1
                ("md_fecfin", False),   # NEW v5.1
                ("md_fecimg", False),
                ("md_fuente_sat", False),
            ]

            campos_map = _campos_map_fc(fc_dest)
            campos_insert = ["SHAPE@"]
            for nombre, obligatorio in _campos_cfg:
                if nombre == "SHAPE@":
                    continue
                key = nombre.lower()
                if key in campos_map or obligatorio:
                    campos_insert.append(
                        _nombre_campo_fc(campos_map, nombre))

            def _idx(c):
                nom = _nombre_campo_fc(campos_map, c)
                try:
                    return campos_insert.index(nom)
                except ValueError:
                    return -1

            msg(f"   Campos a insertar ({len(campos_insert)}): "
                f"{', '.join(campos_insert[1:8])}...")
            msg(f"   i_md_fuente={_idx('md_fuente')}  "
                f"i_md_fecimg={_idx('md_fecimg')}")

            i_acod  = _idx("anp_codi")
            i_zcod  = _idx("zi_codi")
            i_zona  = _idx("zona_influencia")
            i_nom   = _idx("ac_nomb")
            i_fue   = _idx("md_fuente")
            i_anno  = _idx("md_anno")
            i_sup   = _idx("md_sup")
            i_este  = _idx("md_este")
            i_nor   = _idx("md_norte")
            i_exa   = _idx("md_exa")
            i_zon   = _idx("md_zonif")
            i_mes   = _idx("md_mesrep")
            i_fini  = _idx("md_fecini")   # NEW v5.1
            i_ffin  = _idx("md_fecfin")   # NEW v5.1
            i_fecimg = _idx("md_fecimg")

            mes_actual   = dt.now().month
            total_insert = 0
            n_con_fecha  = 0
            n_con_zonif  = 0

            for area in areas:
                cod   = area["cod"]
                nom   = area["nom"]
                es_zi = area["es_zi"]
                shape = area["geom"]

                tag  = cod.replace(" ", "_").replace("/", "_").replace("-", "_")
                clip = f"in_memory/clip_{tag}_{uuid.uuid4().hex[:8]}"
                _borrar_fc(clip)

                try:
                    arcpy.analysis.Clip(poly_raw, shape, clip)
                    cnt = int(arcpy.management.GetCount(clip)[0])

                    if cnt == 0:
                        tipo_txt = "ZI" if es_zi else "ACR"
                        msg(f"   {tipo_txt} {cod}: sin alertas, omitido.")
                        continue

                    arcpy.management.AddField(clip, "_area_ha_", "DOUBLE")
                    arcpy.management.CalculateField(
                        clip, "_area_ha_",
                        "!SHAPE.AREA@hectares!", "PYTHON3")

                    clip_fields = ["SHAPE@", "_area_ha_"]
                    clip_field_names = {
                        f.name.lower(): f.name for f in arcpy.ListFields(clip)
                    }
                    idx_grid = None
                    idx_fec_poly = None
                    if campo_grid_poly and campo_grid_poly.lower() in clip_field_names:
                        clip_fields.append(
                            clip_field_names[campo_grid_poly.lower()])
                        idx_grid = len(clip_fields) - 1
                    if _CAMPO_FEC_IMG_POLY.lower() in clip_field_names:
                        clip_fields.append(
                            clip_field_names[_CAMPO_FEC_IMG_POLY.lower()])
                        idx_fec_poly = len(clip_fields) - 1

                    filas_clip = []
                    with arcpy.da.SearchCursor(clip, clip_fields) as sc:
                        for row in sc:
                            filas_clip.append(row)

                    ins = 0
                    with arcpy.da.InsertCursor(fc_dest, campos_insert) as ic:
                        for row in filas_clip:
                            geom = row[0]
                            area_ha = row[1]
                            if geom is None:
                                continue

                            grid_val = (
                                row[idx_grid] if idx_grid is not None else None)
                            fec_img = (
                                row[idx_fec_poly]
                                if idx_fec_poly is not None else None)
                            fec_img = _parse_fecha(fec_img)
                            if not fec_img:
                                fec_img = _fecha_desde_gridcode(
                                    mapa_fechas, grid_val, anno)

                            try:
                                cent  = geom.centroid
                                este  = round(cent.X, 1)
                                norte = round(cent.Y, 1)
                            except Exception:
                                este = norte = None

                            val_exa = None
                            val_zon = None
                            if col_fi:
                                val_exa = _buscar_espacial(
                                    geom, fc_exa, col_fi)
                            if campos_zonif_busqueda:
                                cod_acr_zon = cod if not es_zi else None
                                if es_zi:
                                    zi_map = (
                                        REGION_CONFIGS.get(
                                            _REGION_ACTIVA or "", {})
                                        .get("zi_codi_to_acr", {}))
                                    cod_acr_zon = zi_map.get(cod, cod_acr_zon)
                                val_zon = _buscar_zonificacion(
                                    geom, fc_zon, cod_acr_zon,
                                    campos_zonif_busqueda)
                                if val_zon:
                                    _asegurar_valor_zonif_en_dominio(
                                        gdb, fc_dest, val_zon)

                            fila = [None] * len(campos_insert)
                            fila[0] = geom

                            zi_map = (
                                REGION_CONFIGS.get(
                                    _REGION_ACTIVA or "", {})
                                .get("zi_codi_to_acr", {}))

                            if i_acod >= 0:
                                if es_zi:
                                    lbl = cod.upper()
                                    if not lbl.startswith("ZI "):
                                        lbl = f"ZI {lbl.replace('ZI_', '').replace('_', ' ').strip()}"
                                    fila[i_acod] = zi_map.get(lbl) or zi_map.get(cod)
                                else:
                                    fila[i_acod] = cod
                            if i_zcod >= 0:
                                fila[i_zcod] = None
                            if i_zona >= 0:
                                if es_zi:
                                    lbl = cod.upper()
                                    if lbl.startswith("ZI"):
                                        fila[i_zona] = lbl if " " in lbl else f"ZI {lbl[2:].strip()}"
                                    else:
                                        fila[i_zona] = cod
                                else:
                                    fila[i_zona] = None
                            if i_nom  >= 0: fila[i_nom]  = nom
                            if i_fue  >= 0: fila[i_fue]  = cod_md_fuente
                            if i_anno >= 0: fila[i_anno] = anno
                            if i_sup  >= 0:
                                fila[i_sup] = (
                                    round(area_ha, 6) if area_ha else None)
                            if i_este >= 0: fila[i_este] = este
                            if i_nor  >= 0: fila[i_nor]  = norte
                            if i_exa  >= 0: fila[i_exa]  = val_exa
                            if i_zon  >= 0 and val_zon:
                                fila[i_zon]  = val_zon
                                n_con_zonif += 1
                            if i_mes  >= 0: fila[i_mes]  = mes_actual
                            if i_fini >= 0: fila[i_fini] = fecha_ini
                            if i_ffin >= 0: fila[i_ffin] = fecha_fin
                            if i_fecimg >= 0:
                                if fec_img:
                                    fila[i_fecimg] = fec_img
                                    n_con_fecha += 1

                            ic.insertRow(fila)
                            ins += 1

                    total_insert += ins
                    tipo_txt = "ZI" if es_zi else "ACR"
                    msg(f"   {tipo_txt} {cod} ({nom[:32]}): {ins:>5} alertas")

                except Exception as e:
                    arcpy.AddWarning(f"   ERROR en {cod}: {e}")

                finally:
                    _borrar_fc(clip)

            _borrar_fc(poly_raw)

            n_fue = _forzar_landsat_md_fuente(
                fc_dest, gdb, anno, cod_md_fuente, msg)
            desc_fue = _desc_codigo_dominio(gdb, dom_fue, cod_md_fuente)

            # ── RESUMEN FINAL ─────────────────────────────────────────
            msg("")
            msg("=" * 65)
            msg(f"ATD H1 v5.7 — COMPLETADO")
            msg("=" * 65)
            msg(f"   Año procesado      : {anno}")
            msg(f"   Periodo            : "
                f"{_fmt_fecha(fecha_ini)} → {_fmt_fecha(fecha_fin)}")
            msg(f"   Areas procesadas   : {len(areas)}  "
                f"({n_acr} ACR + {n_zi} ZI)")
            msg(f"   Alertas insertadas : {total_insert:,}")
            msg(f"   FC destino         : {fc_dest_nom}")
            msg(f"   md_fuente (Fuente) : {cod_md_fuente} = "
                f"{desc_fue or 'Landsat'} ({n_fue:,} registros)")
            msg(f"   md_fecimg          : {n_con_fecha:,} / {total_insert:,} alertas con fecha")
            msg(f"   md_zonif           : {n_con_zonif:,} / {total_insert:,} alertas con zonificacion")
            if total_insert and n_con_fecha < total_insert:
                msg(f"   AVISO md_fecimg     : {total_insert - n_con_fecha:,} sin fecha "
                    f"(revisa gridcode en poligonos)")
            msg(f"   md_anno            : {anno}")
            msg(f"   md_fecini          : {_fmt_fecha(fecha_ini) if fecha_ini else 'campo no existe'}")
            msg(f"   md_fecfin          : {_fmt_fecha(fecha_fin) if fecha_fin else 'campo no existe'}")
            msg(f"   EXA campo          : {col_fi or 'N/A'}")
            msg(f"   Zonif campo        : {campo_tz or 'N/A'}")
            msg("")
            msg("PROXIMOS PASOS:")
            msg(f"  → H2: Abre el Visor Satelital")
            msg(f"       Filtra por md_anno = {anno} para ver las nuevas alertas")
            msg("       md_img (H2); md_fecimg ya viene de H1")
            msg("  → Fotointerpreta: marca md_causa en cada alerta")
            msg("  → H3: Genera el Reporte PDF oficial")
            msg("=" * 65)

        except Exception as e:
            arcpy.AddError("ERROR CRITICO: " + str(e))
            arcpy.AddError(traceback.format_exc())

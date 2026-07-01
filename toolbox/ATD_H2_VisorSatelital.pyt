"""
═══════════════════════════════════════════════════════════════════════════════
ATD TOOLBOX — HERRAMIENTA 2: VISOR SATELITAL
Alertas Tempranas de Deforestacion — GFP Subnacional Loreto/Cuzco/San Martin
UI estilo USGS EarthExplorer + Planet API + Landsat MPC firmado + export HD
═══════════════════════════════════════════════════════════════════════════════
  ✓ UI por pasos: 1.Datos → 2.Satélite → 3.Resultados → 4.Exportar
  ✓ Vectores: mostrar/ocultar alerta seleccionada y vecinas en el visor
  ✓ Export ArcGIS: prioriza imagen HD (4096 px) igual a la vista
  ✓ Landsat: firma SAS Planetary Computer + capas GIBS Landsat 8/9
  ✓ Alertas ZI: lectura desde zi_codi además de anp_codi
═══════════════════════════════════════════════════════════════════════════════
"""

import arcpy
import os
import sys
import traceback

_toolbox_dir = os.path.dirname(os.path.abspath(__file__))
if _toolbox_dir not in sys.path:
    sys.path.insert(0, _toolbox_dir)
from atd_region_config import (
    configurar_region,
    sincronizar_imports_region,
    resolver_fc_alertas,
    gdb_absoluta_si_existe,
    ACR_CODIGOS_FC,
    REGION_NOMBRE,
)
from atd_imagenes_h3 import guardar_imagen_h3

try:
    from atd_planet_io import (
        get_api_key as _planet_api_key,
        is_available as _planet_disponible,
        http_bytes as _planet_http_bytes,
        search_scenes as _planet_search_scenes,
        thumbnail_url as _planet_thumbnail_url,
    )
except ImportError:
    def _planet_disponible():
        return False

    def _planet_api_key():
        return None

    def _planet_search_scenes(*_a, **_k):
        return []

    def _planet_http_bytes(*_a, **_k):
        raise RuntimeError("atd_planet_io no disponible")

    def _planet_thumbnail_url(*_a, **_k):
        raise RuntimeError("atd_planet_io no disponible")
import threading
import json
import io
import struct
import zlib
import re
import tempfile
import shutil
import math
from datetime import datetime as dt, timedelta
import tkinter as tk
from tkinter import ttk, messagebox
import urllib.request
import urllib.parse
import ssl

# ─── SSL ──────────────────────────────────────────────────────────────────────
try:
    _CTX = ssl.create_default_context()
    _CTX.check_hostname = False
    _CTX.verify_mode    = ssl.CERT_NONE
except Exception:
    _CTX = None

# ─── COLORES GFP (fondo blanco · azul · rojo institucional) ───────────────────
C = {
    "bg":      "#FFFFFF", "panel":  "#F4F6F8", "card":   "#FFFFFF",
    "card2":   "#E8EEF4", "sel":    "#2F5F8F", "hover":  "#D6E4F0",
    "verde":   "#2F5F8F", "verde2": "#3A7CA5", "texto":  "#1A2B3C",
    "dim":     "#5A6B7D", "borde":  "#B8C8D8", "rojo":   "#C41E3A",
    "rojo2":   "#E30613",
    "amarillo":"#D35400", "azul":   "#2F5F8F", "azul2":  "#3A7CA5",
    "header":  "#2F5F8F", "header2": "#C41E3A", "sep":    "#D0DCE8",
    "log":     "#F0F4F8", "purp":   "#6C3483", "teal":   "#148F77",
    "grid":    "#DDE4EC",
}
BUFFER_KM_DEFAULT = 1.5
BUFFER_KM_MAX     = 25.0

# ─── ENDPOINTS STAC ───────────────────────────────────────────────────────────
E84_SEARCH  = "https://earth-search.aws.element84.com/v1/search"
MPC_SEARCH  = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
CDSE_SEARCH = "https://catalogue.dataspace.copernicus.eu/stac/search"
MPC_TILER  = "https://planetarycomputer.microsoft.com/api/data/v1/item"
UA          = "ATD-Toolbox/GFP-Subnacional"
TIMEOUT     = 25
STAC_TIMEOUT = 55
RENDER_SIZE = 1024
RENDER_SIZE_EXPORT = 4096
MPC_SIGN_API = "https://planetarycomputer.microsoft.com/api/sas/v1/sign"
TITILER_COG = "https://titiler.xyz/cog/bbox"
_IMG_CACHE = {}
_IMG_CACHE_MAX = 32

_PERU_XFORMS = [
    "",
    "WGS_1984_(ITRF08)_To_SIRGAS_2000",
    "PSAD_1956_To_WGS_1984_3",
    "WGS_1984_To_WGS_1984",
]

# ─── COMBINACIONES DE BANDAS ──────────────────────────────────────────────────
BANDAS_S2 = [
    {
        "nombre":  "Color Natural (B04,B03,B02)",
        "codigo":  "B04, B03, B02",
        "desc":    "RGB estándar. Suelo = marrón, vegetación = verde, agua = azul oscuro.",
        "uso":     "Fotointerpretación visual básica.",
        "color":   "#3498DB",
        "s2_key":  "visual",
        "landsat": "B4, B3, B2",
    },
    {
        "nombre":  "SWIR-NIR-Rojo ★ (B11,B8A,B04)",
        "codigo":  "B11, B8A, B04",
        "desc":    "Suelo deforestado = ROJO brillante, vegetación sana = verde.",
        "uso":     "PRINCIPAL para GFP — detecta cortas y degradación.",
        "color":   "#E74C3C",
        "s2_key":  "rendered_preview",
        "landsat": "B6, B5, B4",
    },
    {
        "nombre":  "Infrarrojo Falso (B08,B04,B03)",
        "codigo":  "B08, B04, B03",
        "desc":    "Vegetación = rojo/magenta intenso. Agua = negro.",
        "uso":     "Distinguir tipos de cobertura vegetal.",
        "color":   "#8E44AD",
        "s2_key":  "rendered_preview",
        "landsat": "B5, B4, B3",
    },
    {
        "nombre":  "Agricultura (B12,B11,B08)",
        "codigo":  "B12, B11, B08",
        "desc":    "Cultivos activos = verde brillante. Vegetación = naranja/amarillo.",
        "uso":     "Diferenciar agrícola vs bosque.",
        "color":   "#27AE60",
        "s2_key":  "rendered_preview",
        "landsat": "B7, B6, B5",
    },
    {
        "nombre":  "NDVI (B08-B04)/(B08+B04)",
        "codigo":  "(B08-B04)/(B08+B04)",
        "desc":    "Valores -1 a +1. >0.5 = vegetación densa. <0.2 = suelo/agua.",
        "uso":     "Cuantificar salud vegetal. ArcGIS Pro: Imagery → Indices → NDVI.",
        "color":   "#1E8449",
        "s2_key":  "rendered_preview",
        "landsat": "(B5-B4)/(B5+B4)",
    },
    {
        "nombre":  "NBR quemas (B08-B12)/(B08+B12)",
        "codigo":  "(B08-B12)/(B08+B12)",
        "desc":    "Detecta áreas quemadas. Valores bajos = quema reciente.",
        "uso":     "Identificar quemas. ArcGIS Pro: Raster Calculator.",
        "color":   "#7B241C",
        "s2_key":  "rendered_preview",
        "landsat": "(B5-B7)/(B5+B7)",
    },
    {
        "nombre":  "Landsat SWIR (B6,B5,B4)",
        "codigo":  "B6, B5, B4",
        "desc":    "Equivalente SWIR-NIR-Rojo S2. Resolución 30m.",
        "uso":     "GFP cuando no hay S2 disponible.",
        "color":   "#E67E22",
        "s2_key":  "rendered_preview",
        "landsat": "B6, B5, B4",
    },
]

BANDA_DEFAULT_IDX = 0

# ─── HTTP ─────────────────────────────────────────────────────────────────────

def _urlopen(req, timeout=TIMEOUT):
    try:
        return urllib.request.urlopen(req, timeout=timeout, context=_CTX)
    except TypeError:
        return urllib.request.urlopen(req, timeout=timeout)

def http_get(url):
    r = urllib.request.Request(url, headers={"User-Agent": UA,
                                              "Accept": "application/json"})
    with _urlopen(r) as resp:
        return json.loads(resp.read().decode())

def http_post(url, body, timeout=None):
    data = json.dumps(body).encode()
    r = urllib.request.Request(url, data=data, headers={
        "User-Agent": UA, "Content-Type": "application/json",
        "Accept": "application/geo+json, application/json"})
    with _urlopen(r, timeout=timeout or TIMEOUT) as resp:
        return json.loads(resp.read().decode())

def _bytes_son_imagen(data):
    if not data or len(data) < 12:
        return False
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return True
    if data[:3] == b"\xff\xd8\xff":
        return True
    return False


def _bytes_a_pil(data, size_px=None):
    """Convierte bytes PNG/JPEG a PIL RGB."""
    from PIL import Image
    if not _bytes_son_imagen(data):
        return None
    img = Image.open(io.BytesIO(data)).convert("RGB")
    if size_px and max(img.size) > size_px:
        rs = getattr(Image, "LANCZOS", getattr(Image, "BICUBIC", Image.BILINEAR))
        img = img.resize((size_px, size_px), rs)
    return img


def http_bytes(url, max_mb=30, timeout=None):
    r = urllib.request.Request(url, headers={"User-Agent": UA})
    with _urlopen(r, timeout=timeout or TIMEOUT) as resp:
        data = b""
        limit = max_mb * 1024 * 1024
        while True:
            chunk = resp.read(262144)
            if not chunk:
                break
            data += chunk
            if len(data) > limit:
                break
        return data


def _sign_mpc_href(href):
    """Firma URLs de assets MPC (Azure Blob) para descarga sin 404."""
    if not href or not isinstance(href, str):
        return href
    low = href.lower()
    if "sig=" in low or "se=" in low:
        return href
    if ("blob.core.windows.net" not in low
            and "planetarycomputer.microsoft.com" not in low):
        return href
    try:
        q = urllib.parse.urlencode({"href": href})
        data = http_get(f"{MPC_SIGN_API}?{q}")
        return data.get("href") or href
    except Exception:
        return href


def _sign_mpc_features(feats):
    """Firma solo preview principal (rápido; no todos los assets)."""
    out = []
    for f in feats or []:
        nf = dict(f)
        assets = dict(f.get("assets", {}) or {})
        for key in ("rendered_preview", "visual", "visual_tci", "thumbnail"):
            if key in assets and isinstance(assets[key], dict):
                href = assets[key].get("href")
                if href:
                    assets[key] = dict(assets[key])
                    assets[key]["href"] = _sign_mpc_href(href)
                    break
        nf["assets"] = assets
        out.append(nf)
    return out


def _img_cache_key(esc_id, banda_idx, buffer_km, lado, bbox_wgs84):
    bb = tuple(round(x, 5) for x in (bbox_wgs84 or []))
    return f"v2|{esc_id}|{banda_idx}|{buffer_km:.2f}|{lado}|{bb}"


def _img_cache_get(key):
    return _IMG_CACHE.get(key)


def _img_cache_put(key, pil_img):
    if key in _IMG_CACHE:
        return
    while len(_IMG_CACHE) >= _IMG_CACHE_MAX:
        _IMG_CACHE.pop(next(iter(_IMG_CACHE)))
    try:
        _IMG_CACHE[key] = pil_img.copy()
    except Exception:
        _IMG_CACHE[key] = pil_img


def _utm_epsg_from_wkt(sr_wkt):
    """EPSG UTM Sur Perú: 18 (Loreto) o 19 (Cuzco) según central meridian."""
    if not sr_wkt:
        return 32718
    s = str(sr_wkt).upper()
    if "ZONE 19" in s or "19S" in s or "CM 75" in s:
        return 32719
    if "ZONE 18" in s or "18S" in s or "CM 69" in s:
        return 32718
    return 32718


# ─── RESOLVER URLs S3 ─────────────────────────────────────────────────────────

def _err_msg(exc):
    if exc is None:
        return "error desconocido"
    txt = str(exc).strip()
    if txt and txt.lower() != "none":
        return txt
    reason = getattr(exc, "reason", None)
    if reason:
        return str(reason)
    return type(exc).__name__


def _url_preview_landsat(href_raw, fuente=""):
    """USGS Landsat público vía landsatlook; MPC vía firma SAS."""
    if not href_raw:
        return None
    if str(href_raw).startswith("s3://usgs-landsat/"):
        try:
            key = str(href_raw).split("collection02/", 1)[1]
            return f"https://landsatlook.usgs.gov/data/collection02/{key}"
        except Exception:
            pass
    if str(href_raw).startswith(("http://", "https://")):
        low = href_raw.lower()
        if "landsatlook.usgs.gov" in low:
            return href_raw
        if fuente == "MPC" or "planetarycomputer" in low or "blob.core.windows.net" in low:
            return _sign_mpc_href(href_raw)
        return href_raw
    resolved = _resolver_url_asset(href_raw)
    return resolved


def _resolver_url_asset(href, collection=""):
    if not href:
        return None
    resolved = None
    if href.startswith("https://") or href.startswith("http://"):
        resolved = href
    elif href.startswith("s3://"):
        parts = href[5:].split("/", 1)
        if len(parts) == 2:
            bucket, key = parts
            if bucket == "usgs-landsat":
                if "collection02/" in key:
                    resolved = (
                        "https://landsatlook.usgs.gov/data/collection02/"
                        + key.split("collection02/", 1)[1]
                    )
                else:
                    resolved = f"https://landsatlook.usgs.gov/data/{key}"
            else:
                resolved = f"https://{bucket}.s3.us-west-2.amazonaws.com/{key}"
    if resolved:
        return _sign_mpc_href(resolved)
    return None


def _http_resp_es_imagen(data):
    """Rechaza páginas HTML (landsatlook a veces devuelve HTML en vez de JPEG)."""
    if not data or len(data) < 24:
        return False
    head = data[:16].lstrip().lower()
    if head.startswith((b"<!doc", b"<html", b"<?xml")):
        return False
    return (
        data[:3] == b"\xff\xd8\xff"
        or data[:8] == b"\x89PNG\r\n\x1a\n"
        or data[:4] == b"GIF8"
    )


def _mejor_preview_landsat(assets, fuente=""):
    orden = [
        "reduced_resolution_browse", "thumbnail",
        "rendered_preview", "overview",
    ]
    for k in orden:
        if k in assets:
            href_raw = assets[k].get("href", "")
            href = _url_preview_landsat(href_raw, fuente)
            if href and not str(href).lower().split("?")[0].endswith(
                    (".tif", ".tiff")):
                return href, k
    for k, v in assets.items():
        if isinstance(v, dict):
            href = _url_preview_landsat(v.get("href", ""), fuente)
            if href:
                return href, k
    return None, "none"


def _landsat_plataforma_ok(props, sat):
    plat = str(props.get("platform", "") or "").lower().replace("_", "-")
    if "9" in sat:
        return "landsat-9" in plat or plat == "lc09"
    return "landsat-8" in plat or plat == "lc08"


def _mejor_preview_s2(assets, banda_key="visual"):
    orden_pref = [banda_key, "rendered_preview", "visual", "visual_tci", "overview", "thumbnail"]
    seen = set()
    orden_final = []
    for k in orden_pref:
        if k not in seen:
            seen.add(k)
            orden_final.append(k)

    for k in orden_final:
        if k in assets:
            href = assets[k].get("href", "")
            if href and href.startswith("http"):
                ext = href.split("?")[0].lower()
                if not ext.endswith((".tif", ".tiff", ".geotiff")):
                    return href, k
    return None, "none"


def _asset_keys(assets):
    try:
        return set(assets.keys())
    except Exception:
        return set()


def _stac_asset_href(assets, *candidatos):
    if not assets:
        return None
    lower = {str(k).lower(): k for k in assets.keys()}
    for cand in candidatos:
        if cand in assets and isinstance(assets[cand], dict):
            href = assets[cand].get("href", "")
            if href:
                return href
        ck = str(cand).lower()
        if ck in lower and isinstance(assets[lower[ck]], dict):
            href = assets[lower[ck]].get("href", "")
            if href:
                return href
    return None


def _url_cog_publico(href):
    """Convierte s3:// a HTTPS para Titiler (E84 Sentinel/Landsat)."""
    if not href:
        return None
    if str(href).startswith(("http://", "https://")):
        return href
    return _resolver_url_asset(href) or href


def _titiler_cog_bbox_url(cog_url, bbox_wgs84, size=RENDER_SIZE, rescale=None):
    """Render HD desde COG publico (E84/AWS) cuando MPC tiler devuelve 404."""
    cog_url = _url_cog_publico(cog_url)
    if not cog_url or not bbox_wgs84 or len(bbox_wgs84) != 4:
        return None
    x0, y0, x1, y1 = bbox_wgs84
    base = (
        f"{TITILER_COG}/{x0:.8f},{y0:.8f},{x1:.8f},{y1:.8f}/"
        f"{int(size)}x{int(size)}.png"
    )
    params = [("url", cog_url), ("resampling", "lanczos")]
    if rescale:
        params.append(("rescale", rescale))
    return base + "?" + urllib.parse.urlencode(params)


def _pick_asset(keys, *candidates):
    keys_l = {str(k).lower(): k for k in keys}
    for cand in candidates:
        if cand in keys:
            return cand
        ck = str(cand).lower()
        if ck in keys_l:
            return keys_l[ck]
    return None


def _es_banda_indice(banda_idx):
    n = BANDAS_S2[banda_idx]["nombre"].lower()
    return "ndvi" in n or "nbr" in n


def _band_recipe(tipo, asset_keys, banda_idx):
    keys = asset_keys or set()
    nombre = BANDAS_S2[banda_idx]["nombre"].lower()

    if tipo == "landsat":
        red   = _pick_asset(keys, "red", "SR_B4", "B4") or "red"
        green = _pick_asset(keys, "green", "SR_B3", "B3") or "green"
        blue  = _pick_asset(keys, "blue", "SR_B2", "B2") or "blue"
        nir   = _pick_asset(keys, "nir08", "nir", "SR_B5", "B5") or "nir08"
        sw1   = _pick_asset(keys, "swir16", "swir1", "SR_B6", "B6") or "swir16"
        sw2   = _pick_asset(keys, "swir22", "swir2", "SR_B7", "B7") or "swir22"
    else:
        red   = _pick_asset(keys, "B04", "red") or "B04"
        green = _pick_asset(keys, "B03", "green") or "B03"
        blue  = _pick_asset(keys, "B02", "blue") or "B02"
        nir   = _pick_asset(keys, "B08", "nir", "nir08") or "B08"
        nir8a = _pick_asset(keys, "B8A", "nir09", "nir8a") or "B8A"
        sw1   = _pick_asset(keys, "B11", "swir16", "swir1") or "B11"
        sw2   = _pick_asset(keys, "B12", "swir22", "swir2") or "B12"

    if "color natural" in nombre:
        if "visual" in keys:
            return {"assets": ["visual"], "nodata": "0", "natural": True}
        return {
            "assets": [red, green, blue],
            "nodata": "0",
            "rescale": "0,3000",
            "color_formula": "Gamma RGB 3.2 Saturation 0.8 Sigmoidal RGB 25 0.35",
            "natural": True,
        }

    if "ndvi" in nombre and red and nir:
        return {
            "assets": [nir, red],
            "expression": f"({nir}-{red})/({nir}+{red})",
            "rescale": "-0.2,0.9",
            "colormap_name": "rdylgn",
            "unscale": True,
            "nodata": "0",
            "index": True,
        }
    if "nbr" in nombre and nir and sw2:
        return {
            "assets": [nir, sw2],
            "expression": f"({nir}-{sw2})/({nir}+{sw2})",
            "rescale": "-0.5,0.8",
            "colormap_name": "rdylgn",
            "unscale": True,
            "nodata": "0",
            "index": True,
        }
    if "swir-nir" in nombre and sw1 and (nir8a or nir) and red:
        return {
            "assets": [sw1, nir8a or nir, red],
            "rescale": "0,0.4" if tipo == "landsat" else "0,4000",
            "nodata": "0",
            "unscale": tipo == "landsat",
            "color_formula": "Gamma RGB 2.2 Saturation 1.1 Sigmoidal RGB 15 0.4",
        }
    if "infrarrojo" in nombre and nir and red and green:
        return {
            "assets": [nir, red, green],
            "rescale": "0,0.35" if tipo == "landsat" else "0,3500",
            "nodata": "0",
            "unscale": tipo == "landsat",
            "color_formula": "Gamma RGB 2.2 Saturation 1.1 Sigmoidal RGB 15 0.4",
        }
    if "agricultura" in nombre and sw2 and sw1 and nir:
        return {
            "assets": [sw2, sw1, nir],
            "rescale": "0,0.4" if tipo == "landsat" else "0,4500",
            "nodata": "0",
            "unscale": tipo == "landsat",
            "color_formula": "Gamma RGB 2.2 Saturation 1.1 Sigmoidal RGB 15 0.4",
        }
    if "landsat swir" in nombre and sw1 and nir and red:
        return {
            "assets": [sw1, nir, red],
            "rescale": "0,0.4" if tipo == "landsat" else "0,4000",
            "nodata": "0",
            "unscale": tipo == "landsat",
            "color_formula": "Gamma RGB 2.2 Saturation 1.1 Sigmoidal RGB 15 0.4",
        }
    if red and green and blue:
        if tipo == "landsat":
            return {
                "assets": [red, green, blue],
                "rescale": "0,10000",
                "nodata": "0",
                "natural": True,
                "natural_visual_only": True,
            }
        return {
            "assets": [red, green, blue],
            "rescale": "0,3000",
            "nodata": "0",
            "color_formula": "Gamma RGB 3.2 Saturation 0.8 Sigmoidal RGB 25 0.35",
            "natural": True,
        }
    return None


def _pc_bbox_render_url(collection, item_id, bbox_wgs84, recipe, size=RENDER_SIZE):
    if not collection or not item_id or not bbox_wgs84 or not recipe:
        return None
    x0, y0, x1, y1 = bbox_wgs84
    bbox_txt = f"{x0:.8f},{y0:.8f},{x1:.8f},{y1:.8f}"
    base = f"{MPC_TILER}/bbox/{bbox_txt}/{int(size)}x{int(size)}.png"
    params = [
        ("collection", collection),
        ("item", item_id),
        ("format", "png"),
        ("resampling", "bilinear"),
    ]
    if recipe.get("nodata") is not None:
        params.append(("nodata", str(recipe["nodata"])))
    if recipe.get("unscale"):
        params.append(("unscale", "true"))
    if recipe.get("expression"):
        params.append(("expression", recipe["expression"]))
        for a in recipe.get("assets", []):
            params.append(("assets", a))
    else:
        for a in recipe.get("assets", []):
            params.append(("assets", a))
        cf = recipe.get("color_formula")
        if cf and not recipe.get("natural_visual_only"):
            params.append(("color_formula", cf))
    if recipe.get("rescale"):
        params.append(("rescale", recipe["rescale"]))
    if recipe.get("colormap_name"):
        params.append(("colormap_name", recipe["colormap_name"]))
    return base + "?" + urllib.parse.urlencode(params, doseq=True)


def _render_url_para_escena(esc, bbox_wgs84, banda_idx, size=RENDER_SIZE):
    api = str(esc.get("api", "")).upper()
    es_idx = _es_banda_indice(banda_idx)
    nombre = BANDAS_S2[banda_idx]["nombre"].lower()

    # Landsat: MPC tiler RGB (30 m HD); browse JPEG solo como respaldo
    if esc.get("tipo") == "landsat":
        if esc.get("prev_tipo") == "wms_gibs" and esc.get("prev"):
            return esc["prev"], "wms_gibs"
        keys = set(esc.get("asset_keys") or [])
        recipe = _band_recipe("landsat", keys, banda_idx)
        if recipe and esc.get("id") and esc.get("collection"):
            url = _pc_bbox_render_url(
                esc["collection"], esc["id"], bbox_wgs84, recipe, size=size)
            if url:
                return url, "mpc_landsat_rgb"
        if not es_idx:
            prev = esc.get("preview_href") or esc.get("prev")
            if prev and not str(prev).lower().split("?")[0].endswith(
                    (".tif", ".tiff")):
                return prev, "preview_browse"
            fecha = esc.get("fecha", "")
            sensor = "L9" if "9" in str(esc.get("sat", "")) else "L8"
            wms = _landsat_wms_url(
                bbox_wgs84, fecha, sensor=sensor, size=size)
            if wms:
                return wms, "wms_gibs"
        return None, "sin_preview"

    # E84/CDSE Sentinel-2: Titiler COG (no usar thumbnail como render HD)
    if esc.get("tipo") == "s2" and api in ("E84", "CDSE") and not es_idx:
        cog = _url_cog_publico(esc.get("cog_visual") or "")
        if cog and str(cog).lower().endswith((".tif", ".tiff")):
            turl = _titiler_cog_bbox_url(cog, bbox_wgs84, size)
            if turl:
                return turl, "titiler_tci"
        return None, "sin_cog"

    # E84/CDSE otros: MPC tiler suele dar 404 con el mismo item-id → Titiler COG
    if api in ("E84", "CDSE") and not es_idx:
        cog = esc.get("cog_visual") or ""
        if cog and (
            "color natural" in nombre
            or banda_idx == BANDA_DEFAULT_IDX
            or "infrarrojo falso" in nombre
        ):
            turl = _titiler_cog_bbox_url(cog, bbox_wgs84, size)
            if turl:
                return turl, "titiler_tci"
        prev = esc.get("preview_href") or esc.get("prev")
        if prev and not str(prev).lower().endswith((".tif", ".tiff")):
            return prev, "preview_direct"

    recipe = _band_recipe(esc.get("tipo", ""), set(esc.get("asset_keys", [])), banda_idx)
    if not recipe:
        return None, "sin_bandas"
    url = _pc_bbox_render_url(esc.get("collection"), esc.get("id"),
                              bbox_wgs84, recipe, size=size)
    if recipe.get("natural") and recipe.get("assets") == ["visual"]:
        tipo = "pc_visual_tci"
    elif recipe.get("index"):
        tipo = "pc_index"
    else:
        tipo = "pc_bbox_10m" if esc.get("tipo") == "s2" else "pc_bbox_30m"
    return url, tipo


# ─── WMS FALLBACK PARA LANDSAT ────────────────────────────────────────────────

def _landsat_bboxes_render(esc, alert_bbox_wgs84):
    """Bboxes a probar: alerta primero, luego tile completo STAC."""
    out = []
    seen = set()
    if alert_bbox_wgs84 and alert_bbox_wgs84 != [0, 0, 0, 0]:
        key = tuple(round(x, 5) for x in alert_bbox_wgs84)
        out.append(alert_bbox_wgs84)
        seen.add(key)
    esc_bb = esc.get("bbox") or []
    if esc_bb and len(esc_bb) == 4 and esc_bb != [0, 0, 0, 0]:
        ex0, ey0, ex1, ey1 = esc_bb
        pad = 0.015
        tile_bb = [ex0 - pad, ey0 - pad, ex1 + pad, ey1 + pad]
        key = tuple(round(x, 5) for x in tile_bb)
        if key not in seen:
            out.append(tile_bb)
    return out


def _landsat_mpc_rgb_url(esc, bbox_wgs84, recipe, size=RENDER_SIZE):
    if not esc.get("id") or not esc.get("collection") or not recipe:
        return None
    return _pc_bbox_render_url(
        esc["collection"], esc["id"], bbox_wgs84, recipe, size=size)


def _descargar_landsat_mpc(esc, alert_bbox, banda_idx=0, size=RENDER_SIZE):
    """
    Landsat RGB vía MPC: prueba bbox alerta y tile STAC; recorta al buffer.
    """
    keys = set(esc.get("asset_keys") or [])
    recipes = []
    main = _band_recipe("landsat", keys, banda_idx)
    if main:
        recipes.append(main)
    red = _pick_asset(keys, "red", "SR_B4", "B4") or "red"
    green = _pick_asset(keys, "green", "SR_B3", "B3") or "green"
    blue = _pick_asset(keys, "blue", "SR_B2", "B2") or "blue"
    recipes.append({
        "assets": [red, green, blue],
        "rescale": "0,10000",
        "nodata": "0",
        "natural_visual_only": True,
    })
    bboxes = _landsat_bboxes_render(esc, alert_bbox)
    for recipe in recipes:
        for bbox_try in bboxes:
            url = _landsat_mpc_rgb_url(esc, bbox_try, recipe, size=size)
            if not url:
                continue
            img = _descargar_imagen_render(
                url, size, es_indice=False, es_landsat=True)
            if img is None:
                continue
            if (bbox_try is not alert_bbox and alert_bbox
                    and alert_bbox != [0, 0, 0, 0]):
                cropped, ok = crop_thumbnail_a_bbox(
                    img, bbox_try, alert_bbox, out_size=size)
                if ok:
                    return cropped, "mpc_landsat_rgb"
            else:
                return img, "mpc_landsat_rgb"
    return None, ""


def _landsat_wms_url(bbox_wgs84, fecha_str, sensor="L8", size=1024):
    if not bbox_wgs84 or bbox_wgs84 == [0,0,0,0]:
        return None
    x0, y0, x1, y1 = bbox_wgs84
    pad = 0.05
    x0 -= pad; y0 -= pad; x1 += pad; y1 += pad
    # Capas USGS_Landsat_* retiradas de GIBS; HLS L30 = Landsat 30 m
    layer_gibs = "HLS_L30_Nadir_BRDF_Adjusted_Reflectance"
    base = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"
    params = urllib.parse.urlencode({
        "SERVICE": "WMS", "VERSION": "1.1.1", "REQUEST": "GetMap",
        "FORMAT": "image/png", "LAYERS": layer_gibs, "SRS": "EPSG:4326",
        "BBOX": f"{y0},{x0},{y1},{x1}", "WIDTH": size, "HEIGHT": size,
        "TIME": fecha_str, "TRANSPARENT": "true",
    })
    return f"{base}?{params}"


def _sentinel_wms_url(bbox_wgs84, fecha_str, size=512):
    if not bbox_wgs84 or bbox_wgs84 == [0,0,0,0]:
        return None
    x0, y0, x1, y1 = bbox_wgs84
    pad = 0.02
    x0 -= pad; y0 -= pad; x1 += pad; y1 += pad
    base = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"
    params = urllib.parse.urlencode({
        "SERVICE": "WMS", "VERSION": "1.1.1", "REQUEST": "GetMap",
        "FORMAT": "image/png", "LAYERS": "Sentinel-2_L2A_True-Color",
        "SRS": "EPSG:4326", "BBOX": f"{y0},{x0},{y1},{x1}",
        "WIDTH": size, "HEIGHT": size, "TIME": fecha_str, "TRANSPARENT": "true",
    })
    return f"{base}?{params}"


# ─── BBOX CON BUFFER ──────────────────────────────────────────────────────────

def _parse_float_locale(valor):
    """Acepta 1.5 y 1,5 (configuración regional Windows / Tk Spinbox)."""
    if valor is None:
        return None
    s = str(valor).strip()
    if not s:
        return None
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _normalizar_buffer_km(valor):
    """
    Buffer en kilómetros (máx 25).
    Si el usuario escribe >100 asume metros (ej. 4000 → 4 km).
    """
    v = _parse_float_locale(valor)
    if v is None:
        return BUFFER_KM_DEFAULT
    if v > 100:
        v = v / 1000.0
    return max(0.2, min(v, BUFFER_KM_MAX))


def _bbox_con_buffer_km(bbox_wgs84, buffer_km=1.5):
    buffer_km = _normalizar_buffer_km(buffer_km)
    if not bbox_wgs84 or bbox_wgs84 == [0, 0, 0, 0]:
        return bbox_wgs84
    x0, y0, x1, y1 = bbox_wgs84
    cx = (x0 + x1) / 2
    cy = (y0 + y1) / 2
    d_lat = buffer_km / 111.0
    d_lon = buffer_km / (111.0 * math.cos(math.radians(cy)))
    return [cx - d_lon, cy - d_lat, cx + d_lon, cy + d_lat]


def _bbox_tile_desde_id_s2(scene_id, esc_bbox_stac):
    if esc_bbox_stac and len(esc_bbox_stac) == 4:
        x0, y0, x1, y1 = esc_bbox_stac
        ancho = abs(x1 - x0)
        alto  = abs(y1 - y0)
        if ancho > 0.5 and alto > 0.5:
            return esc_bbox_stac
    return None


def _imagen_rgb_valida(pil_img, min_span=12, es_landsat=False):
    """Detecta PNG corrupto, negro, blanco o rescale incorrecto."""
    try:
        img = pil_img.convert("RGB")
        ext = img.getextrema()
        span = max(ext[i][1] - ext[i][0] for i in range(3))
        if ext[0][1] == 0 and ext[1][1] == 0 and ext[2][1] == 0:
            return False
        if es_landsat:
            if span < 8:
                return False
            if (ext[0][0] >= 250 and ext[1][0] >= 250 and ext[2][0] >= 250
                    and span < 20):
                return False
            return span >= max(min_span, 8)
        return span >= min_span
    except Exception:
        return False


def _preparar_imagen_visor(pil_img, es_indice=False):
    """
    RGB natural: sin autocontrast (destruye colores reales).
    Índices (NDVI/NBR): ajuste suave sobre colormap.
    """
    try:
        from PIL import Image, ImageEnhance
        img = pil_img.convert("RGB")
        if es_indice:
            img = ImageEnhance.Contrast(img).enhance(1.22)
            return ImageEnhance.Color(img).enhance(1.12)
        return ImageEnhance.Brightness(img).enhance(1.03)
    except Exception:
        return pil_img.convert("RGB") if pil_img else pil_img


def _descargar_imagen_render(
        render_url, size_px=RENDER_SIZE, es_indice=False, es_landsat=False):
    """Descarga PNG/JPEG desde tiler MPC, Titiler o preview STAC."""
    if not render_url:
        return None
    low = str(render_url).lower()
    firmar = (
        "planetarycomputer.microsoft.com" in low
        or "blob.core.windows.net" in low
    )
    url_get = _sign_mpc_href(render_url) if firmar else render_url
    try:
        data = http_bytes(url_get, max_mb=25, timeout=STAC_TIMEOUT)
    except Exception:
        return None
    img = _bytes_a_pil(data, size_px=size_px)
    if img is None:
        return None
    if es_indice:
        min_span = 4
    elif es_landsat:
        min_span = 3
    else:
        min_span = 8
    if not _imagen_rgb_valida(
            img, min_span=min_span, es_landsat=es_landsat):
        return None
    return img


def _quemar_vectores_en_pil(pil_img, bbox_wgs84, poly_sel, polys_vec,
                            cod="", show_sel=True, show_neighbors=True):
    """Dibuja polígonos sobre la imagen exportada (misma extensión WGS84)."""
    if not bbox_wgs84 or len(bbox_wgs84) != 4:
        return pil_img
    x0, y0, x1, y1 = bbox_wgs84
    if x1 <= x0 or y1 <= y0:
        return pil_img
    try:
        from PIL import ImageDraw
        img = pil_img.convert("RGBA")
        draw = ImageDraw.Draw(img, "RGBA")
        W, H = img.size

        def _pts(poly):
            out = []
            for lon, lat in poly or []:
                px = (lon - x0) / (x1 - x0) * W
                py = (y1 - lat) / (y1 - y0) * H
                out.append((px, py))
            return out

        if show_neighbors:
            for poly in polys_vec or []:
                pts = _pts(poly)
                if len(pts) >= 3:
                    draw.polygon(pts, fill=(36, 113, 163, 45),
                                 outline=(36, 113, 163, 200))
        if show_sel and poly_sel:
            pts = _pts(poly_sel)
            if len(pts) >= 3:
                draw.polygon(pts, fill=(227, 30, 58, 55),
                             outline=(227, 6, 19, 255))
                cx = sum(p[0] for p in pts) / len(pts)
                cy = sum(p[1] for p in pts) / len(pts)
                if cod:
                    draw.text((cx - 18, cy - 22), str(cod),
                              fill=(180, 0, 0, 255))
        return img.convert("RGB")
    except Exception:
        return pil_img


def _finalizar_imagen_visor(img, esc, bbox_alerta, size_px=RENDER_SIZE,
                            render_tipo=None):
    """
    Centra la imagen en la alerta (Landsat: tile diagonal → recorte).
    Devuelve (imagen, crop_ok).
    """
    if img is None:
        return None, False
    tipo_render = str(render_tipo or esc.get("prev_tipo") or "")
    bbox_alerta = bbox_alerta or []
    if tipo_render in (
        "titiler_tci", "titiler_ls", "wms_gibs", "mpc_landsat_rgb",
        "pc_bbox_30m", "pc_bbox_10m", "pc_visual_tci", "pc_index",
    ):
        if bbox_alerta and bbox_alerta != [0, 0, 0, 0]:
            esc["img_bbox_wgs84"] = bbox_alerta
        return img, True
    esc_bbox = esc.get("bbox") or []
    if (bbox_alerta and bbox_alerta != [0, 0, 0, 0]
            and esc_bbox and len(esc_bbox) == 4
            and esc_bbox != [0, 0, 0, 0]):
        cropped, ok = crop_thumbnail_a_bbox(
            img, esc_bbox, bbox_alerta, out_size=size_px)
        if ok:
            esc["img_bbox_wgs84"] = bbox_alerta
            return cropped, True
    if bbox_alerta and bbox_alerta != [0, 0, 0, 0]:
        esc["img_bbox_wgs84"] = bbox_alerta
    return img, False


def crop_thumbnail_a_bbox(img, esc_bbox, alert_bbox_wgs84, out_size=2048):
    try:
        from PIL import Image
        W, H = img.size
        if (esc_bbox and len(esc_bbox) == 4 and
                esc_bbox != [0, 0, 0, 0] and
                alert_bbox_wgs84 and alert_bbox_wgs84 != [0, 0, 0, 0]):
            ex0, ey0, ex1, ey1 = esc_bbox
            ax0, ay0, ax1, ay1 = alert_bbox_wgs84
            esc_ancho   = abs(ex1 - ex0)
            alert_ancho = abs(ax1 - ax0)
            if esc_ancho > alert_ancho * 2:
                px0 = int((ax0 - ex0) / (ex1 - ex0) * W)
                px1 = int((ax1 - ex0) / (ex1 - ex0) * W)
                py0 = int((ey1 - ay1) / (ey1 - ey0) * H)
                py1 = int((ey1 - ay0) / (ey1 - ey0) * H)
                px0 = max(0, min(px0, W - 1))
                px1 = max(px0 + 2, min(px1, W))
                py0 = max(0, min(py0, H - 1))
                py1 = max(py0 + 2, min(py1, H))
                if (px1 - px0) > 2 and (py1 - py0) > 2:
                    cropped = img.crop((px0, py0, px1, py1))
                    rs = getattr(Image, "LANCZOS", getattr(Image, "BICUBIC", Image.BILINEAR))
                    return cropped.resize((out_size, out_size), rs), True
        rs = getattr(Image, "LANCZOS", getattr(Image, "BICUBIC", Image.BILINEAR))
        return img.resize((out_size, out_size), rs), False
    except Exception:
        try:
            from PIL import Image
            return img.resize((out_size, out_size), Image.BILINEAR), False
        except Exception:
            return img, False


# ─── PNG minimal (fallback) ──────────────────────────────────────────────────

def _png_1px(r, g, b):
    def u32(n): return struct.pack(">I", n)
    def chunk(t, d):
        c = zlib.crc32(t + d) & 0xFFFFFFFF
        return u32(len(d)) + t + d + u32(c)
    raw  = b"\x00" + bytes([r, g, b])
    comp = zlib.compress(raw)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", u32(1) + u32(1) + b"\x08\x02\x00\x00\x00")
            + chunk(b"IDAT", comp)
            + chunk(b"IEND", b""))


# ─── PROYECCION ROBUSTA A WGS84 ──────────────────────────────────────────────

def _proyectar_geom_wgs84(geom, sr_wgs):
    for xf in _PERU_XFORMS:
        try:
            geom_w = geom.projectAs(sr_wgs, xf) if xf else geom.projectAs(sr_wgs)
            pts = []
            for part in geom_w:
                for pnt in part:
                    if pnt:
                        pts.append((pnt.X, pnt.Y))
            if pts and (-180 <= pts[0][0] <= 180) and (-90 <= pts[0][1] <= 90):
                return pts, geom_w.extent
        except Exception:
            continue
    try:
        pts = []
        for part in geom:
            for pnt in part:
                if pnt and (-180 <= pnt.X <= 180) and (-90 <= pnt.Y <= 90):
                    pts.append((pnt.X, pnt.Y))
        if pts:
            return pts, geom.extent
    except Exception:
        pass
    return [], None


def _proyectar_punto_wgs84(x, y, sr_fc, sr_wgs):
    for xf in _PERU_XFORMS:
        try:
            g  = arcpy.PointGeometry(arcpy.Point(x, y), sr_fc)
            gw = g.projectAs(sr_wgs, xf) if xf else g.projectAs(sr_wgs)
            cx, cy = gw.centroid.X, gw.centroid.Y
            if (-180 <= cx <= 180) and (-90 <= cy <= 90):
                return cx, cy
        except Exception:
            continue
    if (-180 <= x <= 180) and (-90 <= y <= 90):
        return x, y
    return None, None


def _bbox_wgs84_a_sr(bbox_wgs84, sr_wkt):
    if not bbox_wgs84 or len(bbox_wgs84) != 4 or not sr_wkt:
        return None
    try:
        sr_wgs = arcpy.SpatialReference(4326)
        sr_out = arcpy.SpatialReference()
        sr_out.loadFromString(sr_wkt)
        x0, y0, x1, y1 = bbox_wgs84
        arr = arcpy.Array([
            arcpy.Point(x0, y0), arcpy.Point(x1, y0),
            arcpy.Point(x1, y1), arcpy.Point(x0, y1),
            arcpy.Point(x0, y0),
        ])
        poly = arcpy.Polygon(arr, sr_wgs)
        for xf in _PERU_XFORMS:
            try:
                geom = poly.projectAs(sr_out, xf) if xf else poly.projectAs(sr_out)
                ext = geom.extent
                return [ext.XMin, ext.YMin, ext.XMax, ext.YMax]
            except Exception:
                continue
    except Exception:
        pass
    return None


# ─── EXTRACCION DE DATOS DEL FC ───────────────────────────────────────────────

def extraer_vectores_fc(fc_path, where_clause="", acr_filtro=""):
    desc   = arcpy.Describe(fc_path)
    sr_fc  = desc.spatialReference
    sr_wgs = arcpy.SpatialReference(4326)

    campos_fc = {f.name.lower(): f.name for f in arcpy.ListFields(fc_path)}

    cod_fields = []
    for c in ["anp_codi", "cod_acr", "acr_codi", "codigo", "cod"]:
        if c in campos_fc:
            cod_fields.append(campos_fc[c])
    if not cod_fields:
        for f in arcpy.ListFields(fc_path):
            if f.type == "String" and f.name not in ("Shape", "GlobalID"):
                cod_fields.append(f.name)
                break

    nom_f = None
    for c in ["ac_nomb", "nombre", "acr_nomb", "nom"]:
        if c in campos_fc:
            nom_f = campos_fc[c]; break

    area_f = None
    for c in ["md_sup", "area_ha", "shape_area", "sup_ha"]:
        if c in campos_fc:
            area_f = campos_fc[c]; break

    leer = ["OID@", "SHAPE@"]
    for cf in cod_fields:
        if cf not in leer:
            leer.append(cf)
    if nom_f and nom_f not in leer:
        leer.append(nom_f)
    if area_f and area_f not in leer:
        leer.append(area_f)

    vectores = []
    wc = where_clause.strip() if where_clause else None
    cursor_kwargs = {}
    if wc:
        cursor_kwargs["where_clause"] = wc

    idx_cod = {leer[i]: i for i in range(len(leer))}
    idx_nom = idx_cod.get(nom_f) if nom_f else None
    idx_area = idx_cod.get(area_f) if area_f else None

    with arcpy.da.SearchCursor(fc_path, leer, **cursor_kwargs) as cur:
        for row in cur:
            oid  = row[0]
            geom = row[1]
            if geom is None:
                continue
            cod = ""
            for cf in cod_fields:
                v = row[idx_cod[cf]]
                if v is not None and str(v).strip():
                    cod = str(v).strip()
                    break
            nom = (
                str(row[idx_nom]).strip() if idx_nom is not None and row[idx_nom]
                else cod
            ) or cod
            area = row[idx_area] if idx_area is not None else None

            if not cod:
                cod = f"POL-{oid}"
            if not nom:
                nom = cod

            if acr_filtro and acr_filtro not in ("(Todos)", "(todos)", ""):
                af = acr_filtro.strip()
                if cod != af and not cod.endswith(af):
                    continue

            ext = geom.extent

            pts_wgs84  = []
            bbox_wgs84 = [0, 0, 0, 0]
            try:
                pts_wgs84, ext_w = _proyectar_geom_wgs84(geom, sr_wgs)
                if pts_wgs84 and ext_w:
                    pad_x = max((ext_w.XMax - ext_w.XMin) * 0.1, 0.001)
                    pad_y = max((ext_w.YMax - ext_w.YMin) * 0.1, 0.001)
                    bbox_wgs84 = [ext_w.XMin - pad_x, ext_w.YMin - pad_y,
                                  ext_w.XMax + pad_x, ext_w.YMax + pad_y]
            except Exception:
                pass

            pad_rx = max((ext.XMax - ext.XMin) * 0.22, 1.0)
            pad_ry = max((ext.YMax - ext.YMin) * 0.22, 1.0)
            bbox_fc_pad = [ext.XMin - pad_rx, ext.YMin - pad_ry,
                           ext.XMax + pad_rx, ext.YMax + pad_ry]

            bbox_stac = [0, 0, 0, 0]
            try:
                x0, y0 = _proyectar_punto_wgs84(ext.XMin, ext.YMin, sr_fc, sr_wgs)
                x1, y1 = _proyectar_punto_wgs84(ext.XMax, ext.YMax, sr_fc, sr_wgs)
                if None not in (x0, y0, x1, y1):
                    bbox_stac = [min(x0,x1), min(y0,y1), max(x0,x1), max(y0,y1)]
                elif -180 <= ext.XMin <= 180 and -90 <= ext.YMin <= 90:
                    bbox_stac = [ext.XMin, ext.YMin, ext.XMax, ext.YMax]
            except Exception:
                if -180 <= ext.XMin <= 180:
                    bbox_stac = [ext.XMin, ext.YMin, ext.XMax, ext.YMax]

            vectores.append({
                "uid":        f"{oid}_{len(vectores)}",
                "oid":        oid,
                "cod":        cod,
                "nom":        nom,
                "area":       area,
                "pts_wgs84":  pts_wgs84,
                "bbox_wgs84": bbox_wgs84,
                "bbox_fc_pad":bbox_fc_pad,
                "bbox_stac":  bbox_stac,
                "activo":     True,
            })

    sr_wkt = ""
    try:
        sr_wkt = sr_fc.exportToString()
    except Exception:
        pass

    return vectores, sr_wkt


def _refrescar_vista_arcgis():
    """Refresca mapa/TOC si la API existe (ArcMap); en Pro no hace falta y no falla."""
    for nombre in ("RefreshActiveView", "RefreshTOC"):
        fn = getattr(arcpy, nombre, None)
        if callable(fn):
            try:
                fn()
            except Exception:
                pass


def _alertas_activas_lista(vectores):
    """Alertas con checkbox activo en el visor."""
    return [v for v in (vectores or []) if v.get("activo", True)]


def _configurar_stretch_custom_capa(lyr):
    """Stretch RGB Custom (evita Percent Clip por defecto en ArcGIS Pro)."""
    if not lyr:
        return False
    try:
        sym = lyr.symbology
        if sym is None:
            return False
        r = sym.renderer
        if hasattr(r, "stretchType"):
            r.stretchType = "Custom"
        for attr_min, attr_max, vals_min, vals_max in [
            ("minValues", "maxValues", [1.0, 1.0, 1.0], [255.0, 255.0, 255.0]),
            ("customStretchMin", "customStretchMax", [1.0, 1.0, 1.0], [255.0, 255.0, 255.0]),
            ("customMinValues", "customMaxValues", [1.0, 1.0, 1.0], [255.0, 255.0, 255.0]),
        ]:
            if hasattr(r, attr_min):
                setattr(r, attr_min, vals_min)
            if hasattr(r, attr_max):
                setattr(r, attr_max, vals_max)
        if hasattr(r, "gamma"):
            r.gamma = [1.0, 1.0, 1.0]
        if hasattr(r, "useGamma"):
            r.useGamma = True
        sym.renderer = r
        lyr.symbology = sym
        return True
    except Exception:
        pass
    try:
        cim = lyr.getDefinition("V2")
        if cim is None:
            return False
        cz = getattr(cim, "colorizer", None)
        if cz is None and hasattr(cim, "renderer"):
            cz = getattr(cim.renderer, "colorizer", None)
        if cz is None:
            return False
        if hasattr(cz, "stretchType"):
            cz.stretchType = "esriRasterStretch_Custom"
        for attr_min, attr_max in [
            ("customMinValues", "customMaxValues"),
            ("minValues", "maxValues"),
        ]:
            if hasattr(cz, attr_min):
                setattr(cz, attr_min, [1.0, 1.0, 1.0])
            if hasattr(cz, attr_max):
                setattr(cz, attr_max, [255.0, 255.0, 255.0])
        if hasattr(cz, "gamma"):
            cz.gamma = [1.0, 1.0, 1.0]
        try:
            lyr.setDefinition(cim)
        except TypeError:
            lyr.setDefinition("V2", cim)
        return True
    except Exception as ex:
        arcpy.AddWarning(f"  Stretch Custom: {ex}")
    return False


def _crear_geotiff_gdal(arr_rgb, bbox_fc_pad, sr_wkt, ruta_tif):
    """GeoTIFF en un solo paso (GDAL) — mucho más rápido que CompositeBands x3."""
    try:
        from osgeo import gdal, osr
        import numpy as np
    except ImportError:
        return False
    try:
        H, W = arr_rgb.shape[0], arr_rgb.shape[1]
        xmin, ymin, xmax, ymax = bbox_fc_pad
        driver = gdal.GetDriverByName("GTiff")
        if driver is None:
            return False
        ds = driver.Create(
            ruta_tif, W, H, 3, gdal.GDT_Byte,
            options=["COMPRESS=LZW", "TILED=YES"],
        )
        if ds is None:
            return False
        px_w = (xmax - xmin) / max(W, 1)
        px_h = (ymax - ymin) / max(H, 1)
        ds.SetGeoTransform([xmin, px_w, 0, ymax, 0, -px_h])
        srs = osr.SpatialReference()
        if sr_wkt:
            srs.ImportFromWkt(sr_wkt)
        else:
            srs.ImportFromEPSG(4326)
        ds.SetProjection(srs.ExportToWkt())
        # PIL/fila 0 = norte (y_max); GDAL fila 0 = ymax en geotransform → sin flip.
        for i in range(3):
            ds.GetRasterBand(i + 1).WriteArray(arr_rgb[:, :, i])
        ds.FlushCache()
        del ds
        return True
    except Exception:
        return False


def crear_geotiff(img_bytes, bbox_fc_pad, sr_wkt, ruta_tif, pil_ok, tmp_dir,
                  target_size=None):
    try:
        import numpy as np
        xmin, ymin, xmax, ymax = bbox_fc_pad
        if pil_ok:
            from PIL import Image
            img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            W0, H0 = img.size
            OUT_SIZE = int(target_size or max(W0, H0, RENDER_SIZE))
            if W0 != OUT_SIZE or H0 != OUT_SIZE:
                rs = getattr(Image, "LANCZOS", getattr(Image, "BICUBIC", Image.BILINEAR))
                img = img.resize((OUT_SIZE, OUT_SIZE), rs)
            W, H = img.size
            arr  = np.array(img, dtype=np.uint8)
            if _crear_geotiff_gdal(arr, bbox_fc_pad, sr_wkt, ruta_tif):
                return True
        else:
            OUT_SIZE = int(target_size or RENDER_SIZE)
            W = H = OUT_SIZE
            arr = np.zeros((H, W, 3), dtype=np.uint8)
            arr[:, :] = [14, 40, 70]
        cell_x = (xmax - xmin) / W
        cell_y = (ymax - ymin) / H
        pt     = arcpy.Point(xmin, ymin)
        sr = arcpy.SpatialReference()
        if sr_wkt:
            try:
                sr.loadFromString(sr_wkt)
            except Exception:
                sr = arcpy.SpatialReference(4326)
        else:
            sr = arcpy.SpatialReference(4326)
        bandas = []
        for b_idx, sufijo in enumerate(["_R", "_G", "_B"]):
            arr_b  = np.flipud(arr[:, :, b_idx].astype(np.float32))
            ras_b  = arcpy.NumPyArrayToRaster(arr_b, pt, cell_x, cell_y)
            ruta_b = os.path.join(tmp_dir, f"_atd_tmp{sufijo}.tif")
            ras_b.save(ruta_b)
            arcpy.management.DefineProjection(ruta_b, sr)
            bandas.append(ruta_b)
        arcpy.management.CompositeBands(bandas, ruta_tif)
        arcpy.management.DefineProjection(ruta_tif, sr)
        for ruta_b in bandas:
            try:
                if arcpy.Exists(ruta_b):
                    arcpy.management.Delete(ruta_b)
            except Exception:
                pass
        return True
    except Exception as e:
        arcpy.AddWarning(f"GeoTIFF NumPy error: {e}")
        try:
            ruta_png = ruta_tif.replace(".tif", "_fallback.png")
            ruta_pgw = ruta_png.replace(".png", ".pgw")
            ruta_prj = ruta_png.replace(".png", ".prj")
            with open(ruta_png, "wb") as f:
                f.write(img_bytes)
            W_px = H_px = 512
            if pil_ok:
                try:
                    from PIL import Image
                    with Image.open(io.BytesIO(img_bytes)) as im:
                        W_px, H_px = im.size
                except Exception:
                    pass
            cw = (xmax - xmin) / W_px
            ch = (ymax - ymin) / H_px
            with open(ruta_pgw, "w") as f:
                f.write(f"{cw:.10f}\n0.0\n0.0\n-{ch:.10f}\n{xmin:.10f}\n{ymax:.10f}\n")
            if sr_wkt:
                with open(ruta_prj, "w") as f:
                    f.write(sr_wkt)
            return ruta_png
        except Exception:
            return False


# ─── CANVAS CON ZOOM + VECTOR ────────────────────────────────────────────────

class ZoomCanvas:
    """
    Canvas con zoom/pan que muestra:
    - Imagen satelital de fondo
    - TODAS las alertas activas (polígonos azul translúcido) con sus vértices
    - La alerta SELECCIONADA en rojo prominente con polígono completo
    """
    def __init__(self, parent, label_text, fg_color):
        self.frame = tk.Frame(parent, bg=C["bg"])
        self.frame.pack(side="left", fill="both", expand=True)

        tk.Label(self.frame, text=label_text, bg=C["bg"], fg=C["dim"],
                 font=("Consolas", 8, "bold")).pack()
        self.lbl_fecha = tk.Label(self.frame, text="—", bg=C["bg"], fg=fg_color,
                                   font=("Segoe UI", 14, "bold"))
        self.lbl_fecha.pack()

        tb = tk.Frame(self.frame, bg=C["bg"])
        tb.pack(fill="x")
        for sym, cmd in [("＋", self._zoom_in), ("－", self._zoom_out), ("⊙", self._reset_zoom)]:
            tk.Button(tb, text=sym, bg=C["card"], fg=C["texto"],
                      font=("Consolas", 8), relief="flat", cursor="hand2",
                      padx=6, pady=1, command=cmd).pack(side="left", padx=1)
        self.lbl_zoom = tk.Label(tb, text="100%", bg=C["bg"], fg=C["texto"],
                                  font=("Segoe UI", 9, "bold"))
        self.lbl_zoom.pack(side="left", padx=4)

        self.lbl_img_status = tk.Label(tb, text="", bg=C["bg"], fg=C["azul"],
                                        font=("Segoe UI", 8, "bold"))
        self.lbl_img_status.pack(side="right", padx=4)

        self.cv = tk.Canvas(self.frame, bg="#FAFBFC",
                             highlightthickness=1,
                             highlightbackground=C["borde"],
                             cursor="crosshair")
        self.cv.pack(fill="both", expand=True, pady=2)

        self.lbl_id  = tk.Label(self.frame, text="ID: —", bg=C["bg"], fg=C["texto"],
                                 font=("Segoe UI", 8), wraplength=340)
        self.lbl_id.pack()
        self.lbl_sat = tk.Label(self.frame, text="Satelite: —", bg=C["bg"], fg=C["dim"],
                                 font=("Segoe UI", 8))
        self.lbl_sat.pack()

        self._pil_orig   = None
        self._tk_img     = None
        self._zoom       = 1.0
        self._pan_x      = 0
        self._pan_y      = 0
        self._drag_x     = 0
        self._drag_y     = 0
        self._poly_sel   = []
        self._polys_vec  = []
        self._bbox_view  = None
        self._info_esc   = None
        self._img_offset = (0, 0, 400, 300)
        self._cod_alerta = ""
        self._crop_ok    = False
        self._lado       = ""
        self._show_sel_poly = True
        self._show_neighbors = True
        self._vec_labels = []

        self.cv.bind("<Configure>",       self._on_resize)
        self.cv.bind("<MouseWheel>",      self._on_wheel)
        self.cv.bind("<Button-4>",        self._on_wheel)
        self.cv.bind("<Button-5>",        self._on_wheel)
        self.cv.bind("<ButtonPress-1>",   self._on_drag_start)
        self.cv.bind("<B1-Motion>",       self._on_drag_move)
        self.cv.bind("<Double-Button-1>", self._reset_zoom)

        self._draw_grilla("Selecciona una alerta del FC")

    def _draw_grilla(self, msg=""):
        self.cv.delete("all")
        self.cv.update_idletasks()
        w = max(self.cv.winfo_width(), 380)
        h = max(self.cv.winfo_height(), 280)
        self.cv.create_rectangle(0, 0, w, h, fill="#FAFBFC", outline="")
        for x in range(0, w, 40):
            self.cv.create_line(x, 0, x, h, fill=C["grid"])
        for y in range(0, h, 40):
            self.cv.create_line(0, y, w, y, fill=C["grid"])
        if msg:
            self.cv.create_text(w // 2, h // 2, text=msg,
                                 fill=C["dim"], font=("Consolas", 10),
                                 justify="center")

    def set_pil(self, pil_img, escena, poly_sel, bbox_view, polys_vec=None,
                cod_alerta="", crop_ok=False, vec_labels=None):
        try:
            self._pil_orig = pil_img.convert("RGB") if pil_img else pil_img
        except Exception:
            self._pil_orig = pil_img
        self._info_esc   = escena
        self._poly_sel   = poly_sel  or []
        self._polys_vec  = polys_vec or []
        self._vec_labels = vec_labels or []
        self._bbox_view  = bbox_view or []
        self._cod_alerta = cod_alerta
        self._crop_ok    = crop_ok
        self._encuadrar_alerta()
        estado = "Imagen lista" if crop_ok else "Tile completo"
        self.lbl_img_status.config(text=estado, fg=C["azul"])
        self._redraw()
        self.cv.update_idletasks()

    def set_escena(self, escena, poly_sel, bbox_view, polys_vec=None, cod_alerta="",
                   vec_labels=None):
        self._pil_orig   = None
        self._info_esc   = escena
        self._poly_sel   = poly_sel  or []
        self._polys_vec  = polys_vec or []
        self._vec_labels = vec_labels or []
        self._bbox_view  = bbox_view or []
        self._cod_alerta = cod_alerta
        self._zoom  = 1.0
        self._pan_x = 0
        self._pan_y = 0
        self.lbl_img_status.config(text="sin imagen")
        self._redraw()

    def set_vector(self, poly_sel, bbox_view, polys_vec=None, cod_alerta="",
                   vec_labels=None):
        self._poly_sel   = poly_sel  or []
        self._polys_vec  = polys_vec or []
        self._vec_labels = vec_labels or []
        self._bbox_view  = bbox_view or []
        self._cod_alerta = cod_alerta
        self._zoom  = 1.0
        self._pan_x = 0
        self._pan_y = 0
        self.lbl_img_status.config(text="")
        self._redraw()

    def actualizar_vectores(self, polys_vec):
        self._polys_vec = polys_vec or []
        self._redraw()

    def set_vector_visibility(self, show_sel=True, show_neighbors=True):
        self._show_sel_poly = bool(show_sel)
        self._show_neighbors = bool(show_neighbors)
        self._redraw()

    def _encuadrar_alerta(self):
        """Zoom al panel + centrar en la alerta (fotointerpretación)."""
        self._pan_x = 0
        self._pan_y = 0
        self.cv.update_idletasks()
        w = max(self.cv.winfo_width(), 400)
        h = max(self.cv.winfo_height(), 300)
        if not self._pil_orig:
            self._zoom = 1.0
            return
        ow, oh = self._pil_orig.size
        self._zoom = min(w / max(ow, 1), h / max(oh, 1)) * 0.95
        px, py = ow / 2.0, oh / 2.0
        if (self._poly_sel and self._bbox_view and len(self._bbox_view) == 4
                and self._bbox_view != [0, 0, 0, 0]):
            x0, y0, x1, y1 = self._bbox_view
            if abs(x1 - x0) > 1e-9 and abs(y1 - y0) > 1e-9:
                cx = sum(p[0] for p in self._poly_sel) / len(self._poly_sel)
                cy = sum(p[1] for p in self._poly_sel) / len(self._poly_sel)
                px = (cx - x0) / (x1 - x0) * ow
                py = (y1 - cy) / (y1 - y0) * oh
        self._pan_x = (ow / 2.0 - px) * self._zoom
        self._pan_y = (oh / 2.0 - py) * self._zoom

    def _redraw(self):
        self.cv.delete("all")
        self.cv.update_idletasks()
        w = max(self.cv.winfo_width(), 200)
        h = max(self.cv.winfo_height(), 200)

        if self._pil_orig is not None:
            self._draw_img(w, h)
        else:
            self._draw_fondo(w, h)

        self._draw_vecinos(w, h)
        self._draw_vector_sel(w, h)
        self.lbl_zoom.config(text=f"{int(self._zoom * 100)}%")

    def _draw_img(self, w, h):
        try:
            from PIL import Image, ImageTk
            img = self._pil_orig
            if img is None:
                self._draw_fondo(w, h)
                return
            ow, oh = img.size
            nw = max(int(ow * self._zoom), 1)
            nh = max(int(oh * self._zoom), 1)
            rs = getattr(Image, "LANCZOS",
                         getattr(Image, "BICUBIC", Image.BILINEAR))
            resized = img.resize((nw, nh), rs)
            ox = int(w / 2 - nw / 2 + self._pan_x)
            oy = int(h / 2 - nh / 2 + self._pan_y)
            self._tk_img = ImageTk.PhotoImage(resized, master=self.cv)
            self.cv._photo_ref = self._tk_img
            self.cv.create_image(ox, oy, anchor="nw", image=self._tk_img, tags=("sat",))
            self.cv.tag_lower("sat")
            self._img_offset = (ox, oy, nw, nh)
        except Exception as ex:
            self.lbl_img_status.config(text=f"Error dibujo: {ex}", fg=C["rojo2"])
            self._draw_fondo(w, h)

    def _draw_fondo(self, w, h):
        self.cv.create_rectangle(0, 0, w, h, fill="#FAFBFC", outline="")
        for x in range(0, w, 30):
            self.cv.create_line(x, 0, x, h, fill=C["grid"])
        for y in range(0, h, 30):
            self.cv.create_line(0, y, w, y, fill=C["grid"])

        pad_cv = 0.12
        iw = int(w * (1 - 2 * pad_cv))
        ih = int(h * (1 - 2 * pad_cv))
        ox = int(w * pad_cv + self._pan_x * self._zoom)
        oy = int(h * pad_cv + self._pan_y * self._zoom)
        self._img_offset = (ox, oy, iw, ih)

        if self._info_esc:
            esc = self._info_esc
            y0  = 12
            msgs = [
                (esc.get("fecha", "—"),            C["texto"], 12, "bold"),
                (esc.get("sat",   "—"),             C["azul2"],  8, "normal"),
                (f"Nubes: {esc.get('nubes','?')}%", C["dim"],    7, "normal"),
                (f"API: {esc.get('api','?')}",       C["purp"],   7, "normal"),
            ]
            if esc.get("prev"):
                msgs.append(("Descargando imagen...", C["amarillo"], 8, "bold"))
            else:
                msgs.append(("Sin preview disponible", C["rojo"], 7, "normal"))
                msgs.append(("→ Prueba con menor % nubes", C["dim"], 6, "normal"))
            for txt, fc, fs, fw in msgs:
                self.cv.create_text(w // 2, y0, text=txt, fill=fc,
                                     font=("Consolas", fs, fw), width=w - 20)
                y0 += fs + 8
        elif self._poly_sel:
            self.cv.create_text(w // 2, 20, text="▣  Vector cargado  ▣",
                                 fill=C["verde"], font=("Consolas", 10, "bold"))
            n_act = len(self._polys_vec) + (
                1 if self._poly_sel and self._show_sel_poly else 0
            )
            self.cv.create_text(w // 2, 42,
                                 text=f"{n_act} alerta(s) activa(s) en vista",
                                 fill=C["dim"], font=("Consolas", 8))
            self.cv.create_text(w // 2, 58,
                                 text="Busca escenas para ver imagen satelital",
                                 fill=C["dim"], font=("Consolas", 8))

    def _bbox(self):
        if self._info_esc:
            ib = self._info_esc.get("img_bbox_wgs84")
            if ib and len(ib) == 4 and ib != [0, 0, 0, 0]:
                return ib
        if self._bbox_view and len(self._bbox_view) == 4:
            bv = self._bbox_view
            if bv != [0, 0, 0, 0]:
                return bv

        all_pts = list(self._poly_sel)
        for poly in self._polys_vec:
            all_pts.extend(poly)

        if all_pts:
            lons = [p[0] for p in all_pts]
            lats = [p[1] for p in all_pts]
            if lons and lats:
                pad  = max((max(lons) - min(lons)) * 0.25, 0.005)
                return [min(lons) - pad, min(lats) - pad,
                        max(lons) + pad, max(lats) + pad]

        if self._poly_sel:
            lons = [p[0] for p in self._poly_sel]
            lats = [p[1] for p in self._poly_sel]
            if lons and lats:
                pad  = max((max(lons) - min(lons)) * 0.25, 0.002)
                return [min(lons) - pad, min(lats) - pad,
                        max(lons) + pad, max(lats) + pad]
        return None

    def _geo2cv(self, lon, lat, bbox):
        bx0, by0, bx1, by1 = bbox
        if bx1 == bx0 or by1 == by0:
            return None, None
        ox, oy, nw, nh = self._img_offset
        px = ox + (lon - bx0) / (bx1 - bx0) * nw
        py = oy + (by1 - lat) / (by1 - by0) * nh
        return px, py

    def _pts_cv(self, poly, bbox):
        pts = [self._geo2cv(lon, lat, bbox) for lon, lat in poly]
        return [(px, py) for px, py in pts if px is not None]

    def _flat(self, pts_cv):
        f = []
        for px, py in pts_cv:
            f += [px, py]
        return f

    # ══════════════════════════════════════════════════════════════════════════
    # v6.3 — _draw_vecinos: dibuja el POLÍGONO completo de cada alerta vecina
    # ══════════════════════════════════════════════════════════════════════════
    def _draw_vecinos(self, w, h):
        """Dibuja TODAS las alertas activas: polígono azul translúcido + número."""
        if not self._show_neighbors or not self._polys_vec:
            return
        bbox = self._bbox()
        if not bbox:
            return
        for i, poly in enumerate(self._polys_vec):
            try:
                pts = self._pts_cv(poly, bbox)
                fl  = self._flat(pts)
                if len(fl) >= 6:  # mínimo 3 vértices para un polígono
                    # Sombra / halo exterior
                    fl_s = [c + 3 for c in fl]
                    self.cv.create_polygon(fl_s, outline="#000000", fill="", width=4)
                    # Relleno translúcido azul (stipple = semitransparencia Tk)
                    self.cv.create_polygon(fl, outline="#2471A3", fill="#1A5276",
                                            stipple="gray25", width=1)
                    # Borde sólido azul
                    self.cv.create_polygon(fl, outline="#2471A3", fill="",
                                            width=2)
                    if pts:
                        cx = sum(p[0] for p in pts) / len(pts)
                        cy = sum(p[1] for p in pts) / len(pts)
                        r = 9
                        for col, wd in [("#000000", 4), ("#5DADE2", 2)]:
                            self.cv.create_line(cx-r-4, cy, cx+r+4, cy, fill=col, width=wd)
                            self.cv.create_line(cx, cy-r-4, cx, cy+r+4, fill=col, width=wd)
                        self.cv.create_oval(cx-r, cy-r, cx+r, cy+r,
                                            fill="#1A5276", outline="#5DADE2", width=2)
                        lbl = (
                            self._vec_labels[i]
                            if i < len(self._vec_labels)
                            else str(i + 1)
                        )
                        self.cv.create_rectangle(cx-58, cy-r-24, cx+58, cy-r-8,
                                                 fill="#000000", outline="#2471A3", width=1)
                        self.cv.create_text(cx, cy-r-16, text=f"▲ {lbl[:14]}",
                                            fill="#5DADE2",
                                            font=("Consolas", 7, "bold"))
            except Exception:
                pass

    # ══════════════════════════════════════════════════════════════════════════
    # v6.3 — _draw_vector_sel: polígono rojo completo (fill + outline + vértices)
    # ══════════════════════════════════════════════════════════════════════════
    def _draw_vector_sel(self, w, h):
        """Dibuja el polígono SELECCIONADO en rojo prominente con todos sus vértices."""
        if not self._show_sel_poly or not self._poly_sel:
            return
        bbox = self._bbox()
        if not bbox or bbox == [0, 0, 0, 0]:
            self.cv.create_text(w // 2, h - 20,
                                 text="⚠ Sin coordenadas WGS84 — revisa SR del FC",
                                 fill=C["amarillo"], font=("Consolas", 7))
            return
        try:
            pts = self._pts_cv(self._poly_sel, bbox)
            if len(pts) < 2:
                return
            fl = self._flat(pts)

            # Sombra exterior
            fl_s = [c + 4 for c in fl]
            if len(fl_s) >= 4:
                self.cv.create_polygon(fl_s, outline="#000000", fill="", width=6)

            # Relleno rojo translúcido (polígono completo)
            self.cv.create_polygon(fl, outline=C["rojo2"], fill=C["rojo2"],
                                    stipple="gray25", width=3)
            # Borde rojo sólido (polígono completo)
            self.cv.create_polygon(fl, outline=C["rojo2"], fill="", width=3)

            # Vértices individuales
            for px, py in pts:
                r = 4
                self.cv.create_oval(px-r, py-r, px+r, py+r,
                                     fill=C["rojo2"], outline="white", width=1)

            # Cruz en el centroide
            cx = sum(p[0] for p in pts) / len(pts)
            cy = sum(p[1] for p in pts) / len(pts)
            r  = 10
            for col, wd in [("#000000", 4), (C["amarillo"], 2)]:
                self.cv.create_line(cx-r-6, cy, cx+r+6, cy, fill=col, width=wd)
                self.cv.create_line(cx, cy-r-6, cx, cy+r+6, fill=col, width=wd)
            self.cv.create_oval(cx-r, cy-r, cx+r, cy+r,
                                  fill=C["amarillo"], outline="white", width=2)

            # Etiqueta del código
            cod = self._cod_alerta or "ALERTA"
            self.cv.create_rectangle(cx-65, cy-r-32, cx+65, cy-r-12,
                                      fill="#000000", outline=C["rojo2"], width=1)
            self.cv.create_text(cx, cy-r-22, text=f"▲ {cod}",
                                 fill=C["rojo2"], font=("Consolas", 8, "bold"))

        except Exception:
            pass

    def _zoom_in(self, f=1.25):
        self._zoom = min(self._zoom * f, 16.0)
        self._redraw()

    def _zoom_out(self, f=1.25):
        self._zoom = max(self._zoom / f, 0.05)
        self._redraw()

    def _reset_zoom(self, evt=None):
        self._zoom  = 1.0
        self._pan_x = 0
        self._pan_y = 0
        self._redraw()

    def _on_wheel(self, evt):
        if evt.widget is self.cv:
            if evt.num == 4 or evt.delta > 0:
                self._zoom_in(1.15)
            else:
                self._zoom_out(1.15)

    def _on_drag_start(self, evt):
        self._drag_x = evt.x
        self._drag_y = evt.y

    def _on_drag_move(self, evt):
        self._pan_x += evt.x - self._drag_x
        self._pan_y += evt.y - self._drag_y
        self._drag_x = evt.x
        self._drag_y = evt.y
        self._redraw()

    def _on_resize(self, evt):
        self._redraw()


# ─── PANEL SELECTOR DE BANDAS (OptionMenu) ────────────────────────────────────

class PanelBandas(tk.Frame):
    def __init__(self, parent, bg_color, on_change_callback=None):
        super().__init__(parent, bg=bg_color)
        self._callback = on_change_callback
        self._idx      = tk.IntVar(value=BANDA_DEFAULT_IDX)

        tk.Label(self, text="Combinación de bandas:", bg=bg_color, fg=C["dim"],
                 font=("Consolas", 7, "bold"), anchor="w").pack(fill="x", pady=(4, 0))

        nombres = [b["nombre"] for b in BANDAS_S2]
        self._var_nombre = tk.StringVar(value=nombres[BANDA_DEFAULT_IDX])

        om = tk.OptionMenu(self, self._var_nombre, *nombres,
                           command=self._on_select)
        om.config(bg=C["card2"], fg=C["verde2"], relief="flat",
                  font=("Consolas", 8), activebackground=C["hover"],
                  activeforeground="white", cursor="hand2",
                  highlightthickness=0, bd=0)
        om["menu"].config(bg=C["card"], fg=C["texto"],
                          font=("Consolas", 8), activebackground=C["sel"],
                          activeforeground="white")
        om.pack(fill="x", pady=(2, 2))

        self._lbl_cod  = tk.Label(self, text="", bg=bg_color, fg=C["verde2"],
                                   font=("Consolas", 7, "bold"), anchor="w")
        self._lbl_cod.pack(fill="x", padx=4)
        self._lbl_desc = tk.Label(self, text="", bg=bg_color, fg=C["dim"],
                                   font=("Consolas", 6), justify="left",
                                   wraplength=280, anchor="w")
        self._lbl_desc.pack(fill="x", padx=4)
        self._lbl_uso  = tk.Label(self, text="", bg=bg_color, fg=C["amarillo"],
                                   font=("Consolas", 6), justify="left",
                                   wraplength=280, anchor="w")
        self._lbl_uso.pack(fill="x", padx=4, pady=(0, 4))

        self._actualizar_labels(BANDA_DEFAULT_IDX)

    def _actualizar_labels(self, idx):
        b = BANDAS_S2[idx]
        self._idx.set(idx)
        self._lbl_cod.config(text=f"S2: {b['codigo']}", fg=b["color"])
        self._lbl_desc.config(text=b["desc"])
        self._lbl_uso.config(text=f"Landsat: {b.get('landsat','-')}  |  {b['uso']}")

    def _on_select(self, nombre):
        idx = next((i for i, b in enumerate(BANDAS_S2) if b["nombre"] == nombre),
                   BANDA_DEFAULT_IDX)
        self._actualizar_labels(idx)
        if self._callback:
            self._callback(idx)

    def get_idx(self):
        return self._idx.get()

    def get_banda(self):
        return BANDAS_S2[self._idx.get()]


# ─── CONTROLES UI ESTILIZADOS ─────────────────────────────────────────────────

class _GFPCheck(tk.Frame):
    """Checkbox con borde, sombra y marca precisa."""

    def __init__(self, parent, variable, text="", command=None, bg=None,
                 fg=None, accent=None, size=20, font=None):
        bg = bg or C["card"]
        super().__init__(parent, bg=bg)
        self.var = variable
        self._cmd = command
        self._size = size
        self._bg = bg
        self._fg = fg or C["texto"]
        self._accent = accent or C["sel"]
        self._font = font or ("Segoe UI", 9)

        self._cv = tk.Canvas(
            self, width=size + 4, height=size + 4,
            bg=bg, highlightthickness=0, cursor="hand2",
        )
        self._cv.pack(side="left", padx=(0, 8 if text else 0))
        self._cv.bind("<Button-1>", self._toggle)

        self._lbl = None
        if text:
            self._lbl = tk.Label(
                self, text=text, bg=bg, fg=self._fg,
                font=self._font, cursor="hand2", anchor="w",
            )
            self._lbl.pack(side="left", fill="x", expand=True)
            self._lbl.bind("<Button-1>", self._toggle)

        self.var.trace_add("write", lambda *_: self.redraw())
        self.redraw()

    def _toggle(self, event=None):
        self.var.set(not self.var.get())
        if self._cmd:
            self._cmd()

    def redraw(self):
        s = self._size
        cv = self._cv
        cv.delete("all")
        on = bool(self.var.get())
        on_dark = (
            self._bg == C["header"]
            or str(self._accent).upper() in ("#FFFFFF", "#FFF")
        )
        cv.create_rectangle(
            3, 3, s + 2, s + 2, fill="#C5D0DC", outline="", tags="shadow",
        )
        if on:
            fill = "#27AE60" if on_dark else self._accent
            outline = "#FFFFFF" if on_dark else self._accent
            mark_color = "#FFFFFF"
        else:
            fill = self._bg if on_dark else "#FFFFFF"
            outline = "#FFFFFF" if on_dark else C["borde"]
            mark_color = "#FFFFFF"
        cv.create_rectangle(
            0, 0, s, s, fill=fill, outline=outline, width=2, tags="box",
        )
        if on:
            cv.create_line(
                5, s // 2, s // 2 - 1, s - 6,
                fill=mark_color, width=2, capstyle="round", joinstyle="round",
            )
            cv.create_line(
                s // 2 - 1, s - 6, s - 5, 5,
                fill=mark_color, width=2, capstyle="round", joinstyle="round",
            )
        if self._lbl is not None:
            self._lbl.config(
                fg=self._accent if on else self._fg,
                font=(self._font[0], self._font[1],
                      "bold" if on else "normal"),
            )


class _GFPRadio(tk.Frame):
    """Radio button circular estilizado."""

    def __init__(self, parent, variable, value, text, bg=None, fg=None,
                 accent=None, on_change=None, font=None):
        bg = bg or C["card"]
        super().__init__(parent, bg=bg)
        self.var = variable
        self.value = value
        self._bg = bg
        self._fg = fg or C["texto"]
        self._accent = accent or C["sel"]
        self._on_change = on_change
        self._font = font or ("Segoe UI", 9, "bold")

        self._cv = tk.Canvas(
            self, width=24, height=24, bg=bg,
            highlightthickness=0, cursor="hand2",
        )
        self._cv.pack(side="left", padx=(0, 8))
        self._cv.bind("<Button-1>", self._select)

        self._lbl = tk.Label(
            self, text=text, bg=bg, fg=self._fg,
            font=self._font, cursor="hand2", anchor="w",
        )
        self._lbl.pack(side="left", fill="x", expand=True)
        self._lbl.bind("<Button-1>", self._select)

        self.var.trace_add("write", lambda *_: self.redraw())
        self.redraw()

    def _select(self, event=None):
        self.var.set(self.value)
        if self._on_change:
            self._on_change()

    def redraw(self):
        cv = self._cv
        cv.delete("all")
        on = str(self.var.get()) == str(self.value)
        cv.create_oval(2, 2, 20, 20, fill="#C5D0DC", outline="", tags="shadow")
        cv.create_oval(
            0, 0, 18, 18,
            fill="#FFFFFF", outline=self._accent if on else C["borde"], width=2,
        )
        if on:
            cv.create_oval(5, 5, 13, 13, fill=self._accent, outline="")
        self._lbl.config(
            fg=self._accent if on else self._fg,
            font=(self._font[0], self._font[1], "bold" if on else "normal"),
        )


_VISOR_PKG_ROOT = None


def _resolver_raiz_paquete(gdb_path=None):
    """Raiz ATD_Loreto/Cuzco/San_Martin (donde vive logos/)."""
    global _VISOR_PKG_ROOT
    if _VISOR_PKG_ROOT and os.path.isdir(
            os.path.join(_VISOR_PKG_ROOT, "logos")):
        return _VISOR_PKG_ROOT
    candidatos = []
    if gdb_path:
        gp = os.path.abspath(str(gdb_path))
        parent = os.path.dirname(gp)
        if os.path.basename(parent).lower() == "gdb":
            candidatos.append(os.path.dirname(parent))
        else:
            candidatos.append(parent)
    candidatos.append(os.path.dirname(_toolbox_dir))
    try:
        candidatos.append(os.getcwd())
    except Exception:
        pass
    for raiz in candidatos:
        if raiz and os.path.isdir(os.path.join(raiz, "logos")):
            _VISOR_PKG_ROOT = raiz
            return raiz
    _VISOR_PKG_ROOT = os.path.dirname(_toolbox_dir)
    return _VISOR_PKG_ROOT


def _dir_logos_visor():
    """Carpeta logos/ del paquete ATD (hermana de toolbox/)."""
    return os.path.join(_resolver_raiz_paquete(), "logos")


def _ruta_logo_gfp():
    """Ruta al logo GFP institucional (Suiza apoyando al Peru)."""
    for dir_logos in (
        _dir_logos_visor(),
        os.path.join(os.path.dirname(_toolbox_dir), "logos"),
    ):
        if not dir_logos or not os.path.isdir(dir_logos):
            continue
        try:
            from atd_logos import resolve_logo_path
            p = resolve_logo_path(dir_logos, "logo_gfp")
            if p and os.path.isfile(p):
                return p
        except Exception:
            pass
        for cand in ("logo_gfp.png", "logo_gfp.jpg", "logo_gfp.jpeg"):
            p = os.path.join(dir_logos, cand)
            if os.path.isfile(p):
                return p
    return None


# ─── VISOR PRINCIPAL ──────────────────────────────────────────────────────────

class VisorATD:

    def __init__(self, root, vectores, sr_wkt,
                 arcgis_mapa_nombre, tmp_dir,
                 callback_geotiff=None):
        self.root               = root
        self.vectores           = vectores
        self._vect_filt         = vectores[:]
        self.sr_wkt             = sr_wkt
        self.arcgis_mapa_nombre = arcgis_mapa_nombre
        self.tmp_dir            = tmp_dir
        self.callback_geotiff   = callback_geotiff

        self.vec_sel    = None
        self.escenas    = []
        self.esc_a      = None
        self.esc_d      = None
        self._pil_a     = None
        self._pil_d     = None
        self._pil_a_bar = None
        self._pil_d_bar = None
        self.anim_on    = False
        self.anim_idx   = 0
        self._banda_idx = BANDA_DEFAULT_IDX

        self._checks = {}
        self._cargar_timer = None
        self._img_en_curso = set()
        self._img_pending = 0
        self.v_show_alertas = tk.BooleanVar(value=True)
        self.v_show_vec_sel  = self.v_show_alertas
        self.v_show_vec_all  = self.v_show_alertas

        try:
            from PIL import Image, ImageTk, ImageDraw, ImageFont
            self.PIL = Image; self.PILtk = ImageTk
            self.PILdr = ImageDraw; self.PILft = ImageFont
            self.pil = True
        except ImportError:
            self.pil = False

        self._cargar_branding_gfp()
        self._build_ui()
        self._aplicar_icono_ventana()
        self.root.after(150, self._aplicar_icono_ventana)
        self._log(f"Visor Satelital - GFP Subnacional  [{dt.now():%Y-%m-%d %H:%M}]", "ok")
        self._log(f"FC: {len(vectores)} alertas cargadas", "ok")
        if not self.pil:
            self._log("AVISO: pip install pillow  para imágenes", "warn")
        if arcgis_mapa_nombre:
            self._log(f"Mapa ArcGIS: '{arcgis_mapa_nombre}'", "ok")
        else:
            self._log("Sin mapa activo", "warn")
        sin_coords = sum(1 for v in vectores if not v["pts_wgs84"])
        if sin_coords:
            self._log(f"AVISO: {sin_coords}/{len(vectores)} sin WGS84 — revisa SR", "warn")
        else:
            self._log("WGS84 OK", "ok")
        self._refrescar_lb(self.vectores)
        if self.vectores:
            self._sel_alerta_por_oid(self.vectores[0])

    def _build_ui(self):
        self.root.title("Visor Satelital — GFP Subnacional")
        self.root.geometry("1520x960")
        self.root.minsize(1200, 800)
        self.root.configure(bg=C["bg"])
        self.root.resizable(True, True)

        self._header()
        self._statusbar()

        body = tk.Frame(self.root, bg=C["bg"])
        body.pack(fill="both", expand=True)
        self._panel_izq(body)
        tk.Frame(body, bg=C["sep"], width=2).pack(side="left", fill="y")
        self._panel_cen(body)
        tk.Frame(body, bg=C["sep"], width=2).pack(side="left", fill="y")
        self._panel_der(body)

    def _cargar_branding_gfp(self):
        """Precarga logos GFP para header, pie e icono de ventana."""
        self._win_icon = None
        self._win_icons = []
        self._hdr_logo = None
        logo_path = _ruta_logo_gfp()
        if not self.pil or not logo_path:
            return
        try:
            img = self.PIL.open(logo_path).convert("RGBA")
            rs = getattr(self.PIL, "LANCZOS",
                         getattr(self.PIL, "BICUBIC", self.PIL.BILINEAR))
            for sz in (16, 32, 48):
                ic = img.resize((sz, sz), rs)
                self._win_icons.append(
                    self.PILtk.PhotoImage(ic, master=self.root))
            self._win_icon = self._win_icons[-1]
            hdr_src = img.crop((0, 0, img.width, max(1, int(img.height * 0.55))))
            hdr_src = hdr_src.convert("RGBA")
            bg_rgb = (47, 95, 143)
            px = hdr_src.load()
            for y in range(hdr_src.height):
                for x in range(hdr_src.width):
                    r, g, b, a = px[x, y]
                    if r > 235 and g > 235 and b > 235:
                        px[x, y] = (bg_rgb[0], bg_rgb[1], bg_rgb[2], a)
            ratio = 48 / max(hdr_src.width, 1)
            hdr = hdr_src.resize((48, max(1, int(hdr_src.height * ratio))), rs)
            self._hdr_logo = self.PILtk.PhotoImage(hdr, master=self.root)
        except Exception:
            pass

    def _aplicar_icono_ventana(self):
        """Icono GFP en barra de titulo (reemplaza pluma Tk en Windows)."""
        if not getattr(self, "_win_icon", None):
            return
        try:
            self.root.update_idletasks()
            icons = getattr(self, "_win_icons", None) or [self._win_icon]
            self.root.iconphoto(True, *icons)
        except Exception:
            pass
        try:
            logo_path = _ruta_logo_gfp()
            if not logo_path or not self.pil:
                return
            ico_path = os.path.join(self.tmp_dir, "gfp_visor.ico")
            if not os.path.isfile(ico_path):
                img = self.PIL.open(logo_path).convert("RGBA")
                rs = getattr(self.PIL, "LANCZOS",
                             getattr(self.PIL, "BICUBIC", self.PIL.BILINEAR))
                icon = img.resize((32, 32), rs)
                icon.save(
                    ico_path, format="ICO",
                    sizes=[(16, 16), (32, 32), (48, 48)],
                )
            self.root.iconbitmap(ico_path)
        except Exception:
            pass

    def _header(self):
        tk.Frame(self.root, bg=C["header2"], height=5).pack(fill="x")
        h = tk.Frame(self.root, bg=C["header"], height=54)
        h.pack(fill="x")
        h.pack_propagate(False)
        if getattr(self, "_hdr_logo", None):
            lf = tk.Frame(h, bg=C["header"])
            lf.pack(side="left", padx=(12, 4), pady=6)
            tk.Label(lf, image=self._hdr_logo, bg=C["header"]).pack()
        tk.Label(
            h, text="Visor Satelital — GFP Subnacional",
            bg=C["header"], fg="white",
            font=("Segoe UI", 13, "bold"),
        ).pack(side="left", padx=(6, 18), pady=12)
        tk.Label(
            h,
            text="Fotointerpretación ATD  ·  Planet / STAC",
            bg=C["header"], fg="#D6E4F0",
            font=("Segoe UI", 9),
        ).pack(side="left", pady=12)
        tk.Button(h, text="✕  Cerrar", bg=C["rojo2"], fg="white",
                  font=("Segoe UI", 9, "bold"), relief="flat", cursor="hand2",
                  padx=12, pady=6,
                  command=self.root.destroy).pack(side="right", padx=14, pady=10)
        tk.Frame(self.root, bg=C["header2"], height=2).pack(fill="x")

    def _switch_workflow_tab(self, idx):
        self._workflow_tab = idx
        for i, btn in enumerate(self._tab_btns):
            if i == idx:
                btn.config(bg=C["sel"], fg="white", relief="flat")
            else:
                btn.config(bg=C["card2"], fg=C["dim"], relief="flat")
        for i, fr in self._tab_pages.items():
            fr.pack_forget()
        self._tab_pages[idx].pack(fill="both", expand=True)
        hints = {
            0: "Paso 1: seleccione alerta(s) del FC cargado en ArcGIS",
            1: "Paso 2: elija satélite, fechas y busque escenas STAC",
            2: "Paso 3: marque ANTES y DESPUÉS (carga automática al tener ambas)",
            3: "Paso 4: exporte GeoTIFF HD al mapa activo",
        }
        self.lbl_workflow_hint.config(text=hints.get(idx, ""))

    def _panel_izq(self, body):
        p = tk.Frame(body, bg=C["panel"], width=360)
        p.pack(side="left", fill="y")
        p.pack_propagate(False)

        # ── Barra de pasos (estilo USGS EarthExplorer) ─────────────────────
        tab_bar = tk.Frame(p, bg=C["panel"])
        tab_bar.pack(fill="x")
        self._tab_btns = []
        self._tab_pages = {}
        tab_names = [
            ("1. Datos", 0),
            ("2. Satélite", 1),
            ("3. Resultados", 2),
            ("4. Exportar", 3),
        ]
        for name, idx in tab_names:
            b = tk.Button(
                tab_bar, text=name, bg=C["card2"], fg=C["dim"],
                font=("Segoe UI", 8, "bold"), relief="flat", cursor="hand2",
                padx=6, pady=8,
                command=lambda i=idx: self._switch_workflow_tab(i),
            )
            b.pack(side="left", fill="x", expand=True)
            self._tab_btns.append(b)

        self.lbl_workflow_hint = tk.Label(
            p, text="Paso 1: seleccione alerta(s) del FC cargado en ArcGIS",
            bg=C["panel"], fg=C["texto"], font=("Segoe UI", 9, "bold"),
            wraplength=340, justify="left",
        )
        self.lbl_workflow_hint.pack(fill="x", padx=8, pady=(4, 2))

        host = tk.Frame(p, bg=C["panel"])
        host.pack(fill="both", expand=True)

        # ══ TAB 1 — DATOS ══════════════════════════════════════════════════
        t0 = tk.Frame(host, bg=C["panel"])
        self._tab_pages[0] = t0

        self._sec(t0, "CARGA DE DATOS — ALERTAS DEL FC")
        tk.Label(
            t0,
            text=f"{len(self.vectores)} polígonos cargados desde ArcGIS Pro",
            bg=C["panel"], fg=C["verde2"], font=("Consolas", 8),
        ).pack(anchor="w", padx=12, pady=(0, 4))

        ff = tk.Frame(t0, bg=C["panel"])
        ff.pack(fill="x", padx=10, pady=(0, 3))
        tk.Label(ff, text="Filtrar:", bg=C["panel"], fg=C["dim"],
                 font=("Consolas", 7)).pack(side="left")
        self.v_flt = tk.StringVar()
        self.v_flt.trace("w", self._on_filtro)
        tk.Entry(ff, textvariable=self.v_flt, bg=C["card"], fg=C["texto"],
                 insertbackground=C["verde"], font=("Consolas", 8),
                 relief="flat").pack(side="left", fill="x", expand=True, padx=(4, 0))

        lf = tk.Frame(t0, bg=C["panel"])
        lf.pack(fill="both", expand=True, padx=10, pady=(4, 4))

        chk_wrap = tk.Frame(lf, bg=C["borde"], padx=1, pady=1)
        chk_wrap.pack(fill="both", expand=True)
        self.cv_chk = tk.Canvas(chk_wrap, bg=C["card"], highlightthickness=0, height=220)
        sb_chk = ttk.Scrollbar(lf, orient="vertical", command=self.cv_chk.yview)
        self.fr_chk = tk.Frame(self.cv_chk, bg=C["card"])
        self.cv_chk.configure(yscrollcommand=sb_chk.set)
        sb_chk.pack(side="right", fill="y")
        self.cv_chk.pack(side="left", fill="both", expand=True)
        self._chk_win = self.cv_chk.create_window((0, 0), window=self.fr_chk, anchor="nw")
        self.fr_chk.bind("<Configure>",
            lambda e: self.cv_chk.configure(scrollregion=self.cv_chk.bbox("all")))
        self.cv_chk.bind("<Configure>",
            lambda e: self.cv_chk.itemconfig(self._chk_win, width=e.width))
        self.cv_chk.bind("<MouseWheel>", lambda e: self.cv_chk.yview_scroll(
            -1 if e.delta > 0 else 1, "units"))

        fb_chk = tk.Frame(t0, bg=C["panel"])
        fb_chk.pack(fill="x", padx=10, pady=(0, 4))
        tk.Button(fb_chk, text="✓ Todas", bg=C["sel"], fg="white",
                  font=("Consolas", 7), relief="flat", cursor="hand2",
                  pady=2, command=self._check_all).pack(side="left", padx=(0, 2))
        tk.Button(fb_chk, text="✗ Ninguna", bg=C["card2"], fg=C["dim"],
                  font=("Consolas", 7), relief="flat", cursor="hand2",
                  pady=2, command=self._check_none).pack(side="left")
        self.lbl_chk_cnt = tk.Label(fb_chk, text="", bg=C["panel"], fg=C["dim"],
                                     font=("Consolas", 6))
        self.lbl_chk_cnt.pack(side="right")

        fi = tk.Frame(t0, bg=C["card2"])
        fi.pack(fill="x", padx=10, pady=(0, 6))
        self.lbl_cod = tk.Label(fi, text="Alerta: —", bg=C["card2"],
                                fg=C["verde"], font=("Consolas", 8, "bold"))
        self.lbl_cod.pack(anchor="w", padx=8, pady=(4, 0))
        self.lbl_area = tk.Label(fi, text="Area: — ha", bg=C["card2"],
                                 fg=C["dim"], font=("Consolas", 7))
        self.lbl_area.pack(anchor="w", padx=8)
        self.lbl_bbox = tk.Label(fi, text="bbox WGS84: —", bg=C["card2"],
                                 fg=C["dim"], font=("Consolas", 7), wraplength=310)
        self.lbl_bbox.pack(anchor="w", padx=8, pady=(0, 4))

        self._btn(t0, "Siguiente: Satélite »", C["azul"],
                  lambda: self._switch_workflow_tab(1)).pack(
            fill="x", padx=10, pady=4)

        # ══ TAB 2 — SATÉLITE ═══════════════════════════════════════════════
        t1 = tk.Frame(host, bg=C["panel"])
        self._tab_pages[1] = t1

        self._sec(t1, "SELECCIÓN DE SATÉLITE (Data Sets)")
        _sats = ["Sentinel-2", "Landsat 8", "Landsat 9"]
        if _planet_disponible():
            _sats.insert(0, "Planet (PSScene)")
        self.v_sat = tk.StringVar(value=_sats[0])
        sat_outer = tk.Frame(t1, bg=C["borde"], padx=1, pady=1)
        sat_outer.pack(fill="x", padx=10, pady=4)
        sat_fr = tk.Frame(sat_outer, bg=C["card"], padx=10, pady=8)
        sat_fr.pack(fill="x")
        self._sat_radios = []

        def _sync_sat_radios():
            for r in self._sat_radios:
                r.redraw()

        for s in _sats:
            r = _GFPRadio(
                sat_fr, self.v_sat, s, s, bg=C["card"],
                on_change=_sync_sat_radios,
            )
            r.pack(anchor="w", fill="x", pady=3)
            self._sat_radios.append(r)

        self._sec(t1, "CRITERIOS ADICIONALES")
        for lbl, attr, val in [
            ("Desde:", "v_fi", "01/01/2025"),
            ("Hasta:", "v_ff", dt.now().strftime("%d/%m/%Y")),
        ]:
            fr = tk.Frame(t1, bg=C["panel"])
            fr.pack(fill="x", padx=10, pady=1)
            tk.Label(fr, text=lbl, bg=C["panel"], fg=C["dim"],
                     font=("Consolas", 8), width=7, anchor="w").pack(side="left")
            v = tk.StringVar(value=val)
            setattr(self, attr, v)
            tk.Entry(fr, textvariable=v, bg=C["card"], fg=C["texto"],
                     insertbackground=C["verde"], font=("Consolas", 9),
                     relief="flat", width=13).pack(side="left")

        fn = tk.Frame(t1, bg=C["panel"])
        fn.pack(fill="x", padx=10, pady=(4, 2))
        tk.Label(fn, text="Nubes max (%):", bg=C["panel"], fg=C["dim"],
                 font=("Consolas", 8)).pack(side="left")
        self.v_nubes = tk.IntVar(value=40)
        tk.Spinbox(fn, from_=0, to=100, textvariable=self.v_nubes,
                   width=5, bg=C["card"], fg=C["texto"],
                   font=("Consolas", 9), relief="flat",
                   buttonbackground=C["card"]).pack(side="left", padx=4)

        fb2 = tk.Frame(t1, bg=C["panel"])
        fb2.pack(fill="x", padx=10, pady=(2, 4))
        tk.Label(fb2, text="Buffer (km):", bg=C["panel"], fg=C["dim"],
                 font=("Consolas", 8)).pack(side="left")
        self.v_buffer = tk.StringVar(
            value=f"{BUFFER_KM_DEFAULT:g}".replace(",", "."))
        self.spin_buffer = tk.Spinbox(
            fb2, from_=0.2, to=BUFFER_KM_MAX, increment=0.5,
            textvariable=self.v_buffer,
            width=6, bg=C["card"], fg=C["azul"],
            font=("Consolas", 9), relief="flat",
            buttonbackground=C["card"])
        self.spin_buffer.pack(side="left", padx=4)
        tk.Label(fb2, text="máx 25 · 4000=m→4km", bg=C["panel"],
                 fg=C["dim"], font=("Consolas", 6)).pack(side="left")

        self.panel_bandas = PanelBandas(
            t1, C["panel"], on_change_callback=self._on_banda_change)
        self.panel_bandas.pack(fill="x", padx=10, pady=(2, 4))

        self.btn_bus = self._btn(
            t1, "BUSCAR ESCENAS STAC", C["verde"], self._buscar)
        self.btn_bus.pack(fill="x", padx=10, pady=(4, 2))
        _api_txt = "Listo — seleccione alerta en paso 1"
        if _planet_disponible():
            _api_txt = "Planet API OK (PLANET_API_KEY) — recomendado"
        self.lbl_api = tk.Label(t1, text=_api_txt,
                                bg=C["panel"], fg=C["dim"], font=("Consolas", 7))
        self.lbl_api.pack(pady=(0, 2))
        self.lbl_escenas_info = tk.Label(
            t1, text="",
            bg=C["card2"], fg=C["dim"],
            font=("Segoe UI", 10), padx=12, pady=8,
            anchor="w", justify="left",
        )
        self.lbl_escenas_info.pack(fill="x", padx=10, pady=(2, 4))
        self._btn(t1, "Ver Resultados »", C["azul"],
                  lambda: self._switch_workflow_tab(2)).pack(
            fill="x", padx=10, pady=4)

        # ══ TAB 3 — RESULTADOS ═════════════════════════════════════════════
        t2 = tk.Frame(host, bg=C["panel"])
        self._tab_pages[2] = t2

        self._sec(t2, "ESCENAS ENCONTRADAS")
        self.lbl_escenas_badge = tk.Label(
            t2,
            text="Busque escenas en el paso 2 (Satélite).",
            bg=C["card2"], fg=C["dim"],
            font=("Segoe UI", 10), padx=12, pady=8,
            anchor="w", justify="left",
        )
        self.lbl_escenas_badge.pack(fill="x", padx=10, pady=(0, 4))

        self.btn_cargar_img = self._btn(
            t2, "CARGAR IMÁGENES ANTES / DESPUÉS", C["verde"],
            self._cargar_imagenes_visor)
        self.btn_cargar_img.pack(fill="x", padx=10, pady=(0, 6))

        cont = tk.Frame(t2, bg=C["borde"], padx=1, pady=1)
        cont.pack(fill="both", expand=True, padx=8, pady=(0, 6))

        self.cv_esc = tk.Canvas(cont, bg=C["panel"], highlightthickness=0)
        sb_e = ttk.Scrollbar(cont, orient="vertical", command=self.cv_esc.yview)
        self.fr_esc = tk.Frame(self.cv_esc, bg=C["panel"])
        self.cv_esc.configure(yscrollcommand=sb_e.set)
        sb_e.pack(side="right", fill="y")
        self.cv_esc.pack(side="left", fill="both", expand=True)
        self._cv_win = self.cv_esc.create_window((0, 0), window=self.fr_esc, anchor="nw")

        def _sync_esc_scroll(event=None):
            self.cv_esc.update_idletasks()
            self.cv_esc.configure(scrollregion=self.cv_esc.bbox("all"))
            if event is not None:
                self.cv_esc.itemconfig(self._cv_win, width=event.width)

        self.fr_esc.bind("<Configure>", _sync_esc_scroll)
        self.cv_esc.bind("<Configure>", _sync_esc_scroll)

        def _scroll_esc_bounded(e):
            delta = -1 if (e.delta > 0 or e.num == 4) else 1
            top, bottom = self.cv_esc.yview()
            if delta < 0 and top <= 0.001:
                return "break"
            if delta > 0 and bottom >= 0.999:
                return "break"
            self.cv_esc.yview_scroll(delta, "units")
            return "break"

        for widget in [self.cv_esc, self.fr_esc]:
            widget.bind("<MouseWheel>", _scroll_esc_bounded)
            widget.bind("<Button-4>",   _scroll_esc_bounded)
            widget.bind("<Button-5>",   _scroll_esc_bounded)

        # ══ TAB 4 — EXPORTAR ═══════════════════════════════════════════════
        t3 = tk.Frame(host, bg=C["panel"])
        self._tab_pages[3] = t3

        self._sec(t3, "EXPORTACIÓN A ARCGIS PRO")
        self.v_export_hd = tk.BooleanVar(value=True)
        hd_fr = tk.Frame(t3, bg=C["panel"])
        hd_fr.pack(fill="x", padx=12, pady=(4, 8))
        _GFPCheck(
            hd_fr,
            self.v_export_hd,
            text="Exportar en HD",
            bg=C["panel"], fg=C["texto"], accent=C["verde2"],
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", fill="x")

        for txt, col, cmd in [
            ("Cargar GeoTIFF en HD", C["azul"], self._cargar_arcgis),
            ("Aplicar IDs a tabla de atributos",  C["purp"],   self._aplicar_tabla),
            ("Exportar HTML interactivo",         C["sel"],    self._exportar_html),
        ]:
            self._btn(t3, txt, col, cmd).pack(fill="x", padx=10, pady=3)

        self._workflow_tab = 0
        self._switch_workflow_tab(0)

    def _panel_cen(self, body):
        p = tk.Frame(body, bg=C["bg"])
        p.pack(side="left", fill="both", expand=True)

        hdr = tk.Frame(p, bg=C["header"], height=42)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(
            hdr,
            text="Fotointerpretación — ANTES / DESPUÉS  "
                 "[rueda=zoom | arrastre=pan | doble-click=reset]",
            bg=C["header"], fg="#FFFFFF",
            font=("Segoe UI", 10, "bold"),
        ).pack(side="left", padx=10, pady=10)

        vtb = tk.Frame(hdr, bg=C["header"])
        vtb.pack(side="left", padx=8)
        _GFPCheck(
            vtb, self.v_show_alertas, text="Alertas",
            bg=C["header"], fg="#FFFFFF", accent="#FFFFFF",
            font=("Segoe UI", 9, "bold"),
            command=self._on_vector_toggle, size=16,
        ).pack(side="left", padx=6)

        self.btn_anim = self._btn_mini(hdr, "Animación", C["azul"], self._anim_toggle)
        self.btn_anim.pack(side="right", padx=8, pady=6)

        area = tk.Frame(p, bg=C["bg"])
        area.pack(fill="both", expand=True, padx=6, pady=4)

        self.zc_a = ZoomCanvas(area, "ANTES",   C["verde"])
        self.zc_a._lado = "ANTES"
        tk.Frame(area, bg=C["sep"], width=2).pack(side="left", fill="y")
        self.zc_d = ZoomCanvas(area, "DESPUES", C["verde2"])
        self.zc_d._lado = "DESPUES"

        self.lbl_fa    = self.zc_a.lbl_fecha
        self.lbl_fd    = self.zc_d.lbl_fecha
        self.lbl_id_a  = self.zc_a.lbl_id
        self.lbl_id_d  = self.zc_d.lbl_id
        self.lbl_sat_a = self.zc_a.lbl_sat
        self.lbl_sat_d = self.zc_d.lbl_sat

        lf = tk.Frame(p, bg=C["log"], height=110)
        lf.pack(fill="x", padx=6, pady=(0, 4))
        lf.pack_propagate(False)
        tk.Label(lf, text="  LOG STAC API",
                 bg=C["log"], fg=C["dim"],
                 font=("Consolas", 7, "bold"), anchor="w").pack(fill="x")
        self.log_txt = tk.Text(lf, bg="#FFFFFF", fg=C["texto"],
                                font=("Consolas", 9), relief="flat",
                                state="disabled", height=5, wrap="word")
        lsb = ttk.Scrollbar(lf, orient="vertical", command=self.log_txt.yview)
        self.log_txt.configure(yscrollcommand=lsb.set)
        lsb.pack(side="right", fill="y")
        self.log_txt.pack(fill="both", expand=True, padx=4)
        for tag, col in [
            ("ok", "#1B5E20"), ("err", C["rojo2"]),
            ("warn", "#B45309"), ("info", "#1565C0"),
        ]:
            self.log_txt.tag_configure(tag, foreground=col, font=("Consolas", 9))

    def _panel_der(self, body):
        p = tk.Frame(body, bg=C["panel"], width=290)
        p.pack(side="right", fill="y")
        p.pack_propagate(False)

        content = tk.Frame(p, bg=C["panel"])
        content.pack(fill="both", expand=True)

        self._sec(content, "DATOS DE ESCENA")
        for etiq, key, fg in [("ANTES:", "a", C["verde"]),
                                ("DESPUES:", "d", C["verde2"])]:
            tk.Label(content, text=etiq, bg=C["panel"], fg=fg,
                     font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=12, pady=(6, 0))
            info = {}
            for campo, label in [
                ("sat",       "Satelite"),
                ("id",        "ID"),
                ("fecha",     "Fecha"),
                ("nubes",     "Nubes%"),
                ("res",       "Res."),
                ("api",       "Fuente API"),
            ]:
                fr = tk.Frame(content, bg=C["panel"])
                fr.pack(fill="x", padx=12, pady=1)
                tk.Label(fr, text=f"{label}:", bg=C["panel"], fg=C["dim"],
                         font=("Segoe UI", 8), width=10, anchor="w").pack(side="left")
                lbl = tk.Label(fr, text="—", bg=C["panel"], fg=C["texto"],
                               font=("Segoe UI", 8), anchor="w", wraplength=150)
                lbl.pack(side="left", fill="x")
                info[campo] = lbl
            setattr(self, f"info_{key}", info)
            if key == "a":
                tk.Frame(content, bg=C["sep"], height=1).pack(fill="x", padx=8, pady=5)

        tk.Frame(content, bg=C["sep"], height=1).pack(fill="x", padx=8, pady=6)
        self._sec(content, "ÍNDICES RÁPIDOS")
        idx_fr = tk.Frame(content, bg=C["panel"])
        idx_fr.pack(fill="x", padx=10, pady=(0, 4))
        self._btn(idx_fr, "NDVI", C["sel"], self._aplicar_ndvi).pack(
            side="left", fill="x", expand=True, padx=(0, 3))
        self._btn(idx_fr, "NBR", C["rojo"], self._aplicar_nbr).pack(
            side="left", fill="x", expand=True, padx=(3, 0))
        tk.Label(
            content,
            text="También use «Combinación de bandas» en paso 2.",
            bg=C["panel"], fg=C["dim"], font=("Segoe UI", 7),
            wraplength=250, justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 4))

        logo_frame = tk.Frame(p, bg=C["card2"])
        logo_frame.pack(side="bottom", fill="x", padx=8, pady=(6, 10))
        self._logo_gfp_img = None
        self._logo_gfp_frame = logo_frame
        self._poner_logo_gfp(logo_frame)

    def _statusbar(self):
        tk.Frame(self.root, bg=C["sep"], height=1).pack(fill="x")
        sb = tk.Frame(self.root, bg=C["header"], height=26)
        sb.pack(fill="x", side="bottom")
        sb.pack_propagate(False)
        self.lbl_st = tk.Label(sb, text="  Listo — selecciona una alerta",
                                bg=C["header"], fg=C["verde"],
                                font=("Consolas", 8), anchor="w")
        self.lbl_st.pack(side="left", padx=12, pady=4)
        self.lbl_cnt = tk.Label(sb, text="", bg=C["header"], fg=C["dim"],
                                 font=("Consolas", 8))
        self.lbl_cnt.pack(side="right", padx=12, pady=4)

    def _poner_logo_gfp(self, parent):
        """Logo GFP al pie del panel derecho."""
        for w in parent.winfo_children():
            w.destroy()
        logo_path = _ruta_logo_gfp()
        inner = tk.Frame(parent, bg="#FFFFFF", padx=12, pady=10)
        inner.pack(fill="x")
        if self.pil and logo_path:
            try:
                img = self.PIL.open(logo_path).convert("RGBA")
                max_w = 240
                if img.width > max_w:
                    ratio = max_w / float(img.width)
                    img = img.resize(
                        (max_w, max(1, int(img.height * ratio))),
                        getattr(self.PIL, "LANCZOS",
                                getattr(self.PIL, "BICUBIC", self.PIL.BILINEAR)),
                    )
                self._logo_gfp_img = self.PILtk.PhotoImage(
                    img, master=self.root)
                tk.Label(inner, image=self._logo_gfp_img, bg="#FFFFFF").pack()
                return
            except Exception:
                pass
        tk.Label(
            inner, text="GFP Subnacional",
            bg="#FFFFFF", fg=C["sel"],
            font=("Segoe UI", 10, "bold"),
        ).pack()
    def _sec(self, p, txt):
        fr = tk.Frame(p, bg=C["sep"])
        fr.pack(fill="x", pady=(6, 2))
        tk.Label(fr, text=f"  {txt}", bg=C["sep"], fg=C["texto"],
                 font=("Segoe UI", 9, "bold"), anchor="w").pack(fill="x", padx=2, pady=2)

    def _btn(self, p, txt, col, cmd):
        b = tk.Button(p, text=txt, bg=col, fg="white",
                      font=("Consolas", 9, "bold"), relief="flat",
                      cursor="hand2", padx=6, pady=6,
                      activebackground=C["hover"], activeforeground="white",
                      command=cmd)
        b.bind("<Enter>", lambda e: b.config(bg=C["hover"]))
        b.bind("<Leave>", lambda e: b.config(bg=col))
        return b

    def _btn_mini(self, p, txt, col, cmd):
        return tk.Button(p, text=txt, bg=col, fg="white",
                          font=("Consolas", 8), relief="flat",
                          cursor="hand2", padx=6, pady=3, command=cmd)

    def _st(self, msg, col=None):
        if not hasattr(self, "lbl_st"):
            return
        self.lbl_st.config(text=f"  {msg}", fg=col or C["verde"])
        self.root.update_idletasks()

    def _log(self, msg, tag="ok"):
        if not hasattr(self, "log_txt"):
            return
        ts = dt.now().strftime("%H:%M:%S")
        self.log_txt.config(state="normal")
        self.log_txt.insert("end", f"[{ts}] {msg}\n", tag)
        self.log_txt.see("end")
        self.log_txt.config(state="disabled")
        self.root.update_idletasks()

    def _leer_texto_buffer(self):
        for fuente in (
            getattr(self, "spin_buffer", None),
            getattr(self, "v_buffer", None),
        ):
            if fuente is None:
                continue
            try:
                txt = fuente.get() if hasattr(fuente, "get") else None
                if txt is not None and str(txt).strip():
                    return str(txt).strip()
            except tk.TclError:
                continue
            except Exception:
                continue
        return f"{BUFFER_KM_DEFAULT:g}"

    def _get_buffer_km(self):
        raw = self._leer_texto_buffer()
        norm = _normalizar_buffer_km(raw)
        raw_f = _parse_float_locale(raw)
        if raw_f is None or abs(raw_f - norm) > 0.05:
            txt_norm = f"{norm:g}".replace(",", ".")
            self.v_buffer.set(txt_norm)
            if raw_f is not None and abs(raw_f - norm) > 0.05:
                self._log(
                    f"Buffer corregido: {raw} → {norm:.2f} km "
                    f"(el campo es en km; 4000 m = 4 km)",
                    "warn",
                )
        return norm

    def _bbox_imagen_alerta(self, buffer_km=None):
        """BBox WGS84 centrado en la alerta (+ buffer km) — solo para imagen HD."""
        if not self.vec_sel:
            return [0, 0, 0, 0]
        bk = buffer_km if buffer_km is not None else self._get_buffer_km()
        pts = self.vec_sel.get("pts_wgs84") or []
        if pts:
            cx = sum(p[0] for p in pts) / len(pts)
            cy = sum(p[1] for p in pts) / len(pts)
            d_lat = bk / 111.0
            d_lon = bk / (111.0 * math.cos(math.radians(cy)))
            return [cx - d_lon, cy - d_lat, cx + d_lon, cy + d_lat]
        bb = self.vec_sel.get("bbox_wgs84")
        if not bb or bb == [0, 0, 0, 0]:
            return [0, 0, 0, 0]
        return _bbox_con_buffer_km(bb, bk)

    def _bbox_union_activos(self, buffer_km=None):
        """BBox WGS84 que abarca TODAS las alertas activas (solo overlay de vecinos)."""
        buffer_km = buffer_km if buffer_km is not None else self._get_buffer_km()
        bboxes = []
        for v in self.vectores:
            if not v.get("activo", True):
                continue
            bb = v.get("bbox_wgs84")
            if bb and bb != [0, 0, 0, 0]:
                bboxes.append(bb)
        if not bboxes:
            if self.vec_sel and self.vec_sel.get("bbox_wgs84"):
                return _bbox_con_buffer_km(self.vec_sel["bbox_wgs84"], buffer_km)
            return [0, 0, 0, 0]
        x0 = min(b[0] for b in bboxes)
        y0 = min(b[1] for b in bboxes)
        x1 = max(b[2] for b in bboxes)
        y1 = max(b[3] for b in bboxes)
        cx = (x0 + x1) / 2
        cy = (y0 + y1) / 2
        d_lat = buffer_km / 111.0
        d_lon = buffer_km / (111.0 * math.cos(math.radians(cy)))
        ux0 = min(x0, cx - d_lon)
        uy0 = min(y0, cy - d_lat)
        ux1 = max(x1, cx + d_lon)
        uy1 = max(y1, cy + d_lat)
        if ux1 - ux0 < 0.002:
            ux0 -= 0.001
            ux1 += 0.001
        if uy1 - uy0 < 0.002:
            uy0 -= 0.001
            uy1 += 0.001
        return [ux0, uy0, ux1, uy1]

    def _aplicar_banda_por_nombre(self, clave):
        clave_l = clave.lower()
        idx = next(
            (i for i, b in enumerate(BANDAS_S2) if clave_l in b["nombre"].lower()),
            None,
        )
        if idx is None:
            messagebox.showwarning("Banda", f"No se encontró índice {clave}")
            return
        self.panel_bandas._var_nombre.set(BANDAS_S2[idx]["nombre"])
        self.panel_bandas._actualizar_labels(idx)
        self._banda_idx = idx
        self._on_banda_change(idx)
        self._log(f"Índice {clave} aplicado — recargando imágenes...", "ok")

    def _aplicar_ndvi(self):
        if not self.vec_sel:
            messagebox.showwarning("Atención", "Seleccione una alerta primero.")
            return
        self._aplicar_banda_por_nombre("NDVI")

    def _aplicar_nbr(self):
        if not self.vec_sel:
            messagebox.showwarning("Atención", "Seleccione una alerta primero.")
            return
        self._aplicar_banda_por_nombre("NBR")

    def _on_banda_change(self, idx):
        self._banda_idx = idx
        _IMG_CACHE.clear()
        self._pil_a = self._pil_d = None
        banda = BANDAS_S2[idx]
        self._log(f"Banda: {banda['nombre']}", "info")
        if self.vec_sel:
            self._mostrar_info_vector(self.vec_sel)
        if self.esc_a:
            threading.Thread(
                target=self._img_hilo, args=(self.esc_a, "a"), daemon=True,
            ).start()
        if self.esc_d:
            threading.Thread(
                target=self._img_hilo, args=(self.esc_d, "d"), daemon=True,
            ).start()

    def _on_vector_toggle(self):
        on = self.v_show_alertas.get()
        for zc in (self.zc_a, self.zc_d):
            zc.set_vector_visibility(on, on)
        self._log(f"Alertas en mapa: {'ON' if on else 'OFF'}", "info")

    def _bytes_imagen_export(self, esc, pil_img, export_px):
        """
        Exportación rápida: usa la imagen ya cargada en el visor y escala a HD.
        Evita re-descargar 4096px desde STAC/MPC (causa principal de lentitud).
        """
        export_px = int(export_px or RENDER_SIZE)
        if pil_img and self.pil:
            try:
                from PIL import Image
                buf = io.BytesIO()
                img_out = _preparar_imagen_visor(
                    pil_img, es_indice=_es_banda_indice(self._banda_idx))
                if img_out.size[0] != export_px:
                    rs = getattr(Image, "LANCZOS",
                                 getattr(Image, "BICUBIC", Image.BILINEAR))
                    img_out = img_out.resize((export_px, export_px), rs)
                img_out.save(buf, format="PNG", compress_level=3)
                return buf.getvalue()
            except Exception:
                pass
        return self._descargar_bytes_imagen(
            esc, size_px=export_px, forzar_redescarga=False)

    def _descargar_bytes_imagen(self, esc, size_px=None, forzar_redescarga=False):
        """Descarga bytes PNG de la escena al tamaño pedido (visor o export HD)."""
        if not esc or not self.vec_sel:
            return None
        size_px = int(size_px or RENDER_SIZE)
        lado_key = "a" if esc is self.esc_a else "d" if esc is self.esc_d else None
        pil_cache = self._pil_a if lado_key == "a" else self._pil_d if lado_key == "d" else None

        if pil_cache and self.pil and not forzar_redescarga:
            if size_px <= RENDER_SIZE or pil_cache.size[0] >= size_px * 0.9:
                try:
                    from PIL import Image
                    buf = io.BytesIO()
                    img_out = _preparar_imagen_visor(
                        pil_cache, es_indice=_es_banda_indice(self._banda_idx))
                    if img_out.size[0] != size_px:
                        rs = getattr(Image, "LANCZOS",
                                     getattr(Image, "BICUBIC", Image.BILINEAR))
                        img_out = img_out.resize((size_px, size_px), rs)
                    img_out.save(buf, format="PNG", optimize=True)
                    return buf.getvalue()
                except Exception:
                    pass

        buffer_km = self._get_buffer_km()
        bbox_v_buf = self._bbox_imagen_alerta(buffer_km)
        esc["img_bbox_wgs84"] = bbox_v_buf
        render_url, _ = _render_url_para_escena(
            esc, bbox_v_buf, self._banda_idx, size=size_px)
        urls = []
        if render_url:
            urls.append(render_url)
        prev = esc.get("prev")
        if prev:
            if esc.get("tipo") == "planet":
                urls.append(prev)
            else:
                urls.append(_sign_mpc_href(prev))
        for url in urls:
            try:
                if esc.get("tipo") == "planet":
                    return _planet_http_bytes(url, max_mb=80)
                return http_bytes(url, max_mb=80)
            except Exception:
                continue
        return None

    def _refrescar_checklist(self, vecs):
        for w in self.fr_chk.winfo_children():
            w.destroy()
        self._checks = {}
        activas = 0
        for v in vecs:
            var = tk.BooleanVar(value=v.get("activo", True))
            if var.get():
                activas += 1
            uid = v.get("uid") or f"{v['oid']}_{len(self._checks)}"
            v["uid"] = uid
            self._checks[uid] = var

            fr = tk.Frame(self.fr_chk, bg=C["card"])
            fr.pack(fill="x", padx=4, pady=2)

            lbl_txt = f"[{v['cod']}] OID{v['oid']}"
            if v["area"]:
                try:
                    lbl_txt += f"  {float(v['area']):.4f} ha"
                except Exception:
                    pass
            ok = "●" if v["pts_wgs84"] else "○"

            chk = _GFPCheck(
                fr, var, bg=C["card"], accent=C["sel"],
                command=lambda v=v, var=var, fr=fr: self._on_check(v, var, fr),
            )
            chk.pack(side="left")

            lbl = tk.Label(
                fr, text=f"{ok}  {lbl_txt}",
                bg=C["card"],
                fg=C["texto"] if var.get() else C["dim"],
                font=("Segoe UI", 9),
                cursor="hand2", anchor="w",
            )
            lbl.pack(side="left", fill="x", expand=True, padx=(2, 4))
            lbl.bind("<Button-1>", lambda e, vec=v: self._sel_alerta_por_oid(vec))

        self.lbl_chk_cnt.config(text=f"{activas}/{len(vecs)} activas")

    def _on_check(self, vec, var, fr):
        vec["activo"] = var.get()
        for w in fr.winfo_children():
            if isinstance(w, tk.Label):
                w.config(fg=C["texto"] if var.get() else C["dim"])
            elif isinstance(w, _GFPCheck):
                w.redraw()

        activas = sum(1 for v in self._vect_filt if v.get("activo", True))
        self.lbl_chk_cnt.config(text=f"{activas}/{len(self._vect_filt)} activas")

        if self.vec_sel:
            kw_v = self._kwargs_vecinos()
            bbox_vec = self._bbox_union_activos()
            bbox_img = self._bbox_imagen_alerta()
            poly_sel = (
                self.vec_sel["pts_wgs84"]
                if self.vec_sel.get("activo", True) else []
            )
            cod_sel = (
                f"{self.vec_sel['cod']}·{self.vec_sel['oid']}"
                if self.vec_sel.get("activo", True) else ""
            )

            self.zc_a.set_vector(poly_sel, bbox_vec, cod_alerta=cod_sel, **kw_v)
            self.zc_d.set_vector(poly_sel, bbox_vec, cod_alerta=cod_sel, **kw_v)

            if self._pil_a and self.esc_a:
                self.zc_a.set_pil(
                    self._pil_a, self.esc_a, poly_sel, bbox_img,
                    cod_alerta=cod_sel, **kw_v,
                )
            if self._pil_d and self.esc_d:
                self.zc_d.set_pil(
                    self._pil_d, self.esc_d, poly_sel, bbox_img,
                    cod_alerta=cod_sel, **kw_v,
                )
        else:
            self._actualizar_mapa_sin_seleccion()

    def _vecinos_activos(self):
        """Polígonos activos excepto la alerta seleccionada (por uid)."""
        sel_uid = self.vec_sel.get("uid") if self.vec_sel else None
        polys, labels = [], []
        for v in self.vectores:
            if not v.get("activo", True) or not v["pts_wgs84"]:
                continue
            if sel_uid and v.get("uid") == sel_uid:
                continue
            polys.append(v["pts_wgs84"])
            labels.append(f"{v['cod']}·{v['oid']}")
        return polys, labels

    def _kwargs_vecinos(self):
        polys, labels = self._vecinos_activos()
        return {"polys_vec": polys, "vec_labels": labels}

    def _todos_activos_poligonos(self):
        return self._vecinos_activos()[0]

    def _poligonos_todos_activos(self):
        polys, labels = [], []
        for v in self.vectores:
            if v.get("activo", True) and v["pts_wgs84"]:
                polys.append(v["pts_wgs84"])
                labels.append(f"{v['cod']}·{v['oid']}")
        return polys, labels

    def _actualizar_mapa_sin_seleccion(self):
        polys, labels = self._poligonos_todos_activos()
        all_pts = []
        for poly in polys:
            all_pts.extend(poly)
        if all_pts:
            lons = [p[0] for p in all_pts]
            lats = [p[1] for p in all_pts]
            pad  = max((max(lons) - min(lons)) * 0.15, 0.01)
            bbox = [min(lons)-pad, min(lats)-pad, max(lons)+pad, max(lats)+pad]
        else:
            bbox = [0, 0, 0, 0]
        self.zc_a.set_vector([], bbox, polys, vec_labels=labels)
        self.zc_d.set_vector([], bbox, polys, vec_labels=labels)

    def _check_all(self):
        for v in self._vect_filt:
            v["activo"] = True
            uid = v.get("uid")
            if uid and uid in self._checks:
                self._checks[uid].set(True)
        self._refrescar_checklist(self._vect_filt)
        if self.vec_sel:
            kw_v = self._kwargs_vecinos()
            bbox_vec = self._bbox_union_activos()
            bbox_img = self._bbox_imagen_alerta()
            poly = self.vec_sel["pts_wgs84"]
            cod = self.vec_sel["cod"]
            if self._pil_a and self.esc_a:
                self.zc_a.set_pil(
                    self._pil_a, self.esc_a, poly, bbox_img, cod_alerta=cod, **kw_v)
            else:
                self.zc_a.set_vector(poly, bbox_vec, cod_alerta=cod, **kw_v)
            if self._pil_d and self.esc_d:
                self.zc_d.set_pil(
                    self._pil_d, self.esc_d, poly, bbox_img, cod_alerta=cod, **kw_v)
            else:
                self.zc_d.set_vector(poly, bbox_vec, cod_alerta=cod, **kw_v)

    def _check_none(self):
        for v in self._vect_filt:
            v["activo"] = False
            uid = v.get("uid")
            if uid and uid in self._checks:
                self._checks[uid].set(False)
        self._refrescar_checklist(self._vect_filt)
        if self.vec_sel:
            bbox_img = self._bbox_imagen_alerta()
            if self._pil_a and self.esc_a:
                self.zc_a.set_pil(self._pil_a, self.esc_a, [], bbox_img, [], cod_alerta="")
            else:
                self.zc_a.set_vector([], bbox_img, [], cod_alerta="")
            if self._pil_d and self.esc_d:
                self.zc_d.set_pil(self._pil_d, self.esc_d, [], bbox_img, [], cod_alerta="")
            else:
                self.zc_d.set_vector([], bbox_img, [], cod_alerta="")

    def _sel_alerta_por_oid(self, vec):
        self.vec_sel = vec
        self._mostrar_info_vector(vec)

    def _refrescar_lb(self, vecs):
        self._refrescar_checklist(vecs)
        self.lbl_cnt.config(text=f"{len(vecs)} alertas")

    def _on_filtro(self, *args):
        txt = self.v_flt.get().lower()
        filt = [v for v in self.vectores
                if txt in v["cod"].lower() or txt in v["nom"].lower()]
        self._vect_filt = filt
        self._refrescar_lb(filt)

    def _mostrar_info_vector(self, v):
        self.lbl_cod.config(text=f"[{v['cod']}] {v['nom'][:34]}")
        area_txt = f"{float(v['area']):.4f} ha" if v["area"] else "—"
        self.lbl_area.config(text=f"Area: {area_txt}")
        bb = v["bbox_wgs84"]
        if bb and bb != [0, 0, 0, 0]:
            self.lbl_bbox.config(
                text=f"WGS84: [{bb[0]:.5f},{bb[1]:.5f}  {bb[2]:.5f},{bb[3]:.5f}]")
        else:
            self.lbl_bbox.config(text="WGS84: sin coordenadas (revisar SR)")

        self._st(f"Alerta: [{v['cod']}] {v['nom'][:45]}")
        n_pts = len(v["pts_wgs84"])
        self._log(
            f"Sel: OID={v['oid']} | {v['cod']} | {n_pts} vertices WGS84",
            "ok" if n_pts > 0 else "warn")

        bbox_img = self._bbox_imagen_alerta()
        bbox_vec = self._bbox_union_activos()

        kw_v = self._kwargs_vecinos()
        poly = v["pts_wgs84"]
        cod = f"{v['cod']}·{v['oid']}"

        self.zc_a.set_vector(poly, bbox_vec, cod_alerta=cod, **kw_v)
        self.zc_d.set_vector(poly, bbox_vec, cod_alerta=cod, **kw_v)

        if n_pts == 0:
            self._log("Sin vértices WGS84 — verifica SR del FC en ArcGIS Pro", "warn")

        if self.esc_a:
            ib = bbox_img
            if self._pil_a:
                self.zc_a.set_pil(self._pil_a, self.esc_a, poly, ib, cod_alerta=cod, **kw_v)
            else:
                self.zc_a.set_escena(self.esc_a, poly, ib, cod_alerta=cod, **kw_v)
        if self.esc_d:
            ib = bbox_img
            if self._pil_d:
                self.zc_d.set_pil(self._pil_d, self.esc_d, poly, ib, cod_alerta=cod, **kw_v)
            else:
                self.zc_d.set_escena(self.esc_d, poly, ib, cod_alerta=cod, **kw_v)

    def _buscar(self):
        if not self.vec_sel:
            messagebox.showwarning("Atencion", "Selecciona una alerta primero.")
            return
        if not self.vec_sel["pts_wgs84"]:
            messagebox.showwarning(
                "Sin coordenadas WGS84",
                "Esta alerta no tiene coordenadas WGS84 válidas.\n\n"
                "Verifica el Sistema de Referencia del FC en ArcGIS Pro:\n"
                "  Layer Properties → Source → Spatial Reference\n\n"
                "Para Perú: SIRGAS 2000 / UTM o WGS 1984 / UTM Zone 18S.")
            return
        self._st("Buscando escenas...", C["amarillo"])
        self.btn_bus.config(state="disabled", text="Buscando...")
        self.lbl_escenas_info.config(
            text="Buscando imágenes…", bg=C["card2"], fg=C["dim"],
        )
        self.lbl_escenas_badge.config(
            text="Buscando imágenes…", bg=C["card2"], fg=C["dim"],
        )
        threading.Thread(target=self._buscar_hilo, daemon=True).start()

    def _buscar_hilo(self):
        try:
            self._get_buffer_km()
            fi   = dt.strptime(self.v_fi.get(), "%d/%m/%Y")
            ff   = dt.strptime(self.v_ff.get(), "%d/%m/%Y")
            maxn = self.v_nubes.get()
            sat  = self.v_sat.get()
            bbox = self.vec_sel["bbox_stac"]
            if not bbox or bbox == [0, 0, 0, 0]:
                raise RuntimeError("BBox STAC inválido — revise SR del FC.")

            if "Planet" in sat:
                esc = self._planet(bbox, fi, ff, maxn)
            elif "Sentinel" in sat:
                esc = self._sentinel(bbox, fi, ff, maxn)
            else:
                esc = self._landsat(bbox, fi, ff, maxn, sat)

            self.escenas = esc or []
            self.root.after(0, self._mostrar_escenas)
        except Exception as e:
            msg = str(e)
            self.root.after(0, lambda: self._st(f"Error: {msg}", C["rojo"]))
            self.root.after(0, lambda: self._log(f"ERROR: {msg}", "err"))
        finally:
            self.root.after(0, lambda: self.btn_bus.config(
                state="normal", text="BUSCAR ESCENAS STAC"))

    def _sentinel(self, bbox_stac, fi, ff, maxn):
        x0, y0, x1, y1 = bbox_stac
        pad = 0.05
        x0 -= pad; y0 -= pad; x1 += pad; y1 += pad
        bbox_l = [x0, y0, x1, y1]
        dt_str = (f"{fi:%Y-%m-%d}T00:00:00Z/{ff:%Y-%m-%d}T23:59:59Z")
        self.root.after(0, lambda: self._log(
            f"S2 bbox: {x0:.4f},{y0:.4f},{x1:.4f},{y1:.4f} "
            f"| {fi:%Y-%m-%d}→{ff:%Y-%m-%d} | nubes≤{maxn}%", "info"))

        body = {
            "collections": ["sentinel-2-l2a"],
            "bbox": bbox_l, "datetime": dt_str, "limit": 40,
            "query": {"eo:cloud_cover": {"lte": maxn}},
        }
        banda_key = BANDAS_S2[self._banda_idx].get("s2_key", "visual")
        bbox_wgs84 = (
            self.vec_sel.get("bbox_wgs84") if self.vec_sel else None
        )

        try:
            self.root.after(0, lambda: self._log("Probando Element84...", "info"))
            self.root.after(0, lambda: self.lbl_api.config(text="API: E84"))
            data = http_post(E84_SEARCH, body, timeout=STAC_TIMEOUT)
            feats = data.get("features", [])[:20]
            parsed = self._parse_s2(feats, maxn, "E84", banda_key)
            if parsed:
                return parsed
        except Exception as e:
            self.root.after(0, lambda err=e: self._log(f"E84: {err}", "warn"))

        try:
            self.root.after(0, lambda: self._log("Probando MPC...", "info"))
            self.root.after(0, lambda: self.lbl_api.config(text="API: MPC"))
            data = http_post(MPC_SEARCH, body, timeout=STAC_TIMEOUT)
            feats = _sign_mpc_features(data.get("features", [])[:20])
            self.root.after(0, lambda n=len(feats):
                self._log(f"MPC: {n} escenas", "ok" if n else "warn"))
            parsed = self._parse_s2(feats, maxn, "MPC", banda_key)
            if parsed:
                return parsed
        except Exception as e:
            self.root.after(0, lambda err=e: self._log(
                f"MPC falló: {err} (no bloquea — E84 ya intentó)", "warn"))

        try:
            self.root.after(0, lambda: self._log("Probando Copernicus CDSE...", "info"))
            data = http_post(CDSE_SEARCH, body, timeout=STAC_TIMEOUT)
            feats = data.get("features", [])[:20]
            parsed = self._parse_s2(feats, maxn, "CDSE", banda_key)
            if parsed:
                return parsed
        except Exception as e:
            self.root.after(0, lambda err=e: self._log(f"CDSE: {err}", "warn"))

        self.root.after(0, lambda: self._log(
            "STAC sin respuesta — usando vista GIBS (NASA) como respaldo", "warn"))
        return self._sinteticas(fi, ff, bbox_wgs84)

    def _planet(self, bbox_stac, fi, ff, maxn):
        if not _planet_disponible():
            self.root.after(0, lambda: self._log(
                "Planet: configure PLANET_API_KEY en Windows", "warn"))
            return []
        x0, y0, x1, y1 = bbox_stac
        self.root.after(0, lambda: self._log(
            f"Planet bbox {x0:.4f},{y0:.4f},{x1:.4f},{y1:.4f} | "
            f"{fi:%Y-%m-%d}→{ff:%Y-%m-%d} | nubes≤{maxn}%", "info"))
        self.root.after(0, lambda: self.lbl_api.config(text="API: Planet Data"))
        try:
            escenas = _planet_search_scenes(
                bbox_stac, fi, ff, max_cloud_pct=maxn, limit=40,
            )
            self.root.after(0, lambda n=len(escenas):
                self._log(f"Planet: {n} escenas", "ok" if n else "warn"))
            return escenas
        except Exception as e:
            self.root.after(0, lambda err=e: self._log(f"Planet error: {err}", "err"))
            return []

    def _parse_s2(self, feats, maxn, fuente, banda_key="visual"):
        res = []
        for f in feats:
            p  = f.get("properties", {})
            nc = p.get("eo:cloud_cover", p.get("s2:cloud_cover", 999))
            try:
                nc = float(nc)
            except Exception:
                nc = 999
            if nc > maxn:
                continue
            assets = f.get("assets", {})
            prev, prev_tipo = _mejor_preview_s2(assets, banda_key)
            preview_href = _stac_asset_href(
                assets, "thumbnail", "rendered_preview", "overview")
            cog_raw = _stac_asset_href(assets, "visual", "visual_tci")
            cog_visual = _url_cog_publico(cog_raw) if cog_raw else None
            if prev:
                prev = _sign_mpc_href(prev)
            if not prev and preview_href:
                prev = preview_href
                prev_tipo = "thumbnail"
            res.append({
                "id":        f.get("id", "—"),
                "fecha":     p.get("datetime", "")[:10],
                "nubes":     round(nc, 1),
                "sat":       "Sentinel-2",
                "res":       "10m",
                "prev":      prev,
                "prev_tipo": prev_tipo,
                "preview_href": preview_href or prev,
                "cog_visual": cog_visual,
                "bbox":      f.get("bbox", []),
                "api":       fuente,
                "tipo":      "s2",
                "collection": f.get("collection", "sentinel-2-l2a"),
                "asset_keys": sorted(_asset_keys(assets)),
            })
        return sorted(res, key=lambda x: x["fecha"], reverse=True)

    def _sinteticas(self, fi, ff, bbox_wgs84=None):
        res = []
        d = fi
        i = 0
        while d <= ff and i < 20:
            fecha_str = f"{d:%Y-%m-%d}"
            wms_url = _sentinel_wms_url(
                bbox_wgs84, fecha_str, size=RENDER_SIZE)
            res.append({
                "id": f"S2_GIBS_{d:%Y%m%d}",
                "fecha": fecha_str,
                "nubes": "?",
                "sat": "Sentinel-2 (GIBS)" if wms_url else "Sentinel-2 (est.)",
                "res": "10m",
                "prev": wms_url,
                "prev_tipo": "wms_gibs" if wms_url else "none",
                "bbox": bbox_wgs84 or [],
                "api": "GIBS" if wms_url else "estimado",
                "tipo": "s2",
            })
            d += timedelta(days=5)
            i += 1
        return res

    def _landsat(self, bbox_stac, fi, ff, maxn, sat):
        x0, y0, x1, y1 = bbox_stac
        pad = 0.05
        x0 -= pad; y0 -= pad; x1 += pad; y1 += pad
        plat = "landsat-9" if "9" in sat else "landsat-8"
        body = {
            "collections": ["landsat-c2-l2"],
            "bbox": [x0, y0, x1, y1],
            "datetime": f"{fi:%Y-%m-%d}T00:00:00Z/{ff:%Y-%m-%d}T23:59:59Z",
            "limit": 50,
            "query": {"eo:cloud_cover": {"lte": maxn}},
        }

        self.root.after(0, lambda: self._log(
            f"Landsat {sat} | bbox {x0:.3f},{y0:.3f},{x1:.3f},{y1:.3f}", "info"))

        try:
            body_mpc = dict(body)
            body_mpc["query"] = {
                "eo:cloud_cover": {"lte": maxn},
                "platform": {"eq": plat},
            }
            self.root.after(0, lambda: self._log("Probando MPC Landsat...", "info"))
            self.root.after(0, lambda: self.lbl_api.config(text="API: MPC LS"))
            data = http_post(MPC_SEARCH, body_mpc, timeout=STAC_TIMEOUT)
            feats = _sign_mpc_features(data.get("features", [])[:25])
            self.root.after(0, lambda n=len(feats):
                self._log(f"MPC Landsat: {n} escenas", "ok" if n else "warn"))
            res = self._parse_landsat(feats, maxn, "MPC", sat, bbox_stac, fi, ff)
            if res:
                return res
        except Exception as e:
            self.root.after(0, lambda err=e:
                self._log(f"MPC Landsat: {_err_msg(err)}", "warn"))

        try:
            self.root.after(0, lambda: self._log("Probando Landsat Element84...", "info"))
            self.root.after(0, lambda: self.lbl_api.config(text="API: E84 LS"))
            data = http_post(E84_SEARCH, body, timeout=STAC_TIMEOUT)
            feats = [
                f for f in data.get("features", [])[:40]
                if _landsat_plataforma_ok(f.get("properties", {}), sat)
            ]
            self.root.after(0, lambda n=len(feats):
                self._log(f"E84 Landsat: {n} escenas", "ok" if n else "warn"))
            res = self._parse_landsat(feats, maxn, "E84", sat, bbox_stac, fi, ff)
            if res:
                return res
        except Exception as e:
            self.root.after(0, lambda err=e:
                self._log(f"E84 Landsat: {_err_msg(err)}", "warn"))

        self.root.after(0, lambda: self._log(
            "Landsat: respaldo GIBS HLS (NASA)", "warn"))
        res = []
        d   = fi
        i   = 0
        lbl = "LC09" if "9" in sat else "LC08"
        sensor = "L9" if "9" in sat else "L8"
        bbox_v = self.vec_sel["bbox_wgs84"] if self.vec_sel else [x0, y0, x1, y1]

        while d <= ff and i < 20:
            fecha_str = f"{d:%Y-%m-%d}"
            wms_url = _landsat_wms_url(
                bbox_v, fecha_str, sensor=sensor, size=RENDER_SIZE)
            res.append({
                "id":        f"{lbl}_{d:%Y%m%d}_EST",
                "fecha":     fecha_str,
                "nubes":     "?",
                "sat":       sat,
                "res":       "30m",
                "prev":      wms_url,
                "prev_tipo": "wms_gibs",
                "bbox":      bbox_v if bbox_v != [0,0,0,0] else [],
                "api":       "GIBS",
                "tipo":      "landsat",
            })
            d += timedelta(days=16)
            i += 1
        return res

    def _parse_landsat(self, feats, maxn, fuente, sat, bbox_stac, fi, ff):
        res = []
        for f in feats:
            p  = f.get("properties", {})
            nc = p.get("eo:cloud_cover", 999)
            try:
                nc = float(nc)
            except Exception:
                nc = 999
            if nc > maxn:
                continue
            assets = f.get("assets", {})
            prev, prev_tipo = _mejor_preview_landsat(assets, fuente)
            preview_href = _url_preview_landsat(
                _stac_asset_href(
                    assets, "reduced_resolution_browse", "thumbnail",
                    "rendered_preview", "overview"),
                fuente,
            )
            cog_visual = None
            if prev and fuente == "MPC":
                prev = _sign_mpc_href(prev)

            fecha_str = p.get("datetime", "")[:10]
            bbox_v = (
                self.vec_sel["bbox_wgs84"] if self.vec_sel
                else f.get("bbox", [])
            )
            sensor = "L9" if "9" in sat else "L8"
            if not prev:
                prev = _landsat_wms_url(
                    bbox_v, fecha_str, sensor=sensor, size=RENDER_SIZE)
                prev_tipo = "wms_gibs" if prev else "none"
                if prev:
                    self.root.after(0, lambda:
                        self._log("  → GIBS WMS centrado en alerta (Landsat)", "info"))

            res.append({
                "id":        f.get("id", "—"),
                "fecha":     fecha_str,
                "nubes":     round(nc, 1),
                "sat":       sat,
                "res":       "30m",
                "prev":      prev,
                "prev_tipo": prev_tipo,
                "preview_href": preview_href or prev,
                "cog_visual": cog_visual,
                "bbox":      f.get("bbox", []),
                "api":       fuente,
                "tipo":      "landsat",
                "collection": f.get("collection", "landsat-c2-l2"),
                "asset_keys": sorted(_asset_keys(assets)),
            })

        return sorted(res, key=lambda x: x["fecha"], reverse=True) if res else []

    def _actualizar_badge_escenas(self, n):
        if n <= 0:
            txt = "Sin imágenes — amplíe fechas o suba el % de nubes."
            bg, fg = C["card2"], C["dim"]
        elif n == 1:
            txt = "✓  1 imagen encontrada"
            bg, fg = "#E3F2FD", "#1565C0"
        else:
            txt = f"✓  {n} imágenes encontradas"
            bg, fg = "#E3F2FD", "#1565C0"
        for lbl in (getattr(self, "lbl_escenas_info", None),
                    getattr(self, "lbl_escenas_badge", None)):
            if lbl:
                lbl.config(text=txt, bg=bg, fg=fg, font=("Segoe UI", 10, "bold"))

    def _mostrar_escenas(self):
        self.esc_a = None
        self.esc_d = None
        self._pil_a = self._pil_d = None
        for w in self.fr_esc.winfo_children():
            w.destroy()
        self.btn_bus.config(state="normal", text="BUSCAR ESCENAS STAC")
        self.cv_esc.yview_moveto(0)
        if not self.escenas:
            self._actualizar_badge_escenas(0)
            self._st("Sin escenas", C["amarillo"])
            self.lbl_cnt.config(text="0 imágenes")
            return
        n = len(self.escenas)
        self._actualizar_badge_escenas(n)
        self._st(f"{n} imágenes encontradas")
        self.lbl_cnt.config(text=f"{n} imágenes")
        for i, e in enumerate(self.escenas):
            self._card_esc(i, e)
        self.cv_esc.update_idletasks()
        self.cv_esc.configure(scrollregion=self.cv_esc.bbox("all"))
        self.cv_esc.yview_moveto(0)

    def _preparar_ui_carga(self):
        """Muestra 'Descargando…' en los paneles antes de iniciar hilos."""
        if not self.vec_sel:
            return
        poly = self.vec_sel["pts_wgs84"]
        bbox = self._bbox_imagen_alerta()
        kw_v = self._kwargs_vecinos()
        cod = f"{self.vec_sel['cod']}·{self.vec_sel['oid']}"
        if self.esc_a:
            self.zc_a.set_escena(
                self.esc_a, poly, bbox, cod_alerta=cod, **kw_v)
        if self.esc_d:
            self.zc_d.set_escena(
                self.esc_d, poly, bbox, cod_alerta=cod, **kw_v)
        try:
            self.btn_cargar_img.config(
                state="disabled", text="Descargando imágenes…")
        except Exception:
            pass

    def _fin_carga_imagen(self):
        self._img_pending = max(0, self._img_pending - 1)
        if self._img_pending <= 0:
            self._img_pending = 0
            try:
                self.btn_cargar_img.config(
                    state="normal",
                    text="CARGAR IMÁGENES ANTES / DESPUÉS",
                )
            except Exception:
                pass

    def _cargar_imagenes_visor(self, silencioso=False):
        """Carga las escenas marcadas como ANTES y DESPUÉS."""
        if not self.vec_sel:
            if not silencioso:
                messagebox.showwarning(
                    "Atención", "Seleccione una alerta en el paso 1.")
            return
        if not self.esc_a and not self.esc_d:
            if not silencioso:
                messagebox.showwarning(
                    "Sin escenas",
                    "Marque al menos una escena como ANTES o DESPUÉS\n"
                    "en la lista de escenas encontradas.",
                )
            return
        if not self.esc_a or not self.esc_d:
            if not silencioso:
                messagebox.showwarning(
                    "Faltan escenas",
                    "Marque una escena ANTES y otra DESPUÉS antes de cargar.",
                )
            return
        _IMG_CACHE.clear()
        self._preparar_ui_carga()
        self._log("Cargando imágenes ANTES/DESPUÉS…", "info")
        self._img_pending = 2
        threading.Thread(
            target=self._img_hilo, args=(self.esc_a, "a"), daemon=True,
        ).start()
        threading.Thread(
            target=self._img_hilo, args=(self.esc_d, "d"), daemon=True,
        ).start()

    def _auto_cargar_si_listo(self):
        self._cargar_timer = None
        if self.esc_a and self.esc_d and self.vec_sel:
            self._cargar_imagenes_visor(silencioso=True)

    def _card_esc(self, idx, esc):
        COL = {"E84": C["verde"], "MPC": C["azul2"], "ELE": C["verde"],
               "CDSE": C["purp"], "GIBS": C["teal"], "estimado": C["rojo"]}
        ICONO_PREV = {
            "rendered_preview": "★", "visual_tci": "◉", "overview": "○",
            "thumbnail": "·", "wms_gibs": "≋", "none": "✗",
        }
        card = tk.Frame(self.fr_esc, bg=C["card"], cursor="hand2")
        card.pack(fill="x", padx=4, pady=2)

        h = tk.Frame(card, bg=C["card"])
        h.pack(fill="x", padx=6, pady=(4, 0))
        tk.Label(h, text=f"#{idx+1:02d}", bg=C["card"], fg=C["dim"],
                 font=("Consolas", 7)).pack(side="left")
        fecha_raw = esc.get("fecha", "—")
        try:
            fecha_str = dt.strptime(fecha_raw, "%Y-%m-%d").strftime("%d %b %Y")
        except Exception:
            fecha_str = fecha_raw
        tk.Label(h, text=fecha_str, bg=C["card"], fg=C["texto"],
                 font=("Consolas", 9, "bold")).pack(side="left", padx=4)
        api_lbl = esc.get("api", "?")
        tk.Label(h, text=f"[{api_lbl}]", bg=C["card"],
                 fg=COL.get(api_lbl, C["dim"]),
                 font=("Consolas", 7)).pack(side="left")
        nc = esc.get("nubes", "?")
        nc_lbl = f"☁ {nc}%" if nc not in ("N/A", "?") else "☁ ?"
        tk.Label(h, text=nc_lbl, bg=C["card"], fg=C["dim"],
                 font=("Consolas", 7)).pack(side="right")

        id_c = (esc["id"][:34] + "…") if len(esc["id"]) > 34 else esc["id"]
        tk.Label(card, text=id_c, bg=C["card"], fg=C["dim"],
                 font=("Consolas", 6)).pack(fill="x", padx=6)

        pt = esc.get("prev_tipo", "none")
        ic = ICONO_PREV.get(pt, "?")
        col_ic = (C["verde"] if pt == "rendered_preview" else
                  C["teal"]  if pt == "wms_gibs" else
                  C["azul2"] if pt in ("visual_tci", "overview", "thumbnail") else
                  C["dim"])
        tk.Label(card, text=f"{esc['sat']}  {esc['res']}  {ic}{pt}",
                 bg=C["card"], fg=col_ic, font=("Consolas", 7)).pack(anchor="w", padx=6)

        fb = tk.Frame(card, bg=C["card"])
        fb.pack(fill="x", padx=6, pady=(2, 4))
        tk.Button(fb, text="◀  ANTES", bg="#1A3A5C", fg="white",
                  font=("Consolas", 7), relief="flat", cursor="hand2",
                  padx=4, pady=2,
                  command=lambda e=esc: self._marcar("a", e)).pack(side="left", padx=(0, 2))
        tk.Button(fb, text="DESPUES  ▶", bg=C["sel"], fg="white",
                  font=("Consolas", 7), relief="flat", cursor="hand2",
                  padx=4, pady=2,
                  command=lambda e=esc: self._marcar("d", e)).pack(side="left", padx=(0, 2))

        def _on_enter(e, c=card):
            c.config(bg=C["hover"])

        def _on_leave(e, c=card):
            c.config(bg=C["card"])

        def _scroll_card(e):
            delta = -1 if (e.delta > 0 or e.num == 4) else 1
            top, bottom = self.cv_esc.yview()
            if delta < 0 and top <= 0.001:
                return "break"
            if delta > 0 and bottom >= 0.999:
                return "break"
            self.cv_esc.yview_scroll(delta, "units")
            return "break"

        for w in [card] + list(card.winfo_children()):
            w.bind("<Enter>",      _on_enter)
            w.bind("<Leave>",      _on_leave)
            w.bind("<MouseWheel>", _scroll_card)
            w.bind("<Button-4>",   _scroll_card)
            w.bind("<Button-5>",   _scroll_card)

    def _marcar(self, lado, esc):
        fecha_raw = esc.get("fecha", "—")
        try:
            fecha_str = dt.strptime(fecha_raw, "%Y-%m-%d").strftime("%d %b %Y")
        except Exception:
            fecha_str = fecha_raw

        if lado == "a":
            self.esc_a = esc
            self.lbl_fa.config(text=fecha_str)
            self.lbl_id_a.config(text=f"ID: {esc['id'][:52]}")
            self.lbl_sat_a.config(text=esc["sat"])
        else:
            self.esc_d = esc
            self.lbl_fd.config(text=fecha_str)
            self.lbl_id_d.config(text=f"ID: {esc['id'][:52]}")
            self.lbl_sat_d.config(text=esc["sat"])

        self._upd_info(esc, lado)
        etiq = "ANTES" if lado == "a" else "DESPUES"
        self._st(f"{etiq} seleccionado: {fecha_str}  |  {esc['sat']}")
        self._log(
            f"{etiq} marcado: {esc['id'][:62]} | {esc.get('api','?')} "
            f"| preview={esc.get('prev_tipo','?')}",
            "info",
        )
        if self.vec_sel:
            poly = self.vec_sel["pts_wgs84"]
            bbox = self._bbox_imagen_alerta()
            kw_v = self._kwargs_vecinos()
            cod = f"{self.vec_sel['cod']}·{self.vec_sel['oid']}"
            zc = self.zc_a if lado == "a" else self.zc_d
            zc.set_escena(esc, poly, bbox, cod_alerta=cod, **kw_v)
        if self.esc_a and self.esc_d:
            if self._cargar_timer:
                self.root.after_cancel(self._cargar_timer)
            self._cargar_timer = self.root.after(
                400, self._auto_cargar_si_listo)

    def _upd_info(self, esc, lado):
        inf = self.info_a if lado == "a" else self.info_d
        iid = esc["id"]
        inf["sat"].config(text=esc.get("sat", "—"))
        inf["id"].config(text=(iid[:24] + "…") if len(iid) > 24 else iid)
        fecha_raw = esc.get("fecha", "—")
        try:
            fecha_str = dt.strptime(fecha_raw, "%Y-%m-%d").strftime("%d %b %Y")
        except Exception:
            fecha_str = fecha_raw
        inf["fecha"].config(text=fecha_str)
        inf["nubes"].config(text=str(esc.get("nubes", "—")))
        inf["res"].config(text=esc.get("res", "—"))
        inf["api"].config(text=esc.get("api", "—"))
        if "prev_tipo" in inf:
            inf["prev_tipo"].config(text=esc.get("prev_tipo", "—"))

    def _img_hilo(self, esc, lado):
        if not self.vec_sel:
            return
        if lado in self._img_en_curso:
            return
        self._img_en_curso.add(lado)
        try:
            self._img_hilo_core(esc, lado)
        finally:
            self._img_en_curso.discard(lado)
            self.root.after(0, self._fin_carga_imagen)

    def _img_hilo_core(self, esc, lado):
        from PIL import Image

        poly        = self.vec_sel["pts_wgs84"]
        buffer_km   = self._get_buffer_km()
        bbox_v_buf  = self._bbox_imagen_alerta(buffer_km)
        kw_v        = self._kwargs_vecinos()
        polys_v     = kw_v["polys_vec"]
        labels_v    = kw_v["vec_labels"]
        cod         = f"{self.vec_sel['cod']}·{self.vec_sel['oid']}"
        es_idx      = _es_banda_indice(self._banda_idx)
        zc          = self.zc_a if lado == "a" else self.zc_d
        esc["img_bbox_wgs84"] = bbox_v_buf
        ckey = _img_cache_key(esc.get("id"), self._banda_idx, buffer_km, lado, bbox_v_buf)

        x0, y0, x1, y1 = bbox_v_buf
        cy = (y0 + y1) / 2
        ancho_km = abs(x1 - x0) * 111.0 * math.cos(math.radians(cy))
        self.root.after(0, lambda l=lado, bk=buffer_km, ak=ancho_km:
            self._log(
                f"Img {l}: alerta+buffer {bk}km | extensión {ak:.1f}km | "
                f"{RENDER_SIZE}px", "info"))

        cached = _img_cache_get(ckey)
        if cached and self.pil:
            img_vis = cached.copy()
            if lado == "a":
                self._pil_a = img_vis
            else:
                self._pil_d = img_vis
            self.root.after(0, lambda iv=img_vis, es=esc:
                zc.set_pil(iv, es, poly, bbox_v_buf, polys_v,
                           cod_alerta=cod, vec_labels=labels_v, crop_ok=True))
            self.root.after(0, lambda: self._log(f"Cache OK ({lado})", "ok"))
            self.root.after(0, lambda e=esc, l=lado: self._upd_info(e, l))
            return

        if esc.get("tipo") == "planet":
            try:
                width = min(max(RENDER_SIZE, 1024), 2048)
                thumb = _planet_thumbnail_url(
                    esc.get("item_type", "PSScene"), esc.get("id"), width=width)
                data_p = _planet_http_bytes(thumb, max_mb=40)
                if data_p[:8] == b"\x89PNG\r\n\x1a\n":
                    img_p = Image.open(io.BytesIO(data_p)).convert("RGB")
                    if max(img_p.size) > RENDER_SIZE:
                        rs = getattr(Image, "LANCZOS",
                                     getattr(Image, "BICUBIC", Image.BILINEAR))
                        img_p = img_p.resize((RENDER_SIZE, RENDER_SIZE), rs)
                    if _imagen_rgb_valida(img_p):
                        img_p = _preparar_imagen_visor(img_p, es_indice=False)
                        _img_cache_put(ckey, img_p)
                        if lado == "a":
                            self._pil_a = img_p.copy()
                        else:
                            self._pil_d = img_p.copy()
                        self.root.after(0, lambda iv=img_p.copy(), es=esc:
                            zc.set_pil(iv, es, poly, bbox_v_buf, polys_v,
                                       cod_alerta=cod, vec_labels=labels_v,
                                       crop_ok=True))
                        self.root.after(0, lambda: self._log(
                            f"Planet thumbnail OK ({lado})", "ok"))
                        self.root.after(0, lambda e=esc, l=lado: self._upd_info(e, l))
                        return
            except Exception as ex:
                self.root.after(0, lambda err=ex: self._log(
                    f"Planet imagen: {err}", "warn"))

        prev_url = esc.get("prev")
        preview_ok = False
        if es_idx and esc.get("tipo") == "planet":
            self.root.after(0, lambda:
                self._log(
                    "NDVI/NBR no disponible en Planet — use Sentinel-2 o Landsat",
                    "warn",
                ))
            self.root.after(0, lambda:
                zc.set_escena(esc, poly, bbox_v_buf, polys_v, cod_alerta=cod,
                              vec_labels=labels_v))
            return
        if prev_url and self.pil and not es_idx and esc.get("tipo") != "s2":
            try:
                if esc.get("tipo") == "planet":
                    data_prev = _planet_http_bytes(prev_url, max_mb=12)
                else:
                    prev_get = (
                        prev_url
                        if "planetarycomputer" not in str(prev_url).lower()
                        else _sign_mpc_href(prev_url)
                    )
                    data_prev = http_bytes(prev_get, max_mb=12, timeout=STAC_TIMEOUT)
                if not _http_resp_es_imagen(data_prev):
                    raise ValueError("preview no es imagen válida (HTML/error)")
                es_ls = esc.get("tipo") == "landsat"
                es_s2 = esc.get("tipo") == "s2"
                img_prev = _bytes_a_pil(
                    data_prev,
                    size_px=RENDER_SIZE if es_ls else None,
                )
                if img_prev and _imagen_rgb_valida(
                        img_prev, min_span=3 if es_ls else 6,
                        es_landsat=es_ls):
                        img_prev = _preparar_imagen_visor(img_prev, es_indice=False)
                        img_prev, crop_prev = _finalizar_imagen_visor(
                            img_prev, esc, bbox_v_buf, RENDER_SIZE,
                            render_tipo=esc.get("prev_tipo"))
                        preview_ok = True
                        mostrar_prev = not (es_s2 and not es_idx)
                        if mostrar_prev:
                            _img_cache_put(ckey, img_prev)
                            if lado == "a":
                                self._pil_a = img_prev.copy()
                            else:
                                self._pil_d = img_prev.copy()
                            self.root.after(0, lambda iv=img_prev.copy(), es=esc, cp=crop_prev:
                                zc.set_pil(iv, es, poly, bbox_v_buf, polys_v,
                                           cod_alerta=cod, vec_labels=labels_v,
                                           crop_ok=cp))
                        prev_lbl = (
                            "GIBS WMS" if esc.get("prev_tipo") == "wms_gibs"
                            else "STAC"
                        )
                        self.root.after(0, lambda l=lado, pl=prev_lbl:
                            self._log(f"Preview {pl} ({l}) OK", "ok"))
                        if esc.get("prev_tipo") == "wms_gibs":
                            self.root.after(0, lambda e=esc, l=lado:
                                self._upd_info(e, l))
                            return
                        self.root.after(0, lambda l=lado:
                            self._log(f"Cargando HD ({l})…", "info"))
            except Exception as ex:
                self.root.after(0, lambda err=ex:
                    self._log(f"Preview falló ({lado}): {err}", "warn"))

        render_url, render_tipo = _render_url_para_escena(
            esc, bbox_v_buf, self._banda_idx, size=RENDER_SIZE)

        if esc.get("tipo") == "planet" and not render_url:
            if not preview_ok:
                self.root.after(0, lambda:
                    zc.set_escena(esc, poly, bbox_v_buf, polys_v, cod_alerta=cod,
                                  vec_labels=labels_v))
            return

        if not render_url or not self.pil:
            if not preview_ok:
                self.root.after(0, lambda:
                    zc.set_escena(esc, poly, bbox_v_buf, polys_v, cod_alerta=cod,
                                  vec_labels=labels_v))
            return

        try:
            es_ls = esc.get("tipo") == "landsat"
            img_proc = None
            if es_ls:
                self.root.after(0, lambda:
                    self._log(f"Descargando [mpc_landsat_rgb] ({lado})...", "info"))
                img_proc, render_tipo = _descargar_landsat_mpc(
                    esc, bbox_v_buf, self._banda_idx, RENDER_SIZE)
            if img_proc is None:
                self.root.after(0, lambda t=render_tipo:
                    self._log(f"Descargando [{t}] ({lado})...", "info"))
                img_proc = _descargar_imagen_render(
                    render_url, RENDER_SIZE, es_indice=es_idx, es_landsat=es_ls)
            if img_proc is None and "visual" in set(esc.get("asset_keys", [])) and not es_idx:
                fb = {"assets": ["visual"], "nodata": "0", "natural": True}
                url_fb = _pc_bbox_render_url(
                    esc.get("collection"), esc.get("id"),
                    bbox_v_buf, fb, size=RENDER_SIZE)
                if url_fb:
                    self.root.after(0, lambda:
                        self._log(f"Reintento asset visual ({lado})…", "warn"))
                    img_proc = _descargar_imagen_render(
                        url_fb, RENDER_SIZE, es_landsat=es_ls)
                    if img_proc:
                        render_tipo = "pc_visual_tci"
            cog_hd = str(esc.get("cog_visual") or "")
            if (img_proc is None and not es_ls
                    and cog_hd.lower().endswith((".tif", ".tiff"))):
                turl = _titiler_cog_bbox_url(
                    esc["cog_visual"], bbox_v_buf, RENDER_SIZE)
                if turl:
                    self.root.after(0, lambda:
                        self._log(f"Reintento Titiler COG ({lado})…", "warn"))
                    img_proc = _descargar_imagen_render(
                        turl, RENDER_SIZE, es_landsat=False)
                    if img_proc:
                        render_tipo = "titiler_tci"
            if img_proc is None and prev_url:
                prev_get = (
                    prev_url
                    if "planetarycomputer" not in str(prev_url).lower()
                    else _sign_mpc_href(prev_url)
                )
                data_fb = http_bytes(prev_get, max_mb=15, timeout=STAC_TIMEOUT)
                if not _http_resp_es_imagen(data_fb):
                    img_proc = None
                else:
                    img_proc = _bytes_a_pil(data_fb, size_px=RENDER_SIZE)
                if img_proc and not _imagen_rgb_valida(
                        img_proc, min_span=4 if es_idx else 6):
                    img_proc = None
                elif img_proc:
                    render_tipo = esc.get("prev_tipo", "preview")
            if (img_proc is None and not es_ls
                    and cog_hd.lower().endswith((".tif", ".tiff"))):
                turl = _titiler_cog_bbox_url(
                    esc["cog_visual"], bbox_v_buf, RENDER_SIZE)
                if turl:
                    self.root.after(0, lambda:
                        self._log(f"Reintento Titiler COG ({lado})…", "warn"))
                    img_proc = _descargar_imagen_render(
                        turl, RENDER_SIZE, es_indice=es_idx)
                    if img_proc:
                        render_tipo = "titiler_tci"
            if img_proc is None and esc.get("fecha") and not es_ls:
                wms = _sentinel_wms_url(
                    bbox_v_buf, esc["fecha"], size=RENDER_SIZE)
                if wms:
                    self.root.after(0, lambda:
                        self._log(f"Respaldo GIBS NASA ({lado})…", "warn"))
                    img_proc = _descargar_imagen_render(
                        wms, RENDER_SIZE, es_indice=False)
                    if img_proc:
                        render_tipo = "wms_gibs"
            if img_proc is None:
                if preview_ok:
                    self.root.after(0, lambda l=lado:
                        self._log(f"HD omitido — se mantiene preview ({l})", "warn"))
                    return
                raise ValueError("Imagen inválida o rescale incorrecto")
            W0, H0 = img_proc.size
            if max(W0, H0) < int(RENDER_SIZE * 0.5):
                raise ValueError(
                    f"Imagen HD demasiado pequeña ({W0}x{H0}) — reintente")
            rt = render_tipo or "pc_bbox"
            esc["prev_tipo"] = rt
            img_vis = _preparar_imagen_visor(img_proc, es_indice=es_idx)
            img_vis, crop_ok = _finalizar_imagen_visor(
                img_vis, esc, bbox_v_buf, RENDER_SIZE, render_tipo=rt)
            _img_cache_put(ckey, img_vis)
            img_final = self._overlay(img_vis, esc, lado)
            if lado == "a":
                self._pil_a = img_vis
                self._pil_a_bar = img_final
            else:
                self._pil_d = img_vis
                self._pil_d_bar = img_final
            self.root.after(0, lambda w=W0, h=H0, l=lado:
                self._log(f"OK visor {RENDER_SIZE}px ({l}) — {w}x{h}", "ok"))
            self.root.after(0, lambda e=esc, l=lado: self._upd_info(e, l))

            self.root.after(0, lambda iv=img_vis, es=esc, z=zc, p=poly,
                            b=bbox_v_buf, pv=polys_v, lv=labels_v, c=cod, cp=crop_ok:
                z.set_pil(iv, es, p, b, pv, cod_alerta=c, vec_labels=lv,
                          crop_ok=cp))
        except Exception as e:
            self.root.after(0, lambda err=e:
                self._log(f"Error imagen [{lado}]: {err}", "warn"))
            if not preview_ok:
                self.root.after(0, lambda:
                    zc.set_escena(esc, poly, bbox_v_buf, polys_v, cod_alerta=cod,
                                  vec_labels=labels_v))
            else:
                self.root.after(0, lambda l=lado:
                    self._log(f"Se mantiene preview ({l}) tras fallo HD", "warn"))

    def _overlay(self, img, esc, lado):
        if not self.pil:
            return img
        try:
            from PIL import ImageDraw, ImageFont
            try:
                fnt    = ImageFont.truetype("consola.ttf", 14)
                fnt_sm = ImageFont.truetype("consola.ttf", 10)
            except Exception:
                fnt = fnt_sm = ImageFont.load_default()
            W, H    = img.size
            col_e   = (39, 174, 96) if lado == "a" else (46, 204, 113)
            overlay = img.copy().convert("RGBA")
            draw    = ImageDraw.Draw(overlay)
            draw.rectangle([0, 0, W, 38], fill=(8, 15, 26, 210))
            etiq = "◀ ANTES" if lado == "a" else "DESPUES ▶"
            fecha_raw = esc.get("fecha", "")
            try:
                fecha_str = dt.strptime(fecha_raw, "%Y-%m-%d").strftime("%d %b %Y")
            except Exception:
                fecha_str = fecha_raw
            draw.text((8, 6),    etiq,      fill=col_e,          font=fnt)
            draw.text((110, 8),  fecha_str, fill=(236, 240, 241), font=fnt)
            draw.text((240, 10), f"☁{esc.get('nubes','?')}%",
                       fill=(127, 140, 141), font=fnt_sm)
            pt = esc.get("prev_tipo", "")
            draw.text((8, H - 16),
                       f"{esc['sat']}  |  {esc.get('api','?')}  |  {esc.get('res','?')}  |  {pt}",
                       fill=(127, 140, 141), font=fnt_sm)
            return overlay.convert("RGB")
        except Exception:
            return img

    def _anim_toggle(self):
        if self.anim_on:
            self.anim_on = False
            self.btn_anim.config(text="Animacion", bg=C["azul"])
        else:
            if not self.esc_a or not self.esc_d:
                messagebox.showinfo("Animacion", "Selecciona ANTES y DESPUES primero.")
                return
            self.anim_on = True
            self.btn_anim.config(text="Detener", bg=C["rojo"])
            self._anim_ciclo()

    def _anim_ciclo(self):
        if not self.anim_on:
            return
        self.anim_idx = (self.anim_idx + 1) % 2
        pil = self._pil_a if self.anim_idx == 0 else self._pil_d
        esc = self.esc_a  if self.anim_idx == 0 else self.esc_d
        if not self.vec_sel:
            return
        poly    = self.vec_sel["pts_wgs84"]
        bbox_v  = self._bbox_imagen_alerta()
        kw_v    = self._kwargs_vecinos()
        cod     = f"{self.vec_sel['cod']}·{self.vec_sel['oid']}"
        if pil:
            self.zc_d.set_pil(
                pil, esc, poly, bbox_v, cod_alerta=cod, **kw_v)
        elif esc:
            self.zc_d.set_escena(
                esc, poly, bbox_v, cod_alerta=cod, **kw_v)
        self.root.after(1500, self._anim_ciclo)

    def _cargar_arcgis(self):
        if not self.esc_a and not self.esc_d:
            messagebox.showwarning("Atencion", "Marca al menos ANTES o DESPUES.")
            return
        if not self.vec_sel:
            messagebox.showwarning("Atencion", "Selecciona una alerta.")
            return
        if not self.arcgis_mapa_nombre:
            messagebox.showerror("Sin mapa ArcGIS",
                "No hay mapa activo.\n\nAlternativa: usa 'Exportar HTML Interactivo'.")
            return
        if self.callback_geotiff:
            self._st("Cargando GeoTIFF en HD...", C["amarillo"])
            self.callback_geotiff(self.esc_a, self.esc_d, self.vec_sel)
        else:
            messagebox.showinfo("Info", "El callback de ArcGIS no está disponible.")

    def _alertas_activas(self):
        return _alertas_activas_lista(self.vectores)

    def _aplicar_tabla(self):
        activas = self._alertas_activas()
        if not activas:
            messagebox.showwarning("Atencion", "Active al menos una alerta.")
            return
        if not self.esc_a and not self.esc_d:
            messagebox.showwarning("Atencion", "Marca ANTES o DESPUES.")
            return
        oids = list(dict.fromkeys(v["oid"] for v in activas))
        self._tabla_req = {
            "oids":  oids,
            "esc_a": self.esc_a,
            "esc_d": self.esc_d,
        }
        if len(oids) == 1:
            det = f"OID {oids[0]}"
        else:
            det = f"{len(oids)} alertas: " + ", ".join(f"OID {o}" for o in oids)
        messagebox.showinfo(
            "Tabla",
            f"Solicitud registrada para {det}.\n"
            "Cierra el visor para aplicar cambios a la tabla.",
        )

    def _exportar_html(self):
        if not self.esc_a or not self.esc_d:
            messagebox.showwarning("Atencion", "Marca ANTES y DESPUES.")
            return
        from tkinter import filedialog
        cod = self.vec_sel["cod"] if self.vec_sel else "alerta"
        nom = self.vec_sel["nom"] if self.vec_sel else "—"
        ruta = filedialog.asksaveasfilename(
            defaultextension=".html",
            filetypes=[("HTML", "*.html")],
            initialfile=f"ATD_{cod}.html")
        if not ruta:
            return

        bb    = self.vec_sel["bbox_wgs84"] if self.vec_sel else [0, 0, 0, 0]
        lat_c = (bb[1] + bb[3]) / 2
        lon_c = (bb[0] + bb[2]) / 2
        ea    = self.esc_a
        ed    = self.esc_d
        pts   = self.vec_sel["pts_wgs84"] if self.vec_sel else []
        coords_str   = ",".join(f"[{lat},{lon}]" for lon, lat in pts)
        geojson_coords = f"[{coords_str}]" if pts else "[]"

        def _fmt(f):
            try:
                return dt.strptime(f, "%Y-%m-%d").strftime("%d %b %Y")
            except Exception:
                return f

        html = f"""<!DOCTYPE html>
<html lang="es"><head>
<meta charset="UTF-8"><title>GFP — {cod}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
body{{margin:0;font-family:Consolas,monospace;background:#0B1622;color:#E8EDF2}}
#hdr{{background:#080F1A;padding:10px 20px;border-bottom:2px solid #27AE60}}
#hdr h1{{font-size:14px;color:#27AE60;margin:0}}
#mapa{{height:calc(100vh - 80px)}}
#bar{{background:#0F1E30;padding:6px 20px;font-size:10px;color:#6B7C8D;
      display:flex;gap:20px;flex-wrap:wrap;border-top:1px solid #182A3E}}
.a{{color:#3498DB;font-weight:bold}}.d{{color:#27AE60;font-weight:bold}}
</style></head><body>
<div id="hdr">
  <h1>GFP Subnacional — [{cod}] {nom}</h1>
</div>
<div id="mapa"></div>
<div id="bar">
  <span>ACR: <b>{cod}</b></span>
  <span>ANTES: <span class="a">{_fmt(ea['fecha'])}</span>&nbsp;{ea['sat']}&nbsp;☁{ea['nubes']}%</span>
  <span>DESPUES: <span class="d">{_fmt(ed['fecha'])}</span>&nbsp;{ed['sat']}&nbsp;☁{ed['nubes']}%</span>
</div>
<script>
var map=L.map('mapa').setView([{lat_c:.5f},{lon_c:.5f}],14);
var osm=L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',
  {{attribution:'OSM',maxZoom:19}}).addTo(map);
var esri=L.tileLayer(
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',
  {{attribution:'ESRI',maxZoom:19}});
L.control.layers({{"OSM":osm,"Satelite (ESRI)":esri}},{{}},{{collapsed:false}}).addTo(map);
L.control.scale({{metric:true,imperial:false}}).addTo(map);
var pts={geojson_coords};
if(pts.length>0){{
  var poly=L.polygon(pts,{{color:'#FF2222',weight:3,fill:true,fillColor:'#FF2222',fillOpacity:0.20}})
    .addTo(map).bindPopup('<b>[{cod}] {nom}</b><br>ANTES:{_fmt(ea["fecha"])}<br>DESPUES:{_fmt(ed["fecha"])}').openPopup();
  map.fitBounds(poly.getBounds().pad(0.18));
}}
</script></body></html>"""

        with open(ruta, "w", encoding="utf-8") as f:
            f.write(html)
        self._st(f"HTML: {os.path.basename(ruta)}")
        self._log(f"HTML exportado: {ruta}", "ok")
        messagebox.showinfo("HTML exportado", f"Visor guardado:\n{ruta}")

# ─── TOOLBOX ──────────────────────────────────────────────────────────────────

class Toolbox(object):
    def __init__(self):
        self.label       = (
            "Geo Herramienta 2 — Visor de imágenes satelitales para "
            "fotointerpretación de las causas de deforestación"
        )
        self.alias       = "ATD_H2_VisorSatelital"
        self.description = (
            "ATD TOOLBOX H2 v7 — GFP Subnacional\n"
            "Flujo USGS: 1.Datos → 2.Satélite → 3.Resultados → 4.Exportar.\n"
            "Landsat MPC firmado, alertas on/off, export HD a TOC."
        )
        self.tools = [VisualizarSatelital]


def _gdb_desde_fc(fc_path):
    """Obtiene la GDB del FC de alertas (sin parametro GDB en la UI)."""
    if not fc_path:
        return None
    try:
        desc = arcpy.Describe(fc_path)
        cat = getattr(desc, "catalogPath", None) or str(fc_path)
        if ".gdb" in cat.lower():
            i = cat.lower().index(".gdb")
            return cat[: i + 4]
        ws = getattr(desc, "path", None) or getattr(desc, "workspacePath", None)
        if ws and str(ws).lower().endswith(".gdb"):
            return str(ws)
    except Exception:
        pass
    s = str(fc_path)
    if ".gdb" in s.lower():
        i = s.lower().index(".gdb")
        return s[: i + 4]
    return None


def _detectar_anno_defecto(fc_path):
    """Año con alertas: actual si hay datos; si no, el máximo en el FC."""
    anio = dt.now().year
    try:
        campos = {f.name.lower(): f.name for f in arcpy.ListFields(fc_path)}
        if "md_anno" not in campos:
            return str(anio)
        col = campos["md_anno"]
        lyr = "__atd_h2_anno__"
        try:
            if arcpy.Exists(lyr):
                arcpy.management.Delete(lyr)
            arcpy.management.MakeFeatureLayer(
                fc_path, lyr, f"{col} = {anio}")
            if int(arcpy.management.GetCount(lyr)[0]) > 0:
                return str(anio)
        finally:
            if arcpy.Exists(lyr):
                arcpy.management.Delete(lyr)
        stats = os.path.join("in_memory", "atd_max_anno")
        if arcpy.Exists(stats):
            arcpy.management.Delete(stats)
        arcpy.analysis.Statistics(fc_path, stats, [[col, "MAX"]])
        max_col = f"MAX_{col}"
        with arcpy.da.SearchCursor(stats, [max_col]) as cur:
            for row in cur:
                if row[0] is not None:
                    return str(int(row[0]))
    except Exception:
        pass
    return str(anio)


def _fc_nombre_base(fc_path):
    """Nombre de FC sin ruta GDB ni extension de capa."""
    s = str(fc_path or "").replace("\\", "/")
    if ".gdb/" in s.lower():
        i = s.lower().rindex(".gdb/")
        s = s[i + 5:]
    return os.path.basename(s).split(".")[0]


def _fc_es_vigente(fc_path):
    """MonitoreoDeforestacion = alertas del año en curso (sin md_anno)."""
    return _fc_nombre_base(fc_path) == "MonitoreoDeforestacion"


def _fc_accesible(fc):
    """Comprueba que la capa o FC sea legible."""
    if not fc:
        return False
    try:
        arcpy.Describe(fc)
        return True
    except Exception:
        return bool(arcpy.Exists(fc))


def _where_clause_anno(fc_path, anno=None):
    """Filtro SQL por md_anno (evita cargar 90k+ registros en San Martin)."""
    if not anno:
        anno = _detectar_anno_defecto(fc_path)
    try:
        anno_i = int(str(anno).strip())
        campos = {f.name.lower() for f in arcpy.ListFields(fc_path)}
        if "md_anno" in campos:
            return f"md_anno = {anno_i}"
    except Exception:
        pass
    return ""


def _where_clause_h2(fc_path, anno=None):
    """Vigente: sin filtro año. Acumulado: filtro md_anno."""
    if _fc_es_vigente(fc_path):
        return ""
    return _where_clause_anno(fc_path, anno)


def _where_clause_auto(fc_path):
    return _where_clause_anno(fc_path)


def _run_visor_satelital(
        fc,
        where_clause="",
        acr_filtro="",
        guardar_ids_tabla=True,
        exportar_h3=True,
        titulo="Visor Satelital — GFP Subnacional",
        prefijo_tmp="ATD_H2_",
):
    """Lanza VisorATD (visor satelital H2 GFP Subnacional)."""
    arcpy.AddMessage("=" * 65)
    arcpy.AddMessage(titulo)
    arcpy.AddMessage(
        f"Region: {REGION_NOMBRE} | Planet + S2 + Landsat | Export HD"
    )
    arcpy.AddMessage("=" * 65)
    if _planet_disponible():
        arcpy.AddMessage("  Planet API: PLANET_API_KEY detectada (recomendado).")
    else:
        arcpy.AddWarning(
            "  Planet API no detectada. Configure PLANET_API_KEY para usar Planet."
        )

    if where_clause:
        arcpy.AddMessage(f"   Filtro SQL   : {where_clause}")
        try:
            lyr_cnt = "__atd_h2_cnt__"
            if arcpy.Exists(lyr_cnt):
                arcpy.management.Delete(lyr_cnt)
            arcpy.management.MakeFeatureLayer(fc, lyr_cnt, where_clause)
            n_filt = int(arcpy.management.GetCount(lyr_cnt)[0])
            arcpy.management.Delete(lyr_cnt)
            arcpy.AddMessage(f"   Poligonos filtro: {n_filt:,}")
            if n_filt == 0:
                arcpy.AddWarning("Sin poligonos con el filtro indicado.")
                return
            if n_filt > 3000:
                arcpy.AddWarning(
                    f"{n_filt:,} poligonos — el visor puede tardar. "
                    "Use un filtro SQL mas restrictivo.")
        except Exception:
            pass
    if acr_filtro and acr_filtro not in ("(Todos)", ""):
        arcpy.AddMessage(f"   Filtro ACR   : {acr_filtro}")

    arcpy.AddMessage("Extrayendo poligonos de la capa...")
    try:
        vectores, sr_wkt = extraer_vectores_fc(
            fc, where_clause=where_clause,
            acr_filtro=acr_filtro if acr_filtro not in ("(Todos)", "") else "")
    except Exception as e:
        arcpy.AddError(f"Error extrayendo capa: {e}")
        arcpy.AddError(traceback.format_exc())
        return

    if not vectores:
        fc_nom = _fc_nombre_base(fc)
        try:
            n_capa = int(arcpy.management.GetCount(fc)[0])
        except Exception:
            n_capa = -1
        gdb_hint = ""
        try:
            cat = str(arcpy.Describe(fc).catalogPath or fc)
            if ".gdb" in cat.lower():
                gdb_hint = f"\nGDB en uso: {cat.split('.gdb')[0]}.gdb"
        except Exception:
            pass
        arcpy.AddError(
            f"No hay poligonos validos en '{fc_nom}'"
            f"{gdb_hint}\n\n"
            f"Registros en la capa: {n_capa if n_capa >= 0 else '?'}\n\n"
            "Revise:\n"
            "  1) H1 y H2 deben usar la MISMA geodatabase "
            "(ATD_Loreto/GDB/Linea_base_deforestacion_Loreto.gdb).\n"
            "  2) Ejecute H1 antes de H2 para cargar alertas 2026.\n"
            "  3) Si filtra por seleccion, elija un poligono con geometria "
            "(no solo fila en tabla).\n"
            "  4) Capa en WGS84 (EPSG:4326)."
        )
        return

    arcpy.AddMessage(f"OK — {len(vectores)} poligonos cargados")
    sin_wgs = sum(1 for v in vectores if not v["pts_wgs84"])
    if sin_wgs:
        arcpy.AddWarning(
            f"{sin_wgs}/{len(vectores)} sin WGS84.\n"
            "  Solucion: Define Projection (EPSG:32718/32719 o WGS84).")
    else:
        arcpy.AddMessage("Proyeccion WGS84 OK.")

    arcgis_mapa        = None
    arcgis_mapa_nombre = None
    tmp_dir            = tempfile.mkdtemp(prefix=prefijo_tmp)
    base_salida        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dir_img_h3         = os.path.join(base_salida, "imagenes_sentinel")
    os.makedirs(dir_img_h3, exist_ok=True)

    try:
        aprx = arcpy.mp.ArcGISProject("CURRENT")
        arcgis_mapa = aprx.activeMap
        if arcgis_mapa:
            arcgis_mapa_nombre = arcgis_mapa.name
            arcpy.AddMessage(f"Mapa activo: '{arcgis_mapa_nombre}'")
        else:
            arcpy.AddWarning("Sin mapa activo")
    except Exception as e:
        arcpy.AddWarning(f"No se pudo obtener mapa: {e}")

    _geotiff_queue = []

    def _callback_geotiff(esc_a, esc_d, vec_sel):
        _geotiff_queue.append((esc_a, esc_d, vec_sel))

    try:
        root = tk.Tk()
        sty  = ttk.Style(root)
        sty.theme_use("clam")
        sty.configure("Vertical.TScrollbar",
                       background=C["card"],
                       troughcolor=C["panel"],
                       arrowcolor=C["dim"])

        visor = VisorATD(
            root, vectores, sr_wkt,
            arcgis_mapa_nombre=arcgis_mapa_nombre,
            tmp_dir=tmp_dir,
            callback_geotiff=_callback_geotiff)

        def _poll_geotiff():
            while _geotiff_queue:
                esc_a, esc_d, vec_sel = _geotiff_queue.pop(0)
                try:
                    root.update_idletasks()
                    _hacer_geotiff(esc_a, esc_d, vec_sel)
                except Exception as ex:
                    messagebox.showerror("GeoTIFF", f"Error al exportar:\n{ex}")
            root.after(250, _poll_geotiff)

        def _hacer_geotiff(esc_a, esc_d, vec_sel):
            if not arcgis_mapa:
                root.after(0, lambda: messagebox.showerror(
                    "Sin mapa", "No hay mapa activo."))
                return
            pil_ok = visor.pil
            use_hd = bool(
                getattr(visor, "v_export_hd", None)
                and visor.v_export_hd.get()
            )
            export_px = RENDER_SIZE_EXPORT if use_hd else RENDER_SIZE
            capas  = []
            arcpy.AddMessage(
                f"Export GeoTIFF — {'HD' if use_hd else 'estandar'} "
                f"(desde imagen del visor, sin re-descarga STAC)"
            )
            for esc, etiq, pil_img in [
                (esc_a, "ANTES",   visor._pil_a),
                (esc_d, "DESPUES", visor._pil_d),
            ]:
                if not esc:
                    continue

                img_bytes = None
                bbox_img_wgs84 = esc.get("img_bbox_wgs84")

                if pil_ok:
                    try:
                        img_bytes = visor._bytes_imagen_export(
                            esc, pil_img, export_px)
                        if img_bytes:
                            arcpy.AddMessage(
                                f"  {etiq}: listo {export_px}px "
                                f"({len(img_bytes)//1024} KB)"
                            )
                    except Exception as ex:
                        arcpy.AddWarning(f"  {etiq}: export: {ex}")

                if not img_bytes and esc.get("prev"):
                    try:
                        prev_url = _sign_mpc_href(esc["prev"])
                        img_bytes = http_bytes(prev_url, max_mb=40)
                        arcpy.AddMessage(
                            f"  {etiq}: preview STAC {len(img_bytes)//1024} KB"
                        )
                    except Exception as e:
                        arcpy.AddWarning(f"  {etiq}: preview error: {e}")

                if not img_bytes:
                    img_bytes = _png_1px(14, 40, 70)

                if exportar_h3:
                    try:
                        suf = "A" if etiq == "ANTES" else "D"
                        oids_h3 = [
                            int(v.get("oid", 0) or 0)
                            for v in _alertas_activas_lista(visor.vectores)
                        ]
                        if not oids_h3 and vec_sel:
                            oids_h3 = [int(vec_sel.get("oid", 0) or 0)]
                        for i_oid, oid_local in enumerate(oids_h3):
                            if not oid_local:
                                continue
                            vec_h3 = next(
                                (v for v in visor.vectores
                                 if v.get("oid") == oid_local),
                                vec_sel,
                            )
                            bbox_h3 = (
                                bbox_img_wgs84
                                or (vec_h3 or {}).get("bbox_wgs84")
                                or esc.get("bbox_stac")
                            )
                            meta = {
                                "oid": oid_local,
                                "acr": str((vec_h3 or {}).get("cod", "") or ""),
                                "fecha": str(esc.get("fecha", "") or ""),
                                "id": str(esc.get("id", "") or ""),
                                "sat": str(esc.get("sat", "") or ""),
                                "fuente": str(esc.get("api", "") or "STAC"),
                                "item_type": str(
                                    esc.get("item_type", "")
                                    or esc.get("collection", "")
                                ),
                                "etiqueta": etiq,
                            }
                            if bbox_h3 and len(bbox_h3) == 4:
                                meta["bbox_wgs84"] = [
                                    float(x) for x in bbox_h3]
                            bytes_h3 = img_bytes
                            pts_wgs = (vec_h3 or {}).get("pts_wgs84") or []
                            if (pil_ok and bbox_h3 and len(pts_wgs) >= 3
                                    and len(bbox_h3) == 4):
                                try:
                                    from shapely.geometry import Polygon
                                    from atd_imagenes_h3 import (
                                        quemar_vector_alerta_en_imagen,
                                    )
                                    pil_h3 = visor.PIL.open(
                                        io.BytesIO(img_bytes)).convert("RGB")
                                    geom_h3 = Polygon(pts_wgs)
                                    pil_m = quemar_vector_alerta_en_imagen(
                                        pil_h3,
                                        tuple(float(x) for x in bbox_h3),
                                        geom_h3,
                                        epsg_bounds=4326,
                                        epsg_geom=4326,
                                    )
                                    buf_h3 = io.BytesIO()
                                    pil_m.save(buf_h3, format="PNG")
                                    bytes_h3 = buf_h3.getvalue()
                                except Exception:
                                    bytes_h3 = img_bytes
                            if i_oid == 0:
                                ok_h3 = guardar_imagen_h3(
                                    dir_img_h3, oid_local, suf,
                                    bytes_h3, meta)
                            else:
                                try:
                                    from atd_imagenes_h3 import ruta_png, ruta_meta
                                    import json as _json
                                    shutil.copy2(
                                        ruta_png(dir_img_h3, oids_h3[0], suf),
                                        ruta_png(dir_img_h3, oid_local, suf),
                                    )
                                    with open(
                                        ruta_meta(dir_img_h3, oid_local, suf),
                                        "w", encoding="utf-8",
                                    ) as fm:
                                        _json.dump(meta, fm, ensure_ascii=False, indent=2)
                                    ok_h3 = True
                                except Exception:
                                    ok_h3 = guardar_imagen_h3(
                                        dir_img_h3, oid_local, suf,
                                        bytes_h3, meta)
                            if ok_h3 and i_oid == len(oids_h3) - 1:
                                arcpy.AddMessage(
                                    f"  {etiq}: PNG H3 ({len(oids_h3)} alerta(s))"
                                )
                    except Exception as ex:
                        arcpy.AddWarning(f"  {etiq}: H3: {ex}")

                nb       = (f"ATD_{etiq}_{esc['fecha'].replace('-','')}"
                            f"_{esc['sat'].replace(' ','_').replace('-','')}")
                ruta_tif = os.path.join(tmp_dir, f"{nb}.tif")
                if bbox_img_wgs84:
                    bbox_export = _bbox_wgs84_a_sr(bbox_img_wgs84, sr_wkt)
                else:
                    bbox_export = None
                if not bbox_export:
                    bbox_export = vec_sel["bbox_fc_pad"]
                resultado = crear_geotiff(
                    img_bytes, bbox_export,
                    sr_wkt, ruta_tif, pil_ok, tmp_dir,
                    target_size=export_px)

                if resultado is False:
                    arcpy.AddWarning(f"  No se pudo crear GeoTIFF {etiq}")
                    continue
                ruta_final = resultado if isinstance(resultado, str) else ruta_tif
                try:
                    lyr = arcgis_mapa.addDataFromPath(ruta_final)
                    if lyr:
                        fecha_raw = esc.get("fecha", "")
                        try:
                            fecha_lyr = dt.strptime(
                                fecha_raw, "%Y-%m-%d").strftime("%d-%b-%Y")
                        except Exception:
                            fecha_lyr = fecha_raw
                        lyr.name = f"GFP_{etiq}_{fecha_lyr}"
                        if _configurar_stretch_custom_capa(lyr):
                            arcpy.AddMessage(
                                f"  OK capa '{lyr.name}' (stretch Custom)"
                            )
                        else:
                            arcpy.AddMessage(f"  OK capa '{lyr.name}'")
                        capas.append(lyr.name)
                except Exception as ex:
                    arcpy.AddWarning(f"  addDataFromPath: {ex}")

            try:
                sr  = arcpy.SpatialReference()
                if sr_wkt:
                    sr.loadFromString(sr_wkt)
                bfc = vec_sel["bbox_fc_pad"]
                ext = arcpy.Extent(bfc[0], bfc[1], bfc[2], bfc[3],
                                   spatial_reference=sr)
                if arcgis_mapa.defaultView:
                    arcgis_mapa.defaultView.camera.setExtent(ext)
            except Exception as ex:
                arcpy.AddWarning(f"  Zoom: {ex}")

            _refrescar_vista_arcgis()
            if capas:
                def _msg_ok():
                    messagebox.showinfo(
                        "GeoTIFF en HD",
                        "Capas cargadas en el mapa:\n"
                        + "\n".join(f"  · {n}" for n in capas),
                    )
                    visor._st(f"OK — {len(capas)} capas en mapa", C["verde"])
                root.after(0, _msg_ok)
            else:
                root.after(0, lambda: messagebox.showwarning(
                    "Sin capas", "No se pudieron agregar capas."))

        root.protocol("WM_DELETE_WINDOW", root.destroy)
        root.after(250, _poll_geotiff)
        root.mainloop()

        if guardar_ids_tabla and hasattr(visor, "_tabla_req") and visor._tabla_req:
            req = visor._tabla_req
            oids_req = req.get("oids") or []
            if not oids_req and req.get("oid") is not None:
                oids_req = [req["oid"]]
            for oid_t in oids_req:
                _aplicar_ids_tabla(fc, oid_t, req["esc_a"], req["esc_d"], sr_wkt)
            if len(oids_req) > 1:
                arcpy.AddMessage(
                    f"Tabla actualizada para {len(oids_req)} poligonos activos."
                )

        arcpy.AddMessage("Visor cerrado OK.")

    except Exception as e:
        arcpy.AddError(f"Error iniciando visor: {e}")
        arcpy.AddError(traceback.format_exc())


# ─── HERRAMIENTA ARCGIS PRO ───────────────────────────────────────────────────

class VisualizarSatelital(object):

    def __init__(self):
        self.label = (
            "Visor de imágenes satelitales para fotointerpretación "
            "de las causas de deforestación"
        )
        self.description = (
            "Visor profesional estilo USGS EarthExplorer.\n\n"
            "Paso 1: Datos del FC (alertas + checklist)\n"
            "Paso 2: Satélite Planet / STAC (S2 / Landsat 8-9)\n"
            "Paso 3: Resultados — marque ANTES y DESPUÉS (carga automática)\n"
            "Paso 4: Exportar GeoTIFF HD al mapa activo (TOC)\n\n"
            "MonitoreoDeforestacion = alertas vigentes (ano en curso, sin elegir año).\n"
            "MonitoreoDeforestacionAcumulado = historico (elija año md_anno).\n\n"
            "Alertas on/off | Export HD | Landsat MPC firmado"
        )
        self.canRunInBackground = False

    def getParameterInfo(self):
        p0 = arcpy.Parameter(
            displayName="* GDB Linea Base Deforestacion",
            name="gdb_trabajo",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Input",
        )
        p0.filter.list = ["Local Database"]

        p1 = arcpy.Parameter(
            displayName="* FC de alertas",
            name="fc_alertas",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input",
        )

        p2 = arcpy.Parameter(
            displayName="Año de monitoreo (solo MonitoreoDeforestacionAcumulado)",
            name="anno_alertas",
            datatype="GPString",
            parameterType="Optional",
            direction="Input",
        )
        p2.filter.type = "ValueList"
        p2.filter.list = [
            "2026", "2025", "2024", "2023", "2022", "2021", "2020",
        ]
        p2.value = str(dt.now().year)
        p2.enabled = False

        return [p0, p1, p2]

    def isLicensed(self): return True

    def updateParameters(self, p):
        gdb_abs = gdb_absoluta_si_existe(p[0].valueAsText)
        if not gdb_abs:
            return
        try:
            p[0].value = gdb_abs
            configurar_region(gdb_abs)
            arcpy.env.workspace = gdb_abs
            fcs = sorted(arcpy.ListFeatureClasses() or [])
            if fcs:
                vigente = "MonitoreoDeforestacion"
                fc_path = os.path.join(
                    gdb_abs,
                    vigente if vigente in fcs else resolver_fc_alertas(gdb_abs, fcs),
                )
                if arcpy.Exists(fc_path):
                    cur = p[1].valueAsText or ""
                    cur_base = _fc_nombre_base(cur) if cur else ""
                    if not cur or cur_base not in fcs:
                        p[1].value = fc_path

            fc_sel = p[1].valueAsText or ""
            if _fc_es_vigente(fc_sel):
                p[2].enabled = False
                p[2].parameterType = "Optional"
                p[2].value = str(dt.now().year)
            else:
                p[2].enabled = True
                p[2].parameterType = "Required"
                if not p[2].altered and fc_sel and arcpy.Exists(fc_sel):
                    p[2].value = _detectar_anno_defecto(fc_sel)
        except Exception:
            pass

    def updateMessages(self, p): return

    def execute(self, parameters, messages):
        gdb = parameters[0].valueAsText
        fc = parameters[1].value or parameters[1].valueAsText
        acr_filtro = ""
        vigente = _fc_es_vigente(fc)

        if vigente:
            anno_alertas = str(dt.now().year)
            where_clause = ""
        else:
            anno_alertas = parameters[2].valueAsText or _detectar_anno_defecto(fc)
            where_clause = _where_clause_h2(fc, anno_alertas)

        if not gdb or not arcpy.Exists(gdb):
            arcpy.AddError("GDB de trabajo no valida o no existe.")
            return
        configurar_region(gdb, force=True)
        sincronizar_imports_region(globals())
        _resolver_raiz_paquete(gdb)

        fc_nom = _fc_nombre_base(fc)
        if vigente:
            arcpy.AddMessage(
                f"   Capa vigente : {fc_nom} — año en curso {anno_alertas} "
                f"(todas las alertas de la capa, sin filtro md_anno)"
            )
        else:
            arcpy.AddMessage(f"   Capa historica: {fc_nom} | md_anno = {anno_alertas}")

        try:
            n_sel = int(arcpy.management.GetCount(fc)[0])
            if n_sel == 0:
                arcpy.AddError(
                    f"Sin poligonos en '{fc_nom}'.\n"
                    "Ejecute H1 (Descarga Geobosques) en la misma GDB del paquete ATD_Loreto, "
                    "o quite la seleccion / elija otra alerta en el mapa."
                )
                return
            arcpy.AddMessage(f"   Poligonos a cargar: {n_sel:,}")
        except Exception as ex:
            arcpy.AddError(f"No se pudo leer la capa de alertas: {ex}")
            return

        if where_clause:
            try:
                lyr_cnt = "__atd_h2_cnt_pre__"
                if arcpy.Exists(lyr_cnt):
                    arcpy.management.Delete(lyr_cnt)
                arcpy.management.MakeFeatureLayer(fc, lyr_cnt, where_clause)
                n_filt = int(arcpy.management.GetCount(lyr_cnt)[0])
                arcpy.management.Delete(lyr_cnt)
            except Exception:
                n_filt = int(arcpy.management.GetCount(fc)[0])
        else:
            n_filt = int(arcpy.management.GetCount(fc)[0])

        if n_filt == 0:
            fc_nom = _fc_nombre_base(fc)
            if vigente:
                arcpy.AddError(
                    f"Sin alertas en '{fc_nom}'.\n\n"
                    "Ejecute primero H1 (Descarga Geobosques) para cargar "
                    f"las alertas de {anno_alertas} en esta capa."
                )
            else:
                sug = _detectar_anno_defecto(fc)
                arcpy.AddError(
                    f"Sin alertas en '{fc_nom}' para md_anno={anno_alertas}.\n"
                    f"Pruebe otro año (ej. {sug}) o use MonitoreoDeforestacion "
                    "tras descargar con H1."
                )
            return

        _run_visor_satelital(
            fc,
            where_clause=where_clause,
            acr_filtro=acr_filtro,
            guardar_ids_tabla=True,
            exportar_h3=True,
            titulo="Visor Satelital — GFP Subnacional",
        )


def _aplicar_ids_tabla(fc_path, oid_target, esc_a, esc_d, sr_wkt):
    arcpy.AddMessage(f"Aplicando IDs a tabla — OID {oid_target}...")
    campos_fc  = {f.name.lower(): f.name for f in arcpy.ListFields(fc_path)}
    SAT_COD_MAP = {
        "Sentinel-2": 2, "Landsat 8": 1, "Landsat 9": 1,
        "PlanetScope": 3, "Planet SkySat": 3,
    }

    for nom, tip, lon, ali in [
        ("md_img_ant",    "TEXT", 500, "ID imagen ANTES"),
        ("md_img_dep",    "TEXT", 500, "ID imagen DESPUES"),
        ("md_sat_ant",    "TEXT",  50, "Satelite imagen ANTES"),
        ("md_sat_dep",    "TEXT",  50, "Satelite imagen DESPUES"),
        ("md_fecimg_ant", "DATE", None, "Fecha imagen ANTES"),
    ]:
        if nom not in campos_fc:
            try:
                kw = {"in_table": fc_path, "field_name": nom,
                      "field_type": tip, "field_alias": ali,
                      "field_is_nullable": "NULLABLE"}
                if lon: kw["field_length"] = lon
                arcpy.management.AddField(**kw)
                arcpy.AddMessage(f"  Campo '{nom}' creado")
                campos_fc[nom] = nom
            except Exception as e:
                arcpy.AddWarning(f"  Campo '{nom}': {e}")

    campos_fc = {f.name.lower(): f.name for f in arcpy.ListFields(fc_path)}

    def _fecha(s):
        if not s: return None
        for fmt in ["%Y-%m-%d", "%d/%m/%Y"]:
            try:
                from datetime import datetime as dtt
                return dtt.strptime(s, fmt)
            except Exception: pass
        return None

    oid_field = arcpy.Describe(fc_path).OIDFieldName
    campos_ed = [oid_field]
    idx_map   = {}
    for nom in ["md_img_ant","md_img_dep","md_img","md_fecimg_ant",
                "md_fecimg","md_sat_ant","md_sat_dep","md_fuente_sat"]:
        if nom in campos_fc:
            idx_map[nom] = len(campos_ed)
            campos_ed.append(campos_fc[nom])

    try:
        with arcpy.da.UpdateCursor(fc_path, campos_ed) as cur:
            for row in cur:
                if row[0] != oid_target:
                    continue
                row = list(row)
                if esc_a:
                    if "md_img_ant"    in idx_map: row[idx_map["md_img_ant"]]    = esc_a["id"][:500]
                    if "md_fecimg_ant" in idx_map: row[idx_map["md_fecimg_ant"]] = _fecha(esc_a["fecha"])
                    if "md_sat_ant"    in idx_map: row[idx_map["md_sat_ant"]]    = esc_a["sat"][:50]
                if esc_d:
                    if "md_img_dep"  in idx_map: row[idx_map["md_img_dep"]]  = esc_d["id"][:500]
                    if "md_img"      in idx_map: row[idx_map["md_img"]]      = esc_d["id"][:500]
                    if "md_fecimg"   in idx_map: row[idx_map["md_fecimg"]]   = _fecha(esc_d["fecha"])
                    if "md_sat_dep"  in idx_map: row[idx_map["md_sat_dep"]]  = esc_d["sat"][:50]
                if "md_fuente_sat" in idx_map:
                    sat_ref = esc_d or esc_a
                    row[idx_map["md_fuente_sat"]] = SAT_COD_MAP.get(sat_ref["sat"], 2)
                cur.updateRow(row)
                break
        _refrescar_vista_arcgis()
        arcpy.AddMessage(f"  OID {oid_target} actualizado OK")
    except Exception as e:
        arcpy.AddError(f"Error tabla: {e}")
        arcpy.AddError(traceback.format_exc())

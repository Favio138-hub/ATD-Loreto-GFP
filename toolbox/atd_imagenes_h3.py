# -*- coding: utf-8 -*-
"""
Rutas y resolucion de imagenes H2 -> H3 (imagenes_sentinel/).
"""
from __future__ import annotations

import glob
import json
import os
import re
import urllib.parse
import urllib.request

MIN_PNG_BYTES = 8000
UA = "ATD-Toolbox/GFP-Subnacional"
MPC_ITEM_S2 = (
    "https://planetarycomputer.microsoft.com/api/stac/v1/collections/"
    "sentinel-2-l2a/items/{item_id}"
)
E84_ITEM_S2 = (
    "https://earth-search.aws.element84.com/v1/collections/"
    "sentinel-2-l2a/items/{item_id}"
)
MPC_SIGN_API = "https://planetarycomputer.microsoft.com/api/sas/v1/sign"
MPC_TILER = "https://planetarycomputer.microsoft.com/api/data/v1/item"
TITILER_COG = "https://titiler.xyz/cog/bbox"


def resolver_oid_imagen(alerta_sel: str | None, alerta_row=None) -> int | None:
    """OID real para buscar ATD_OID{oid}_A/D.png (prioriza seleccion OID:NNN|)."""
    try:
        from atd_arcpy_io import parse_seleccion_alerta

        hint = parse_seleccion_alerta(alerta_sel or "")
        if isinstance(hint, int):
            return hint
    except Exception:
        pass
    if alerta_row is not None:
        for col in ("objectid", "OBJECTID", "oid", "OID"):
            try:
                if hasattr(alerta_row, "index") and col in alerta_row.index:
                    v = alerta_row[col]
                elif hasattr(alerta_row, "get"):
                    v = alerta_row.get(col)
                else:
                    continue
                if v is not None and str(v).strip() not in ("", "nan"):
                    return int(v)
            except Exception:
                continue
    return None


def ruta_png(dir_img: str, oid: int, sufijo: str) -> str:
    return os.path.join(dir_img, f"ATD_OID{int(oid)}_{sufijo}.png")


def ruta_meta(dir_img: str, oid: int, sufijo: str) -> str:
    return os.path.join(dir_img, f"ATD_OID{int(oid)}_{sufijo}.json")


def png_valido(ruta: str) -> bool:
    return bool(ruta and os.path.isfile(ruta) and os.path.getsize(ruta) >= MIN_PNG_BYTES)


def _sign_mpc_href(href: str) -> str:
    if not href:
        return href
    low = href.lower()
    if "sig=" in low or "se=" in low:
        return href
    if "blob.core.windows.net" not in low and "planetarycomputer.microsoft.com" not in low:
        return href
    try:
        q = urllib.parse.urlencode({"href": href})
        req = urllib.request.Request(
            f"{MPC_SIGN_API}?{q}", headers={"User-Agent": UA}
        )
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode())
        return data.get("href") or href
    except Exception:
        return href


def _http_bytes(url: str, max_mb: int = 25) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = b""
        lim = max_mb * 1024 * 1024
        while True:
            chunk = resp.read(262144)
            if not chunk:
                break
            data += chunk
            if len(data) > lim:
                break
    return data


def _bbox_gis_desde_meta(meta):
    """Bbox API [xmin, ymin, xmax, ymax] a partir del JSON H2."""
    if not meta:
        return None
    b = meta.get("bbox_wgs84") or meta.get("bbox")
    if not isinstance(b, (list, tuple)) or len(b) < 4:
        return None
    xmin, xmax, ymin, ymax = _normalizar_bounds(b)
    if xmax <= xmin or ymax <= ymin:
        return None
    return [xmin, ymin, xmax, ymax]


def _es_png(data: bytes) -> bool:
    return bool(data) and len(data) >= MIN_PNG_BYTES and data[:8] == b"\x89PNG\r\n\x1a\n"


def _descargar_png_bbox(item_id: str, bbox_gis, size: int = 800) -> bytes | None:
    """Recorte de la escena al bbox de la alerta (no thumbnail de toda la tile)."""
    if not item_id or not bbox_gis or len(bbox_gis) < 4:
        return None
    x0, y0, x1, y1 = [float(v) for v in bbox_gis[:4]]
    bbox_txt = f"{x0:.8f},{y0:.8f},{x1:.8f},{y1:.8f}"
    qid = urllib.parse.quote(item_id, safe="")
    urls = []
    q_mpc = urllib.parse.urlencode({
        "collection": "sentinel-2-l2a",
        "item": item_id,
        "assets": "visual",
        "format": "png",
        "resampling": "bilinear",
    })
    urls.append(f"{MPC_TILER}/bbox/{bbox_txt}/{int(size)}x{int(size)}.png?{q_mpc}")
    try:
        item_url = E84_ITEM_S2.format(item_id=qid)
        req = urllib.request.Request(item_url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as resp:
            item = json.loads(resp.read().decode())
        assets = item.get("assets") or {}
        href = None
        for key in ("visual", "visual_tci", "rendered_preview"):
            if key in assets and isinstance(assets[key], dict):
                href = assets[key].get("href")
                if href:
                    break
        if href:
            q_t = urllib.parse.urlencode({"url": href, "resampling": "lanczos"})
            urls.append(f"{TITILER_COG}/{bbox_txt}/{int(size)}x{int(size)}.png?{q_t}")
    except Exception:
        pass
    for url in urls:
        try:
            signed = _sign_mpc_href(url) if "planetarycomputer" in url else url
            data = _http_bytes(signed)
            if _es_png(data):
                return data
        except Exception:
            continue
    return None


def _recortar_preview_a_bbox(png_bytes: bytes, scene_bbox, alert_bbox, out_size=800):
    """Si el PNG es la tile completa, recorta al bbox de la alerta."""
    try:
        from PIL import Image
        import io
    except ImportError:
        return png_bytes
    if not scene_bbox or not alert_bbox or len(scene_bbox) < 4 or len(alert_bbox) < 4:
        return png_bytes
    ex0, ey0, ex1, ey1 = [float(v) for v in scene_bbox[:4]]
    ax0, ay0, ax1, ay1 = [float(v) for v in alert_bbox[:4]]
    if abs(ex1 - ex0) <= abs(ax1 - ax0) * 2:
        return png_bytes
    try:
        img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        w, h = img.size
        px0 = int((ax0 - ex0) / (ex1 - ex0) * w)
        px1 = int((ax1 - ex0) / (ex1 - ex0) * w)
        py0 = int((ey1 - ay1) / (ey1 - ey0) * h)
        py1 = int((ey1 - ay0) / (ey1 - ey0) * h)
        px0 = max(0, min(px0, w - 1))
        px1 = max(px0 + 2, min(px1, w))
        py0 = max(0, min(py0, h - 1))
        py1 = max(py0 + 2, min(py1, h))
        if (px1 - px0) < 8 or (py1 - py0) < 8:
            return png_bytes
        cropped = img.crop((px0, py0, px1, py1))
        rs = getattr(Image, "LANCZOS", getattr(Image, "BICUBIC", Image.BILINEAR))
        cropped = cropped.resize((int(out_size), int(out_size)), rs)
        buf = io.BytesIO()
        cropped.save(buf, format="PNG", optimize=True)
        return buf.getvalue()
    except Exception:
        return png_bytes


def regenerar_png_desde_json(json_path: str, dir_img: str | None = None) -> str | None:
    """Si hay .json pero falta .png, baja el recorte del bbox de la alerta."""
    if not os.path.isfile(json_path):
        return None
    dir_img = dir_img or os.path.dirname(json_path)
    try:
        with open(json_path, encoding="utf-8") as f:
            meta = json.load(f)
    except Exception:
        return None
    oid = meta.get("oid")
    suf = "A" if str(meta.get("etiqueta", "")).upper().startswith("ANT") else "D"
    if oid is None:
        m = re.search(r"ATD_OID(\d+)_([AD])\.json$", os.path.basename(json_path), re.I)
        if m:
            oid, suf = int(m.group(1)), m.group(2).upper()
    if oid is None:
        return None
    out_png = ruta_png(dir_img, int(oid), suf)
    if png_valido(out_png):
        return out_png

    item_id = str(meta.get("id") or "").strip()
    if not item_id or item_id == "-":
        return None
    bbox_gis = _bbox_gis_desde_meta(meta)
    data = _descargar_png_bbox(item_id, bbox_gis, size=800) if bbox_gis else None
    if not _es_png(data or b""):
        data = None
        for item_url in (
            E84_ITEM_S2.format(item_id=urllib.parse.quote(item_id, safe="")),
            MPC_ITEM_S2.format(item_id=urllib.parse.quote(item_id, safe="")),
        ):
            try:
                req = urllib.request.Request(item_url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    item = json.loads(resp.read().decode())
                assets = item.get("assets") or {}
                href = None
                for key in ("rendered_preview", "visual", "visual_tci", "thumbnail"):
                    if key in assets and isinstance(assets[key], dict):
                        href = assets[key].get("href")
                        if href:
                            break
                if not href:
                    continue
                preview = _http_bytes(_sign_mpc_href(href))
                if not _es_png(preview):
                    continue
                scene_bb = item.get("bbox")
                if bbox_gis and scene_bb:
                    preview = _recortar_preview_a_bbox(preview, scene_bb, bbox_gis)
                data = preview
                break
            except Exception:
                continue
    if not _es_png(data or b""):
        return None
    with open(out_png, "wb") as fp:
        fp.write(data)
    return out_png


def buscar_imagen_local(
    dir_img: str,
    sufijo: str,
    oid_principal: int | None = None,
    alerta_sel: str | None = None,
    regenerar_si_falta: bool = True,
) -> tuple[str | None, dict | None]:
    """
    Busca ATD_OID{oid}_{A|D}.png. Prueba OID de seleccion y del registro.
    Si solo existe .json, intenta regenerar el .png.
    """
    oids: list[int] = []
    for o in (oid_principal, resolver_oid_imagen(alerta_sel)):
        if o is not None and int(o) not in oids:
            oids.append(int(o))

    for oid in oids:
        p = ruta_png(dir_img, oid, sufijo)
        if png_valido(p):
            meta = _leer_meta(dir_img, oid, sufijo)
            return p, meta

    if regenerar_si_falta:
        for oid in oids:
            jp = ruta_meta(dir_img, oid, sufijo)
            if os.path.isfile(jp):
                regen = regenerar_png_desde_json(jp, dir_img)
                if png_valido(regen):
                    return regen, _leer_meta(dir_img, oid, sufijo)

    pat = os.path.join(dir_img, f"ATD_OID*_{sufijo}.png")
    for p in sorted(glob.glob(pat), key=os.path.getmtime, reverse=True):
        if png_valido(p):
            m = re.search(r"ATD_OID(\d+)_", os.path.basename(p), re.I)
            oid_g = int(m.group(1)) if m else None
            return p, _leer_meta(dir_img, oid_g, sufijo) if oid_g else None

    if regenerar_si_falta:
        for jp in sorted(glob.glob(os.path.join(dir_img, f"ATD_OID*_{sufijo}.json"))):
            regen = regenerar_png_desde_json(jp, dir_img)
            if png_valido(regen):
                m = re.search(r"ATD_OID(\d+)_", os.path.basename(regen), re.I)
                oid_g = int(m.group(1)) if m else None
                return regen, _leer_meta(dir_img, oid_g, sufijo) if oid_g else None

    return None, None


def _leer_meta(dir_img: str, oid: int | None, sufijo: str) -> dict | None:
    if oid is None:
        return None
    jp = ruta_meta(dir_img, oid, sufijo)
    if not os.path.isfile(jp):
        return None
    try:
        with open(jp, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def guardar_imagen_h3(dir_img: str, oid: int, sufijo: str, img_bytes: bytes, meta: dict) -> bool:
    """Guarda PNG+JSON solo si los bytes parecen imagen real."""
    os.makedirs(dir_img, exist_ok=True)
    if not img_bytes or len(img_bytes) < MIN_PNG_BYTES:
        return False
    if img_bytes[:8] != b"\x89PNG\r\n\x1a\n":
        return False
    p = ruta_png(dir_img, oid, sufijo)
    m = ruta_meta(dir_img, oid, sufijo)
    with open(p, "wb") as fp:
        fp.write(img_bytes)
    meta = dict(meta)
    meta["oid"] = int(oid)
    with open(m, "w", encoding="utf-8") as fm:
        json.dump(meta, fm, ensure_ascii=False, indent=2)
    return True


def _normalizar_bounds(bounds):
    """
    Devuelve (xmin, xmax, ymin, ymax).
    Acepta bbox GIS (xmin, ymin, xmax, ymax) — el de H2/STAC —
    o el formato interno (xmin, xmax, ymin, ymax).
    """
    if bounds is None or len(bounds) < 4:
        return bounds
    v = [float(x) for x in bounds[:4]]
    d02 = abs(v[0] - v[2])
    d01 = abs(v[0] - v[1])
    d13 = abs(v[1] - v[3])
    d12 = abs(v[1] - v[2])
    if d02 < d01 and d13 < d12:
        return (v[0], v[2], v[1], v[3])
    return (v[0], v[1], v[2], v[3])


def _epsg_geom_auto(geom, epsg_hint=4326):
    """Si las coordenadas no son lon/lat, asume UTM (hint o 32718)."""
    try:
        crs = getattr(geom, "crs", None)
        if crs is not None:
            code = crs.to_epsg() if hasattr(crs, "to_epsg") else None
            if code:
                return int(code)
    except Exception:
        pass
    try:
        c = geom.centroid
        if abs(float(c.x)) > 180.0 or abs(float(c.y)) > 90.0:
            return int(epsg_hint) if int(epsg_hint) not in (4326, 0) else 32718
    except Exception:
        pass
    return 4326


def _ring_a_pixeles(coords, bounds, w, h):
    """Convierte anillo (x,y) en CRS de bounds a pixeles de imagen."""
    bounds = _normalizar_bounds(bounds)
    xmin, xmax, ymin, ymax = bounds
    if xmax <= xmin or ymax <= ymin:
        return []
    out = []
    for x, y in coords:
        px = (x - xmin) / (xmax - xmin) * w
        py = (ymax - y) / (ymax - ymin) * h
        out.append((px, py))
    return out


def _poligonos_shapely(geom):
    if geom is None or getattr(geom, "is_empty", True):
        return []
    gt = getattr(geom, "geom_type", "")
    if gt == "Polygon":
        return [geom]
    if gt == "MultiPolygon":
        return list(geom.geoms)
    if gt == "GeometryCollection":
        out = []
        for g in geom.geoms:
            out.extend(_poligonos_shapely(g))
        return out
    return []


def _centro_radio_circulo_pixeles(geom, bounds, w, h, factor=1.12, min_r=12):
    """Centro y radio en pixeles para contorno circular de la alerta."""
    import math

    polys = _poligonos_shapely(geom)
    pts = []
    for poly in polys:
        pts.extend(_ring_a_pixeles(poly.exterior.coords, bounds, w, h))
    if not pts:
        return None
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    r = max(math.hypot(px - cx, py - cy) for px, py in pts) * factor
    return cx, cy, max(r, min_r)


def _dibujar_vector_en_draw(draw, geom, bounds, w, h, estilo="circulo_limpio"):
    """Dibuja alerta sobre ImageDraw: circulo limpio (informe) o poligono."""
    if estilo in ("circulo", "circulo_limpio", None, ""):
        cr = _centro_radio_circulo_pixeles(geom, bounds, w, h)
        if not cr:
            return
        cx, cy, r = cr
        box = [cx - r, cy - r, cx + r, cy + r]
        draw.ellipse(box, outline=(255, 255, 255, 255), width=5)
        draw.ellipse(box, outline=(196, 30, 58, 255), width=3)
        return

    polys = _poligonos_shapely(geom)
    # En el PDF la imagen se achica: 4 px se ve como 1. Grosor ~1% del lado.
    grosor = max(12, min(28, int(round(min(w, h) * 0.010))))
    for poly in polys:
        ext = _ring_a_pixeles(poly.exterior.coords, bounds, w, h)
        if len(ext) < 3:
            continue
        closed = ext + [ext[0]]
        draw.line(closed, fill=(196, 30, 58, 255), width=grosor)


def quemar_vector_alerta_en_imagen(
    img_rgb,
    bounds,
    geom,
    epsg_bounds=4326,
    epsg_geom=4326,
    estilo="circulo_limpio",
):
    """
    Dibuja la alerta en rojo sobre imagen RGB (numpy o PIL).
    estilo: 'circulo_limpio' (informe PDF), 'circulo' o 'poligono'.
    bounds: GIS o interno; se normaliza a (xmin, xmax, ymin, ymax).
    """
    try:
        from PIL import Image, ImageDraw
        import numpy as np
    except ImportError:
        return img_rgb

    if img_rgb is None or geom is None or bounds is None:
        return img_rgb

    as_pil = hasattr(img_rgb, "convert")
    pil = img_rgb.convert("RGBA") if as_pil else Image.fromarray(img_rgb).convert("RGBA")
    epsg_g = _epsg_geom_auto(geom, epsg_geom)
    g = _transformar_geom(geom, epsg_g, epsg_bounds)
    bnds = _normalizar_bounds(bounds)

    draw = ImageDraw.Draw(pil, "RGBA")
    w, h = pil.size
    _dibujar_vector_en_draw(draw, g, bnds, w, h, estilo=estilo or "poligono")

    out = pil.convert("RGB")
    return out if as_pil else np.array(out)


def geom_a_wgs84(geom, epsg_hint=32718):
    """Pasa la geometria de la alerta a EPSG:4326 (detecta UTM si |x|>180)."""
    if geom is None:
        return None
    return _transformar_geom(geom, _epsg_geom_auto(geom, epsg_hint), 4326)


def bounds_imagen_desde_meta(meta, geom_wgs, epsg_utm=32718, buffer_m=500):
    """Extent de imagen: meta.bbox_wgs84 o buffer alrededor de la alerta."""
    if meta:
        b = meta.get("bbox_wgs84") or meta.get("bbox")
        if isinstance(b, (list, tuple)) and len(b) == 4:
            return _normalizar_bounds(b), 4326
    geom4326 = geom_a_wgs84(geom_wgs, epsg_utm)
    try:
        import geopandas as gpd

        gdf = gpd.GeoDataFrame(geometry=[geom4326], crs="EPSG:4326").to_crs(
            f"EPSG:{epsg_utm}")
        gdf["geometry"] = gdf.geometry.buffer(buffer_m)
        xmin, ymin, xmax, ymax = gdf.total_bounds
        return (xmin, xmax, ymin, ymax), epsg_utm
    except Exception:
        pass
    try:
        xmin, ymin, xmax, ymax = geom4326.bounds
        pad = 0.0012
        return (xmin - pad, xmax + pad, ymin - pad, ymax + pad), 4326
    except Exception:
        return None, 4326


def _transformar_geom(geom, epsg_geom, epsg_bounds):
    if geom is None or epsg_geom == epsg_bounds:
        return geom
    try:
        import pyproj
        from shapely.ops import transform as shp_transform

        tr = pyproj.Transformer.from_crs(
            epsg_geom, epsg_bounds, always_xy=True)
        return shp_transform(tr.transform, geom)
    except Exception:
        return geom


def _bbox_pixeles_geom(geom, bounds, w, h):
    pts = []
    for poly in _poligonos_shapely(geom):
        pts.extend(_ring_a_pixeles(poly.exterior.coords, bounds, w, h))
    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def recortar_zoom_alerta(pil, bounds, geom, margen_factor=8.0, min_lado_px=160):
    """
    Zoom suave centrado en el centroide del poligono, con contexto alrededor.
    """
    if pil is None or bounds is None or geom is None:
        return pil, bounds
    bounds = _normalizar_bounds(bounds)
    w, h = pil.size
    if w < 40 or h < 40:
        return pil, bounds
    box = _bbox_pixeles_geom(geom, bounds, w, h)
    if not box:
        return pil, bounds
    x0, y0, x1, y1 = box
    if x1 < 0 or y1 < 0 or x0 > w or y0 > h:
        return pil, bounds
    bw = max(x1 - x0, 6)
    bh = max(y1 - y0, 6)
    try:
        c = geom.centroid
        xmin, xmax, ymin, ymax = bounds
        cx = (float(c.x) - xmin) / (xmax - xmin) * w
        cy = (ymax - float(c.y)) / (ymax - ymin) * h
    except Exception:
        cx = (x0 + x1) / 2.0
        cy = (y0 + y1) / 2.0
    if cx < -8 or cy < -8 or cx > w + 8 or cy > h + 8:
        cx = min(max((x0 + x1) / 2.0, 0.0), float(w))
        cy = min(max((y0 + y1) / 2.0, 0.0), float(h))
    lado = max(max(bw, bh) * margen_factor, 0.62 * min(w, h), float(min_lado_px))
    need = max(abs(x0 - cx), abs(x1 - cx), abs(y0 - cy), abs(y1 - cy)) + 12
    lado = max(lado, need * 2.0)
    lado = min(lado, 0.92 * min(w, h))
    half = lado / 2.0
    cx0 = int(round(cx - half))
    cy0 = int(round(cy - half))
    cx1 = int(round(cx + half))
    cy1 = int(round(cy + half))
    if cx0 < 0:
        cx1 = min(w, cx1 - cx0)
        cx0 = 0
    if cy0 < 0:
        cy1 = min(h, cy1 - cy0)
        cy0 = 0
    if cx1 > w:
        cx0 = max(0, cx0 - (cx1 - w))
        cx1 = w
    if cy1 > h:
        cy0 = max(0, cy0 - (cy1 - h))
        cy1 = h
    if cx1 - cx0 < 40 or cy1 - cy0 < 40:
        return pil, bounds
    cropped = pil.crop((cx0, cy0, cx1, cy1))
    xmin, xmax, ymin, ymax = bounds
    new_xmin = xmin + (cx0 / float(w)) * (xmax - xmin)
    new_xmax = xmin + (cx1 / float(w)) * (xmax - xmin)
    new_ymax = ymax - (cy0 / float(h)) * (ymax - ymin)
    new_ymin = ymax - (cy1 / float(h)) * (ymax - ymin)
    return cropped, (new_xmin, new_xmax, new_ymin, new_ymax)


def aplicar_vector_y_zoom(
    img_rgb,
    bounds,
    geom,
    epsg_bounds=4326,
    epsg_geom=4326,
    estilo="poligono",
    zoom=True,
):
    """Recorta (zoom) y dibuja el poligono de la alerta sobre la imagen."""
    try:
        from PIL import Image, ImageDraw
        import numpy as np
    except ImportError:
        return img_rgb

    if img_rgb is None or geom is None or bounds is None:
        return img_rgb

    as_pil = hasattr(img_rgb, "convert")
    pil = img_rgb.convert("RGBA") if as_pil else Image.fromarray(img_rgb).convert("RGBA")
    epsg_g = _epsg_geom_auto(geom, epsg_geom)
    bnds = _normalizar_bounds(bounds)
    g = _transformar_geom(geom, epsg_g, epsg_bounds)
    if zoom:
        pil_rgb = pil.convert("RGB")
        pil_rgb, bnds = recortar_zoom_alerta(pil_rgb, bnds, g)
        pil = pil_rgb.convert("RGBA")

    draw = ImageDraw.Draw(pil, "RGBA")
    w, h = pil.size
    _dibujar_vector_en_draw(draw, g, bnds, w, h, estilo=estilo or "poligono")
    out = pil.convert("RGB")
    return out if as_pil else np.array(out)


def marcar_png_con_alerta(
    ruta_png, geom_wgs, meta=None, epsg_utm=32718, estilo="poligono",
):
    """Aplica zoom + vector rojo a PNG existente (H2 -> H3). Devuelve ruta marcada."""
    if not ruta_png or not os.path.isfile(ruta_png) or geom_wgs is None:
        return ruta_png
    try:
        from PIL import Image
        import numpy as np
    except ImportError:
        return ruta_png
    bounds, epsg_b = bounds_imagen_desde_meta(meta, geom_wgs, epsg_utm)
    if not bounds:
        return ruta_png
    try:
        arr = np.array(Image.open(ruta_png).convert("RGB"))
        arr_m = aplicar_vector_y_zoom(
            arr, bounds, geom_wgs,
            epsg_bounds=epsg_b,
            epsg_geom=_epsg_geom_auto(geom_wgs, epsg_utm),
            estilo=estilo or "poligono", zoom=True)
        base, ext = os.path.splitext(ruta_png)
        ruta_out = f"{base}_vec{ext}"
        Image.fromarray(arr_m).save(ruta_out, format="PNG", optimize=True)
        return ruta_out
    except Exception:
        return ruta_png

# -*- coding: utf-8 -*-
"""
Cliente Planet Data API para H2 Visor Satelital.
Lee la API key desde la variable de entorno PLANET_API_KEY.
"""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

PLANET_QUICK_SEARCH = "https://api.planet.com/data/v1/quick-search"
PLANET_THUMB_BASE = "https://tiles.planet.com/data/v1/item-types/{item_type}/items/{item_id}/thumb"
UA = "ATD-Toolbox/GFP-Subnacional"
TIMEOUT = 45
DEFAULT_ITEM_TYPES = ("PSScene",)
_OBSOLETE_PLANET_TYPES = frozenset({"PSScene3Band", "PSScene4Band"})


def get_api_key() -> str | None:
    key = (os.environ.get("PLANET_API_KEY") or "").strip()
    return key or None


def is_available() -> bool:
    return bool(get_api_key())


def _auth_header(api_key: str | None = None) -> dict:
    key = api_key or get_api_key()
    if not key:
        raise RuntimeError("PLANET_API_KEY no configurada")
    token = base64.b64encode(f"{key}:".encode("utf-8")).decode("ascii")
    return {
        "Authorization": f"Basic {token}",
        "User-Agent": UA,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _bbox_polygon(bbox_wgs84: list[float]) -> dict:
    x0, y0, x1, y1 = bbox_wgs84
    pad = 0.02
    x0 -= pad
    y0 -= pad
    x1 += pad
    y1 += pad
    return {
        "type": "Polygon",
        "coordinates": [[
            [x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0],
        ]],
    }


def _build_filter(bbox_wgs84, fecha_ini: datetime, fecha_fin: datetime, max_cloud_pct: float):
    cloud_lte = max(0.0, min(1.0, float(max_cloud_pct) / 100.0))
    return {
        "type": "AndFilter",
        "config": [
            {
                "type": "GeometryFilter",
                "field_name": "geometry",
                "config": _bbox_polygon(bbox_wgs84),
            },
            {
                "type": "DateRangeFilter",
                "field_name": "acquired",
                "config": {
                    "gte": fecha_ini.strftime("%Y-%m-%dT00:00:00.000Z"),
                    "lte": fecha_fin.strftime("%Y-%m-%dT23:59:59.999Z"),
                },
            },
            {
                "type": "RangeFilter",
                "field_name": "cloud_cover",
                "config": {"lte": cloud_lte},
            },
        ],
    }


def _http_post_json(url: str, body: dict, api_key: str | None = None) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=_auth_header(api_key), method="POST")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_bytes(url: str, api_key: str | None = None, max_mb: int = 80) -> bytes:
    """Descarga bytes (thumbnail Planet) con autenticacion."""
    key = api_key or get_api_key()
    if not key:
        raise RuntimeError("PLANET_API_KEY no configurada")
    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query)
    if "api_key" not in qs:
        sep = "&" if parsed.query else "?"
        url = f"{url}{sep}api_key={urllib.parse.quote(key)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
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


def thumbnail_url(item_type: str, item_id: str, width: int = 2048, api_key: str | None = None) -> str:
    key = api_key or get_api_key()
    if not key:
        raise RuntimeError("PLANET_API_KEY no configurada")
    base = PLANET_THUMB_BASE.format(item_type=item_type, item_id=item_id)
    w = max(256, min(int(width), 2048))
    return f"{base}?api_key={urllib.parse.quote(key)}&width={w}"


def _parse_feature(feat: dict) -> dict | None:
    props = feat.get("properties") or {}
    item_type = props.get("item_type") or feat.get("collection") or "PSScene"
    item_id = feat.get("id") or props.get("id")
    if not item_id:
        return None
    acquired = str(props.get("acquired") or "")[:10]
    try:
        cloud = float(props.get("cloud_cover", 0) or 0) * 100.0
    except Exception:
        cloud = 0.0
    links = feat.get("_links") or {}
    thumb = links.get("thumbnail")
    if isinstance(thumb, dict):
        thumb = thumb.get("href")
    sat_label = "Planet SkySat" if "SkySat" in str(item_type) else "PlanetScope"
    geom = feat.get("geometry") or {}
    bbox = []
    if geom.get("type") == "Polygon":
        try:
            coords = geom["coordinates"][0]
            xs = [c[0] for c in coords]
            ys = [c[1] for c in coords]
            bbox = [min(xs), min(ys), max(xs), max(ys)]
        except Exception:
            bbox = []
    prev = thumb or thumbnail_url(item_type, item_id, width=1024)
    return {
        "id": item_id,
        "fecha": acquired or "—",
        "nubes": round(cloud, 1),
        "sat": sat_label,
        "res": "3-5m",
        "prev": prev,
        "prev_tipo": "planet_thumb",
        "bbox": bbox,
        "api": "Planet",
        "tipo": "planet",
        "item_type": item_type,
        "collection": item_type,
        "asset_keys": ["visual"],
    }


def search_scenes(
    bbox_wgs84,
    fecha_ini: datetime,
    fecha_fin: datetime,
    max_cloud_pct: float = 40.0,
    item_types=None,
    limit: int = 40,
    api_key: str | None = None,
) -> list[dict]:
    """
    Busca escenas Planet en el bbox/fechas.
    Retorna lista de dicts compatibles con el visor H2.
    """
    key = api_key or get_api_key()
    if not key:
        raise RuntimeError("PLANET_API_KEY no configurada")
    if not bbox_wgs84 or bbox_wgs84 == [0, 0, 0, 0]:
        raise RuntimeError("BBox invalido para busqueda Planet")

    raw_types = list(item_types or DEFAULT_ITEM_TYPES)
    types = [t for t in raw_types if t not in _OBSOLETE_PLANET_TYPES]
    if not types:
        types = ["PSScene"]
    url = (
        f"{PLANET_QUICK_SEARCH}?_sort=acquired%20asc&_page_size={int(limit)}"
    )
    body = {
        "item_types": types,
        "filter": _build_filter(bbox_wgs84, fecha_ini, fecha_fin, max_cloud_pct),
    }
    try:
        data = _http_post_json(url, body, api_key=key)
    except urllib.error.HTTPError as ex:
        detail = ex.read().decode("utf-8", errors="replace")[:300]
        if ex.code == 400 and "end of lifed" in detail.lower():
            body["item_types"] = ["PSScene"]
            data = _http_post_json(url, body, api_key=key)
        else:
            raise RuntimeError(f"Planet HTTP {ex.code}: {detail}") from ex

    features = data.get("features") or []
    if not features and types != ["SkySatScene"]:
        body["item_types"] = ["SkySatScene"]
        try:
            data = _http_post_json(url, body, api_key=key)
            features = data.get("features") or []
        except urllib.error.HTTPError:
            pass
    out = []
    for feat in features:
        parsed = _parse_feature(feat)
        if parsed:
            out.append(parsed)
    return out

# -*- coding: utf-8 -*-
"""Basemap ESRI World Imagery para mapas matplotlib (urllib + PIL, sin contextily)."""
from __future__ import annotations

import io
import ssl
import urllib.request

ORIGIN_SHIFT = 20037508.342789244
INITIAL_RES = 156543.03392804097
ESRI_TILE_URL = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/"
    "World_Imagery/MapServer/tile/{z}/{y}/{x}"
)
UA = "ATD-Toolbox/GFP-Subnacional"
MAX_TILES = 40
TIMEOUT = 15


def _mercator_tile_xy(mx, my, zoom):
    res = INITIAL_RES / (2 ** zoom)
    px = (mx + ORIGIN_SHIFT) / res
    py = (ORIGIN_SHIFT - my) / res
    return int(px // 256), int(py // 256)


def _tile_bounds_mercator(tx, ty, zoom):
    res = INITIAL_RES / (2 ** zoom)
    xmin = tx * 256 * res - ORIGIN_SHIFT
    ymax = ORIGIN_SHIFT - ty * 256 * res
    xmax = (tx + 1) * 256 * res - ORIGIN_SHIFT
    ymin = ORIGIN_SHIFT - (ty + 1) * 256 * res
    return xmin, ymin, xmax, ymax


def _fetch_tile(z, y, x):
    url = ESRI_TILE_URL.format(z=z, y=y, x=x)
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
        data = resp.read()
    from PIL import Image
    return Image.open(io.BytesIO(data)).convert("RGB")


def add_esri_world_imagery(ax, xmin, xmax, ymin, ymax, epsg, log_fn=None):
    """
    Dibuja ESRI World Imagery en el eje matplotlib (coordenadas EPSG:epsg).
    Retorna True si se cargó al menos un tile.
    """
    try:
        import numpy as np
        from PIL import Image
        from pyproj import Transformer
    except ImportError:
        return False

    try:
        tr_m = Transformer.from_crs(f"EPSG:{int(epsg)}", "EPSG:3857", always_xy=True)
        tr_d = Transformer.from_crs("EPSG:3857", f"EPSG:{int(epsg)}", always_xy=True)

        mx0, my0 = tr_m.transform(xmin, ymin)
        mx1, my1 = tr_m.transform(xmax, ymax)
        mx_lo, mx_hi = min(mx0, mx1), max(mx0, mx1)
        my_lo, my_hi = min(my0, my1), max(my0, my1)

        corners_m = [
            (mx_lo, my_lo), (mx_lo, my_hi),
            (mx_hi, my_lo), (mx_hi, my_hi),
        ]

        chosen_z = None
        tx0 = tx1 = ty0 = ty1 = None
        for z in range(19, 9, -1):
            tiles = [_mercator_tile_xy(mx, my, z) for mx, my in corners_m]
            tx0 = min(t[0] for t in tiles)
            tx1 = max(t[0] for t in tiles)
            ty0 = min(t[1] for t in tiles)
            ty1 = max(t[1] for t in tiles)
            nx = tx1 - tx0 + 1
            ny = ty1 - ty0 + 1
            if 1 <= nx * ny <= MAX_TILES:
                chosen_z = z
                break

        if chosen_z is None:
            chosen_z = 11
            tiles = [_mercator_tile_xy(mx, my, chosen_z) for mx, my in corners_m]
            tx0 = min(t[0] for t in tiles)
            tx1 = max(t[0] for t in tiles)
            ty0 = min(t[1] for t in tiles)
            ty1 = max(t[1] for t in tiles)

        nw = (tx1 - tx0 + 1) * 256
        nh = (ty1 - ty0 + 1) * 256
        mosaic = Image.new("RGB", (nw, nh), (40, 44, 36))
        ok_tiles = 0
        for ty in range(ty0, ty1 + 1):
            for tx in range(tx0, tx1 + 1):
                try:
                    tile = _fetch_tile(chosen_z, ty, tx)
                    mosaic.paste(tile, ((tx - tx0) * 256, (ty - ty0) * 256))
                    ok_tiles += 1
                except Exception:
                    continue

        if ok_tiles == 0:
            return False

        bx0, _, _, ymax_m = _tile_bounds_mercator(tx0, ty0, chosen_z)
        _, ymin_m, bx1, _ = _tile_bounds_mercator(tx1, ty1, chosen_z)

        ex_x0, ex_y0 = tr_d.transform(bx0, ymin_m)
        ex_x1, ex_y1 = tr_d.transform(bx1, ymax_m)
        left = min(ex_x0, ex_x1)
        right = max(ex_x0, ex_x1)
        bottom = min(ex_y0, ex_y1)
        top = max(ex_y0, ex_y1)

        ax.imshow(
            np.asarray(mosaic),
            extent=[left, right, bottom, top],
            origin="upper",
            zorder=0,
            interpolation="bilinear",
        )
        if log_fn:
            log_fn(
                f"  Fondo satelital: ESRI World Imagery "
                f"(zoom {chosen_z}, {ok_tiles} tiles)"
            )
        return True
    except Exception:
        return False

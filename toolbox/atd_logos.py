# -*- coding: utf-8 -*-
"""
Resolucion de logos para PDF ATD — nombres por region y alias de carpeta logos/.
"""
from __future__ import annotations

import os
import re

_LOGO_EXT = (".png", ".jpeg", ".jpg", ".jpg.jpeg")

# GORE por region (nombres reales en logos/)
_REGION_GORE = {
    "loreto": [
        "logo_gore.png",
        "logo_gore",
    ],
    "cuzco": [
        "Logo_GORE_Cuzco.png",
        "logo_gore_cuzco.png",
        "logo_gore_cuzco",
    ],
    "san_martin": [
        "Logo_GORE_SAN_Martin_grande.png",
        "Logo_GORE_san_Martin.png",
        "logo_gore_san_martin.png",
        "logo_gore_san_martin",
    ],
}

# Gerencia / GRRNGA (columna izquierda inferior del encabezado)
_REGION_GRRNGA = {
    "loreto": [
        "logo_grrnga.png",
        "logo_grrnga",
    ],
    "cuzco": [
        "Logo_Gerencia_CUzco_Color.png",
        "logo gerencia color.png",
        "logo_gerencia_cuzco_color.png",
    ],
    "san_martin": [
        "logo_grrnga_san_martin.png",
        "Logo_Gerencia_San_Martin.png",
        "logo_gerencia_san_martin.png",
    ],
}

# logo_anp por codigo ACR (alias si no existe logo_anp_ACRxx.*)
_ACR_LOGO_ALIASES = {
    "ACR04": ["logo_anp_ACR04"],
    "ACR09": ["logo_anp_ACR09"],
    "ACR10": ["logo_anp_ACR10"],
    "ACR17": ["logo_anp_ACR17"],
    "ACR07": ["ACR_Choquequirao.png", "ACR_Choquequirao"],
    "ACR26": [
        "Logo Chuyapi Urusayhua_Mesa de trabajo 1.png",
        "Logo Chuyapi Urusayhua_Mesa de trabajo 1",
    ],
    "ACR30": ["QEROS - LOGO POSITIVO.png", "QEROS - LOGO POSITIVO"],
    "ACR01": ["ACR - CE.jpg.jpeg", "ACR - CE.jpg", "ACR - CE"],
    "ACR21": ["ACR - BOSHUMI.png", "ACR - BOSHUMI"],
}

_GENERIC_BASE = {
    "logo_gfp": ["logo_gfp.png", "logo_gfp"],
    "logo_seco": ["logo_SECO.jpg", "logo_seco.jpg", "logo_seco.png", "logo_SECO", "logo_seco"],
    "logo_basel": ["logo_basel.png", "logo_basel"],
}


def _norm_cod(cod: str | None) -> str:
    if not cod:
        return ""
    s = re.sub(r"\s+", "", str(cod).strip().upper())
    if s.startswith("ACR"):
        num = re.sub(r"^ACR", "", s)
        if num.isdigit():
            return f"ACR{int(num):02d}" if len(num) <= 2 else f"ACR{num}"
    return s


def _archivos_en_carpeta(dir_logos: str) -> dict[str, str]:
    """Mapa nombre en minusculas -> nombre real en disco."""
    out = {}
    if not dir_logos or not os.path.isdir(dir_logos):
        return out
    try:
        for nombre in os.listdir(dir_logos):
            ruta = os.path.join(dir_logos, nombre)
            if os.path.isfile(ruta):
                out[nombre.lower()] = nombre
    except OSError:
        pass
    return out


def _resolver_nombre(dir_logos: str, candidatos: list[str], cache: dict | None) -> str | None:
    if not dir_logos or not candidatos:
        return None
    idx = cache if cache is not None else _archivos_en_carpeta(dir_logos)

    for cand in candidatos:
        c = str(cand).strip()
        if not c:
            continue
        cl = c.lower()
        if cl in idx:
            return os.path.join(dir_logos, idx[cl])
        base, ext = os.path.splitext(c)
        if not ext:
            for e in _LOGO_EXT:
                key = (c + e).lower()
                if key in idx:
                    return os.path.join(dir_logos, idx[key])
        elif cl in idx:
            return os.path.join(dir_logos, idx[cl])

    return None


def resolve_logo_path(
    dir_logos: str,
    base_name: str,
    cod_acr: str | None = None,
    region_key: str | None = None,
    cache: dict | None = None,
) -> str:
    """
    Devuelve ruta existente al logo o ruta esperada (para placeholder en PDF).
    Orden: ACR especifico -> regional -> generico.
    """
    dir_logos = str(dir_logos or "").strip()
    region_key = (region_key or "").strip().lower()
    base_name = str(base_name or "").strip()
    idx = cache if cache is not None else _archivos_en_carpeta(dir_logos)

    candidatos: list[str] = []

    if base_name == "logo_anp":
        cod = _norm_cod(cod_acr)
        if cod:
            candidatos.append(f"logo_anp_{cod}")
            candidatos.extend(_ACR_LOGO_ALIASES.get(cod, []))
    elif base_name == "logo_gore" and region_key:
        candidatos.extend(_REGION_GORE.get(region_key, []))
        candidatos.append(f"logo_gore_{region_key}")
        if region_key == "loreto":
            candidatos.append("logo_gore")
    elif base_name == "logo_grrnga" and region_key:
        candidatos.extend(_REGION_GRRNGA.get(region_key, []))
        candidatos.append(f"logo_grrnga_{region_key}")
        if region_key == "loreto":
            candidatos.append("logo_grrnga")
    elif base_name in _GENERIC_BASE:
        candidatos.extend(_GENERIC_BASE[base_name])
    else:
        candidatos.append(base_name)

    found = _resolver_nombre(dir_logos, candidatos, idx)
    if found:
        return found

    fallback = candidatos[0] if candidatos else base_name
    if not os.path.splitext(fallback)[1]:
        fallback += ".png"
    return os.path.join(dir_logos, fallback)


def listar_logos_faltantes(dir_logos: str, region_key: str, codigos_acr: list[str]) -> list[str]:
    """Utilidad diagnostico: que logos ACR/GORE no se encuentran."""
    idx = _archivos_en_carpeta(dir_logos)
    faltan = []
    if not _resolver_nombre(dir_logos, _REGION_GORE.get(region_key, ["logo_gore"]), idx):
        faltan.append(f"GORE ({region_key})")
    if not _resolver_nombre(dir_logos, _REGION_GRRNGA.get(region_key, ["logo_grrnga"]), idx):
        faltan.append(f"Gerencia ({region_key})")
    for cod in codigos_acr:
        if not _resolver_nombre(
            dir_logos,
            [f"logo_anp_{_norm_cod(cod)}"] + _ACR_LOGO_ALIASES.get(_norm_cod(cod), []),
            idx,
        ):
            faltan.append(f"ACR {_norm_cod(cod)}")
    return faltan

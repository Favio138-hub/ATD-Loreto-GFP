# -*- coding: utf-8 -*-
"""
Diagnostico del entorno Python ATD (ejecutar FUERA de ArcGIS Pro o desde
Python Command Prompt de ArcGIS).

Uso:
  python diagnosticar_entorno_atd.py
"""
from __future__ import annotations

import os
import sys
import platform


def _line(msg=""):
    print(msg, flush=True)


def main():
    _line("=" * 70)
    _line("DIAGNOSTICO ENTORNO ATD")
    _line("=" * 70)
    _line(f"Sistema: {platform.system()} {platform.release()}")
    _line(f"Python: {sys.version}")
    _line(f"Ejecutable: {sys.executable}")
    _line()

    roaming = os.path.join(os.environ.get("APPDATA", ""), "Python")
    conflictos = []
    for p in sys.path:
        if roaming and roaming.lower() in p.replace("/", "\\").lower():
            conflictos.append(p)

    _line("--- Rutas Python en conflicto (AppData/Roaming) ---")
    if conflictos:
        _line("  PROBLEMA: pip instalo paquetes fuera del entorno de ArcGIS Pro.")
        _line("  Esto suele CERRAR ArcGIS Pro al usar GeoPandas/pyogrio.")
        for p in conflictos[:15]:
            _line(f"    {p}")
        if len(conflictos) > 15:
            _line(f"    ... y {len(conflictos) - 15} mas")
    else:
        _line("  OK: no se detectaron rutas Roaming en sys.path")
    _line()

    mods = [
        ("arcpy", "ArcGIS Pro / arcpy"),
        ("reportlab", "reportlab"),
        ("PIL", "pillow"),
        ("geopandas", "geopandas"),
        ("fiona", "fiona"),
        ("pyogrio", "pyogrio"),
        ("matplotlib", "matplotlib"),
        ("numpy", "numpy"),
        ("ee", "earthengine-api"),
    ]
    _line("--- Modulos ---")
    for mod, nombre in mods:
        try:
            m = __import__(mod)
            ruta = getattr(m, "__file__", "?")
            _line(f"  OK  {nombre:<22} {ruta}")
        except ImportError as ex:
            _line(f"  --  {nombre:<22} no instalado ({ex})")
        except Exception as ex:
            _line(f"  !!  {nombre:<22} error al importar: {ex}")
    _line()

    _line("--- Recomendacion ---")
    if conflictos:
        _line("1. Abra: Inicio > ArcGIS > Python Command Prompt")
        _line("2. Ejecute:")
        _line("     python -m pip uninstall pyogrio fiona geopandas -y")
        _line("     python -m pip install geopandas fiona --no-user")
        _line("3. En ArcGIS Pro use solo la herramienta 2 (PDF seguro).")
        _line("4. Cierre y vuelva a abrir ArcGIS Pro.")
    else:
        _line("Entorno base OK. Si Pro se cierra, use PDF seguro en toolbox H3.")
    _line("=" * 70)


if __name__ == "__main__":
    main()

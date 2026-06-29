# -*- coding: utf-8 -*-
"""
Worker: ejecuta Generar Reporte ATD fuera del proceso UI de ArcGIS Pro.
Uso: python atd_report_worker.py <ruta_job.json>
"""
from __future__ import annotations

import importlib.machinery
import json
import os
import sys
import traceback


def _sanear_sys_path():
    roaming = os.path.join(os.environ.get("APPDATA", ""), "Python")
    if not roaming:
        return
    sys.path[:] = [
        p for p in sys.path
        if not p.replace("/", "\\").lower().startswith(roaming.lower())
    ]


class _MockParam:
    """Imita arcpy.Parameter para execute() en subproceso."""

    def __init__(self, value, text=None):
        self.value = value
        self._text = text

    @property
    def valueAsText(self):
        if self._text is not None:
            return self._text
        v = self.value
        if v is None:
            return None
        if hasattr(v, "strftime"):
            return v.strftime("%d/%m/%Y")
        return str(v)


def _build_parameters(job, ix):
    """Lista de parametros en el orden de GenerarReporteATD."""
    n = max(ix.values()) + 1
    params = [None] * n

    def setp(key, val, text=None):
        params[ix[key]] = _MockParam(val, text)

    setp("gdb", job["gdb_path"])
    setp("fc_alertas", job["fc_alertas"])
    setp("fc_anp", job["fc_anp"])
    setp("fecha_ini", job.get("fecha_ini"), job.get("fecha_ini"))
    setp("fecha_fin", job.get("fecha_fin"), job.get("fecha_fin"))
    setp("base_salida", job["base_salida"])
    setp("dir_logos", job.get("dir_logos"))
    setp("acr_filtro", job.get("acr_filtro") or "TODAS")
    setp("alerta_sel", job.get("alerta_sel") or "")
    setp("gee_project", job.get("gee_project") or "")
    setp("fc_zonif", job.get("fc_zonif") or "gpo_zonif_anp")
    setp("descargar_gee", bool(job.get("descargar_gee")))
    setp("gee_dias", int(job.get("gee_dias") or 45))
    setp("gee_nubes", int(job.get("gee_nubes") or 35))
    setp("responsable", job.get("responsable") or "")
    setp("cargo", job.get("cargo") or "")
    setp("modo_estable", False)
    return params


def _patch_arcpy_logging():
    import arcpy

    def _out(prefix, msg):
        print(f"{prefix}{msg}", flush=True)

    arcpy.AddMessage = lambda m: _out("", m)
    arcpy.AddWarning = lambda m: _out("AVISO: ", m)
    arcpy.AddError = lambda m: _out("ERROR: ", m)


def main(job_path: str) -> int:
    _sanear_sys_path()
    os.environ["ATD_DENTRO_SUBPROCESO"] = "1"
    os.environ["PYTHONUNBUFFERED"] = "1"

    toolbox_dir = os.path.dirname(os.path.abspath(__file__))
    if toolbox_dir not in sys.path:
        sys.path.insert(0, toolbox_dir)

    with open(job_path, encoding="utf-8") as f:
        job = json.load(f)

    h3_path = os.path.join(toolbox_dir, "ATD_H3_Reporte_PDF.pyt")
    if not os.path.isfile(h3_path):
        print(f"ERROR: no se encuentra {h3_path}", flush=True)
        return 1

    try:
        _patch_arcpy_logging()
        # ArcGIS .pyt no tiene loader en importlib por extension; SourceFileLoader si
        mod = importlib.machinery.SourceFileLoader(
            "atd_h3_reporte", h3_path
        ).load_module()

        ix = mod.GenerarReporteATD._IX
        parameters = _build_parameters(job, ix)
        tool = mod.GenerarReporteATD()
        tool.execute(parameters, None)
        return 0
    except Exception as ex:
        print(f"ERROR worker: {ex}", flush=True)
        print(traceback.format_exc(), flush=True)
        return 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python atd_report_worker.py <job.json>", flush=True)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))

# -*- coding: utf-8 -*-
"""
Ejecuta Generar Reporte ATD sin GeoPandas dentro del proceso de ArcGIS Pro.
El PDF se genera en un subproceso Python separado (ReportLab) para que Pro no se cierre.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import traceback
from datetime import datetime

import arcpy

from atd_arcpy_io import (
    etiqueta_alerta,
    filtrar_registros_seleccion,
    leer_alertas_arcpy,
    listar_opciones_alertas_arcpy,
    parse_seleccion_alerta,
    resumen_diagnostico,
)
from atd_region_config import (
    ACR_GEO,
    ACR_NOMBRES,
    DEPARTAMENTO_REPORTE,
    GERENCIA_REGIONAL,
    GOBIERNO_REGIONAL,
    LOGO_REGION_KEY,
    REGION_NOMBRE,
    REPORTE_TAG,
    SUBGERENCIA_REGIONAL,
    TEXTO_CIERRE,
    _REGION_ACTIVA,
    _utm_epsg_region,
    configurar_region,
    sincronizar_imports_region,
)


def _sanear_sys_path():
    roaming = os.path.join(os.environ.get("APPDATA", ""), "Python")
    if not roaming:
        return
    sys.path[:] = [
        p for p in sys.path
        if not p.replace("/", "\\").lower().startswith(roaming.lower())
    ]


def _python_arcgis_pro():
    cands = [
        os.environ.get("ARCGISPRO_PYTHON"),
        os.path.join(
            os.environ.get("CONDA_PREFIX", ""),
            "python.exe",
        ),
        r"C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe",
        r"C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3-clone\python.exe",
    ]
    for c in cands:
        if c and os.path.isfile(c):
            return c
    exe = sys.executable or ""
    if exe.lower().endswith("python.exe"):
        return exe
    return None


def _urls_vista(este, norte, epsg):
    try:
        import pyproj
        tr = pyproj.Transformer.from_crs(
            f"EPSG:{epsg}", "EPSG:4326", always_xy=True
        )
        lon, lat = tr.transform(float(este), float(norte))
    except Exception:
        return (
            "https://apps.sentinel-hub.com/eo-browser/",
            "https://earth.google.com/web/",
            0.0, 0.0,
        )
    eo = f"https://apps.sentinel-hub.com/eo-browser/?lat={lat:.6f}&lng={lon:.6f}&zoom=15&theme=dark"
    gee = f"https://earth.google.com/web/@{lat:.6f},{lon:.6f},1200a,500d,35y,0h,0t,0r"
    return eo, gee, lat, lon


def _serializar_registro(rec, epsg):
    geo = ACR_GEO.get(rec.get("anp_codi", ""), {})
    f = rec.get("md_fecimg")
    if isinstance(f, datetime):
        fecha_str = f.strftime("%d/%m/%Y")
    else:
        fecha_str = str(f or "-")
    este = rec.get("este_utm") or rec.get("md_este")
    norte = rec.get("norte_utm") or rec.get("md_norte")
    return {
        **{k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in rec.items()},
        "provincia": geo.get("provincia", "-"),
        "distrito": geo.get("distrito", "-"),
        "fecha_str": fecha_str,
        "este_utm": este,
        "norte_utm": norte,
        "md_este": este,
        "md_norte": norte,
        "_epsg": epsg,
    }


def _stream_subproceso(cmd, cwd, env, msg_fn, timeout=7200):
    """Ejecuta comando y reenvia salida al panel de Geoprocessing."""
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=cwd,
        env=env,
    )
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                msg_fn(line)
        return proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        msg_fn("ERROR: subproceso supero el tiempo limite.")
        return -1


def ejecutar_reporte_subproceso_completo(params):
    """
    PDF completo (mapa matplotlib, Sentinel opcional, layout oficial)
    en subproceso Python — ArcGIS Pro solo orquesta, no carga GeoPandas.
    """
    _sanear_sys_path()
    fn = params.get("msg_fn") or arcpy.AddMessage

    tmp_dir = tempfile.mkdtemp(prefix="atd_full_job_")
    job_path = os.path.join(tmp_dir, "job.json")
    job = {
        "gdb_path": params["gdb_path"],
        "fc_alertas": params["fc_alertas"],
        "fc_anp": params["fc_anp"],
        "fc_zonif": params.get("fc_zonif") or "gpo_zonif_anp",
        "fecha_ini": params["fecha_ini"],
        "fecha_fin": params["fecha_fin"],
        "base_salida": params["base_salida"],
        "dir_logos": params.get("dir_logos"),
        "alerta_sel": params.get("alerta_sel") or "",
        "acr_filtro": params.get("acr_filtro") or "",
        "descargar_gee": bool(params.get("descargar_gee")),
        "gee_project": params.get("gee_project") or "",
        "gee_dias": int(params.get("gee_dias") or 45),
        "gee_nubes": int(params.get("gee_nubes") or 35),
        "responsable": params.get("responsable") or "",
        "cargo": params.get("cargo") or "",
    }
    with open(job_path, "w", encoding="utf-8") as f:
        json.dump(job, f, ensure_ascii=False, default=str)

    toolbox_dir = os.path.dirname(os.path.abspath(__file__))
    worker = os.path.join(toolbox_dir, "atd_report_worker.py")
    py = _python_arcgis_pro()
    if not py or not os.path.isfile(worker):
        fn("  AVISO: no se pudo lanzar subproceso; use Modo estable.")
        raise RuntimeError("Python de ArcGIS Pro o atd_report_worker.py no encontrado")

    env = os.environ.copy()
    env["ATD_DENTRO_SUBPROCESO"] = "1"
    env["ATD_USAR_CONTEXTILY"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    if toolbox_dir not in env.get("PYTHONPATH", ""):
        env["PYTHONPATH"] = toolbox_dir + os.pathsep + env.get("PYTHONPATH", "")

    fn("  Subproceso PDF completo (mapa + imagenes; Pro permanece abierto)...")
    fn(f"  Python: {py}")
    rc = _stream_subproceso([py, worker, job_path], toolbox_dir, env, fn)
    if rc != 0:
        arcpy.AddWarning(
            f"Subproceso termino con codigo {rc}. "
            "Revise mensajes arriba o pruebe Modo estable."
        )
    else:
        fn("  Subproceso finalizado correctamente.")


def _generar_pdf_subproceso(job, msg_fn):
    py = _python_arcgis_pro()
    toolbox_dir = os.path.dirname(os.path.abspath(__file__))
    worker = os.path.join(toolbox_dir, "atd_pdf_build.py")
    tmp_dir = tempfile.mkdtemp(prefix="atd_job_")
    job_path = os.path.join(tmp_dir, "job.json")
    with open(job_path, "w", encoding="utf-8") as f:
        json.dump(job, f, ensure_ascii=False, default=str)

    if py and os.path.isfile(worker):
        msg_fn("  -> PDF en subproceso (Pro permanece abierto)...")
        cmd = [py, worker, job_path]
        try:
            r = subprocess.run(
                cmd, capture_output=True, text=True, timeout=180, cwd=toolbox_dir
            )
            if r.returncode != 0:
                msg_fn(f"  AVISO subproceso: {r.stderr[:500]}")
                raise RuntimeError(r.stderr or "subproceso PDF fallo")
            if r.stdout.strip():
                return r.stdout.strip()
            if os.path.isfile(job["pdf_path"]):
                return job["pdf_path"]
        except Exception as ex:
            msg_fn(f"  AVISO: subproceso fallo ({ex}); PDF en mismo proceso...")
    _sanear_sys_path()
    from atd_pdf_build import generar_pdf_atd
    return generar_pdf_atd(job)


def ejecutar_reporte_modo_estable(params):
    """
    params: dict con gdb_path, fc_alertas, fechas, base_salida, dir_logos,
            alerta_sel, acr_filtro, responsable, cargo, msg_fn=arcpy.AddMessage
    """
    _sanear_sys_path()
    fn = params.get("msg_fn") or arcpy.AddMessage
    fn("  ATD Reporte v7.4 — generacion segura (ArcPy en Pro, PDF aparte)")

    GDB_PATH = params["gdb_path"]
    configurar_region(GDB_PATH, force=True)
    sincronizar_imports_region(globals())
    FC_ALERTAS = params["fc_alertas"]
    FECHA_INI = params["fecha_ini"]
    FECHA_FIN = params["fecha_fin"]
    BASE_SALIDA = params["base_salida"]
    DIR_LOGOS = params["dir_logos"]
    ALERTA_SEL = params.get("alerta_sel") or ""
    ACR_FILTRO = params.get("acr_filtro") or ""
    RESPONSABLE = (params.get("responsable") or "").strip() or "-"
    CARGO = (params.get("cargo") or "").strip() or "-"

    DIR_DOCS = os.path.join(BASE_SALIDA, "documentacion_atd")
    DIR_IMAGENES = os.path.join(BASE_SALIDA, "imagenes_sentinel")
    DIR_PDFS = os.path.join(BASE_SALIDA, "pdfs")
    os.makedirs(DIR_DOCS, exist_ok=True)
    os.makedirs(DIR_PDFS, exist_ok=True)

    fn_prep = params.get("fn_prep_docs")
    fn_link = params.get("fn_link_vis")
    if not fn_prep or not fn_link:
        arcpy.AddError("Configuracion interna incompleta (HTML). Actualice la toolbox.")
        return

    LINK_MET, LINK_PROC = fn_prep(DIR_DOCS, REGION_NOMBRE)
    fn(f"  Documentacion HTML: {DIR_DOCS}")

    oid_hint = parse_seleccion_alerta(ALERTA_SEL)
    objectid = oid_hint if isinstance(oid_hint, int) else None

    try:
        registros = leer_alertas_arcpy(
            GDB_PATH, FC_ALERTAS, FECHA_INI, FECHA_FIN,
            objectid=objectid, acr_filtro=ACR_FILTRO, msg_fn=fn,
        )
    except Exception as e:
        arcpy.AddError(f"Error leyendo alertas: {e}")
        arcpy.AddError(traceback.format_exc())
        return

    if not registros:
        arcpy.AddError("Sin alertas en el periodo. Ejecute Diagnostico Pre-Vuelo.")
        return

    if not objectid:
        regs_proc, modo = filtrar_registros_seleccion(registros, ALERTA_SEL)
    else:
        regs_proc, modo = registros, "una"

    if modo == "sin_alertas" or modo == "no_oid":
        arcpy.AddError("Alerta no encontrada. Actualice la lista tras Diagnostico Pre-Vuelo.")
        return
    if modo == "match" and len(regs_proc) != 1:
        arcpy.AddError(
            f"Seleccion ambigua ({len(regs_proc)} coincidencias). "
            "Elija una alerta con OID:NNN| al inicio."
        )
        return
    if modo == "invalid":
        arcpy.AddError("Seleccion de alerta no valida.")
        return

    fn(f"  Procesando {len(regs_proc)} alerta(s)  |  modo={modo}")
    EPSG = _utm_epsg_region()
    ANNO = int(FECHA_FIN.split("/")[-1])
    pdfs = []
    errores = []
    inicio = datetime.now()

    for idx, rec in enumerate(regs_proc):
        oid = rec.get("objectid", idx)
        cod = rec.get("anp_codi", "??")
        fn(f"\n[{idx + 1}/{len(regs_proc)}] OID={oid} | {cod} | {rec.get('causa_texto')}")

        alerta = _serializar_registro(rec, EPSG)
        este = alerta.get("md_este") or 0
        norte = alerta.get("md_norte") or 0
        url_eo, url_gee, lat, lon = _urls_vista(este, norte, EPSG)
        sigla = alerta.get("acr_sigla", cod)
        cod_rep = f"RT-ATD-ACR-{sigla}-{ANNO}-{idx + 1:04d}"

        from atd_imagenes_h3 import buscar_imagen_local
        pa, meta_a = buscar_imagen_local(
            DIR_IMAGENES, "A", oid, ALERTA_SEL, regenerar_si_falta=True)
        pd_, meta_d = buscar_imagen_local(
            DIR_IMAGENES, "D", oid, ALERTA_SEL, regenerar_si_falta=True)
        fecha_a = fecha_d = "—"
        sat_a = sat_d = "Imagen satelital"
        if meta_a:
            fecha_a = str(meta_a.get("fecha", "—") or "—")
            sat_a = str(meta_a.get("sat", sat_a) or sat_a)
        if meta_d:
            fecha_d = str(meta_d.get("fecha", "—") or "—")
            sat_d = str(meta_d.get("sat", sat_d) or sat_d)

        link_visual = fn_link(
            DIR_DOCS, oid, url_eo, url_gee, fecha_a, fecha_d, lat, lon, cod_rep,
            ruta_img_a=pa, ruta_img_d=pd_, sat_a=sat_a, sat_d=sat_d,
        )
        pdf_name = f"ATD_{ANNO}_{cod}_{idx + 1:03d}_OID{oid}.pdf"
        pdf_path = os.path.join(DIR_PDFS, pdf_name)

        job = {
            "pdf_path": pdf_path,
            "idx": idx,
            "mapa_path": None,
            "cfg": {
                "dir_logos": DIR_LOGOS,
                "region_key": _REGION_ACTIVA or LOGO_REGION_KEY or "loreto",
                "fecha_ini": FECHA_INI,
                "fecha_fin": FECHA_FIN,
                "anno_reporte": ANNO,
                "departamento": DEPARTAMENTO_REPORTE,
                "gobierno_regional": GOBIERNO_REGIONAL,
                "gerencia_regional": GERENCIA_REGIONAL,
                "subgerencia_regional": SUBGERENCIA_REGIONAL,
                "responsable": RESPONSABLE,
                "cargo": CARGO,
            },
            "alerta": alerta,
            "links": {
                "url_eo": url_eo,
                "url_gee": url_gee,
                "link_visualizacion": link_visual,
                "link_metodologia": LINK_MET,
                "link_procedimiento": LINK_PROC,
                "fecha_a": fecha_a,
                "fecha_d": fecha_d,
            },
        }
        try:
            out = _generar_pdf_subproceso(job, fn)
            pdfs.append(out)
            fn(f"  OK PDF: {os.path.basename(out)}")
        except Exception as e:
            errores.append(str(e))
            arcpy.AddWarning(f"  ERROR: {e}")
            arcpy.AddWarning(traceback.format_exc())

    dur = (datetime.now() - inicio).total_seconds()
    fn(f"\n{'=' * 65}")
    fn(f"LISTO | PDFs: {len(pdfs)} | Errores: {len(errores)} | {dur:.0f}s")
    fn(f"Carpeta: {DIR_PDFS}")
    for p in pdfs:
        fn(f"  -> {os.path.basename(p)}")
    fn("=" * 65)
    fn(TEXTO_CIERRE)
    fn("=" * 65)


def run_diagnostico_arcpy(gdb_path, fc_alertas, fecha_ini, fecha_fin, base_salida=None):
    import json

    from atd_arcpy_io import DOMINIO_CAUSA

    base_salida = base_salida or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    configurar_region(gdb_path, force=True)
    sincronizar_imports_region(globals())
    arcpy.AddMessage("=" * 65)
    arcpy.AddMessage(f"DIAGNOSTICO PRE-VUELO - {REGION_NOMBRE.upper()}")
    arcpy.AddMessage("  (lectura solo arcpy — sin GeoPandas)")
    arcpy.AddMessage("=" * 65)

    registros = leer_alertas_arcpy(
        gdb_path, fc_alertas, fecha_ini, fecha_fin, msg_fn=arcpy.AddMessage
    )
    by_acr, by_causa, fechas = resumen_diagnostico(registros)
    arcpy.AddMessage("")
    arcpy.AddMessage(f'  {"ACR":<8}  {"Nombre":<42}  {"N":>5}  {"Ha":>10}')
    arcpy.AddMessage("  " + "-" * 70)
    for cod, nom in ACR_NOMBRES.items():
        rows = by_acr.get(cod, [])
        n = len(rows)
        h = sum(float(r.get("md_sup") or 0) for r in rows)
        flag = "" if n > 0 else "  <- SIN ALERTAS"
        arcpy.AddMessage(f"  {cod:<8}  {nom:<42}  {n:>5,}  {h:>10.4f}{flag}")

    if registros:
        arcpy.AddMessage("")
        arcpy.AddMessage("  Por causa:")
        for val, cnt in sorted(by_causa.items(), key=lambda x: -x[1]):
            arcpy.AddMessage(
                f"    {int(val):>2} ({DOMINIO_CAUSA.get(int(val), '?'):<25}) -> {cnt:,}"
            )
        if fechas:
            arcpy.AddMessage(f"  Fecha inicio: {min(fechas).strftime('%d/%m/%Y')}")
            arcpy.AddMessage(f"  Fecha fin   : {max(fechas).strftime('%d/%m/%Y')}")
        arcpy.AddMessage(f"\n  {len(registros)} alertas listas para reporte")
        try:
            meta_path = os.path.join(base_salida, "periodo_reporte_atd.json")
            os.makedirs(base_salida, exist_ok=True)
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(
                    {"fecha_ini": fecha_ini, "fecha_fin": fecha_fin,
                     "n_alertas": len(registros)},
                    f, ensure_ascii=False,
                )
            arcpy.AddMessage(f"  Periodo guardado: {meta_path}")
        except Exception as ex:
            arcpy.AddWarning(f"  No se pudo guardar periodo: {ex}")
    else:
        arcpy.AddWarning("  SIN alertas en este periodo.")

# -*- coding: utf-8 -*-
"""
Genera PDF ATD con ReportLab solamente (sin GeoPandas).
Invocado desde ArcGIS Pro en subproceso para no cerrar la aplicacion.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime


def _sanear_sys_path():
    roaming = os.path.join(os.environ.get("APPDATA", ""), "Python")
    if not roaming:
        return
    sys.path[:] = [
        p for p in sys.path
        if not p.replace("/", "\\").lower().startswith(roaming.lower())
    ]


def generar_pdf_atd(job):
    """job: dict con claves cfg, alerta, idx, links, rutas."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm, mm
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        Image as RLImage, HRFlowable,
    )
    from PIL import Image as PILImage

    cfg = job["cfg"]
    a = job["alerta"]
    idx = int(job.get("idx", 0))
    links = job.get("links", {})

    C_AZUL_GFP = colors.HexColor("#2F5F8F")
    C_ROJO = colors.HexColor("#C41E3A")
    C_ROJO_D = colors.HexColor("#8B1528")
    C_VERDE_CB = C_AZUL_GFP
    C_AZUL_CB = colors.HexColor("#3A7CA5")
    C_GRIS_F = colors.HexColor("#F4F6F8")
    C_BORDE = colors.HexColor("#B8C8D8")
    C_BORDE_EXT = C_AZUL_GFP
    C_BLANCO = colors.white
    C_NEGRO = colors.black
    C_LINK = colors.HexColor("#2F5F8F")

    def _s(texto, fuente="Helvetica", tam=8, color=None, align=TA_LEFT,
           bold=False, italic=False, leading=10, **kw):
        if color is None:
            color = C_NEGRO
        f = fuente
        if bold and italic:
            f += "-BoldOblique"
        elif bold:
            f += "-Bold"
        elif italic:
            f += "-Oblique"
        return Paragraph(
            str(texto),
            ParagraphStyle("_x", fontName=f, fontSize=tam, textColor=color,
                           alignment=align, leading=leading, **kw),
        )

    def img_rl(ruta, max_w, max_h, label=""):
        if not ruta or not os.path.exists(str(ruta)):
            return _s(f"[ {label} ]", align=TA_CENTER, color=colors.grey, tam=7)
        try:
            iw, ih = PILImage.open(str(ruta)).size
            if iw < 1 or ih < 1:
                return _s(f"[ {label} ]", align=TA_CENTER, color=colors.grey, tam=7)
            ratio = iw / ih
            mw, mh = float(max_w), float(max_h)
            if mw / mh > ratio:
                h_use, w_use = mh, mh * ratio
            else:
                w_use, h_use = mw, mw / ratio
            return RLImage(str(ruta), width=w_use, height=h_use)
        except Exception:
            return _s(f"[ {label} ]", align=TA_CENTER, color=colors.grey, tam=7)

    def celda_centro(flow, ancho, alto):
        t = Table([[flow]], colWidths=[ancho], rowHeights=[alto])
        t.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        return t

    def cab(numero, titulo, ancho):
        t = Table([[_s(f"{numero}.  {titulo}", bold=True, tam=7.5, color=C_BLANCO)]],
                  colWidths=[ancho])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), C_VERDE_CB),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ]))
        return t

    def tabla_sec(numero, titulo, filas, w1, w2):
        datos = [[_s(l, bold=True, tam=7.5), _s(str(v) if v else "-", tam=7.5)]
                 for l, v in filas]
        ti = Table(datos, colWidths=[w1, w2])
        ti.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [C_BLANCO, C_GRIS_F]),
            ("LINEBELOW", (0, 0), (-1, -2), 0.3, C_BORDE),
            ("BOX", (0, 0), (-1, -1), 0.5, C_BORDE),
        ]))
        wrap = Table([[cab(numero, titulo, w1 + w2)], [ti]], colWidths=[w1 + w2])
        wrap.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 1.2, C_BORDE_EXT),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        return wrap

    def tabla_sec_link(numero, titulo, filas_link, w1, w2):
        textos = {
            "Metodologia:": "Abrir metodologia (documento HTML)",
            "Procedimiento:": "Abrir guia de fotointerpretacion",
            "Visualizacion:": "Abrir Dashboard ACR (monitoreo deforestacion)",
        }
        datos = []
        for l, url in filas_link:
            txt = textos.get(l, "Abrir enlace")
            datos.append([
                _s(l, bold=True, tam=7),
                _s(
                    f'<link href="{url}"><u><font color="{C_LINK.hexval()}">'
                    f"{txt}</font></u></link>",
                    tam=6.5, leading=8,
                ),
            ])
        ti = Table(datos, colWidths=[w1, w2])
        ti.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [C_BLANCO, C_GRIS_F]),
            ("LINEBELOW", (0, 0), (-1, -2), 0.3, C_BORDE),
            ("BOX", (0, 0), (-1, -1), 0.5, C_BORDE),
        ]))
        wrap = Table([[cab(numero, titulo, w1 + w2)], [ti]], colWidths=[w1 + w2])
        wrap.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 1.2, C_BORDE_EXT),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        return wrap

    oid = a.get("objectid", idx)
    cod_acr = str(a.get("anp_codi", "SIN")).strip()
    sigla = a.get("acr_sigla", cod_acr)
    nombre_acr = a.get("acr_nombre", cod_acr)
    causa = a.get("causa_texto", "Sin clasificar")
    bosque = a.get("bosque_texto", "-")
    confianza = a.get("conf_texto", "-")
    zonif = str(a.get("md_zonif", "") or "-")
    superficie = float(a.get("md_sup", 0) or 0)
    este = a.get("md_este")
    norte = a.get("md_norte")
    grilla = str(a.get("md_exa", "") or "-")
    lugar_poblado = str(a.get("lugar_poblado", "") or "-")
    sector_rep = str(a.get("sector_reporte", "") or "-")
    olv_cercano = str(a.get("olv_cercano", "") or "-")
    provincia = a.get("provincia", "-")
    distrito = a.get("distrito", "-")
    fecha_str = a.get("fecha_str", "-")
    fecha_emision = datetime.now().strftime("%d/%m/%Y")
    anno = int(cfg.get("anno_reporte", datetime.now().year))
    cod_reporte = f"RT-ATD-ACR-{sigla}-{anno}-{idx + 1:04d}"

    DIR_LOGOS = cfg["dir_logos"]
    RK_LOGOS = cfg.get("region_key", "loreto")
    mapa_path = job.get("mapa_path")
    fecha_a = links.get("fecha_a", "-")
    fecha_d = links.get("fecha_d", "-")
    url_eo = links.get("url_eo", "https://apps.sentinel-hub.com/eo-browser/")
    url_gee = links.get("url_gee", "https://earth.google.com/web/")
    from atd_region_config import URL_DASHBOARD_ACR
    link_vis = URL_DASHBOARD_ACR
    link_met = links.get("link_metodologia", "")
    link_proc = links.get("link_procedimiento", "")

    pdf_path = job["pdf_path"]
    MARGIN_L = 0.85 * cm
    MARGIN_R = 0.85 * cm
    W = A4[0] - MARGIN_L - MARGIN_R
    GAP_COL = 2 * mm
    W1, W2 = 3.0 * cm, 3.55 * cm
    W_COL_TABLAS = W1 + W2
    ancho_mapa = W - W_COL_TABLAS - GAP_COL
    W_PAIR = (W - GAP_COL) / 2
    WA = W_PAIR * 0.42
    WB = W_PAIR * 0.58

    doc = SimpleDocTemplate(
        pdf_path, pagesize=A4,
        leftMargin=MARGIN_L, rightMargin=MARGIN_R,
        topMargin=0.45 * cm, bottomMargin=0.4 * cm,
    )
    story = []

    def logo_path(base_name, cod=None):
        from atd_logos import resolve_logo_path
        return resolve_logo_path(DIR_LOGOS, base_name, cod, RK_LOGOS)

    LW, LH = 2.25 * cm, 1.55 * cm
    logo_gfp_h = celda_centro(img_rl(logo_path("logo_gfp"), LW, LH, "GFP"), LW, LH)
    logo_anp_h = celda_centro(img_rl(logo_path("logo_anp", cod_acr), LW, LH, "ACR"), LW, LH)
    bloque_texto = [
        _s(cfg["gobierno_regional"], bold=True, tam=8.5, align=TA_CENTER, leading=11),
        _s(cfg["gerencia_regional"], bold=True, tam=7.2, align=TA_CENTER, leading=9),
        _s(cfg["subgerencia_regional"], bold=True, tam=6.8, align=TA_CENTER, leading=9),
    ]
    if RK_LOGOS == "san_martin":
        logo_gore = celda_centro(
            img_rl(logo_path("logo_gore"), 4.5 * cm, LH, "GORE"),
            4.5 * cm, LH,
        )
        cw_logo = 2.25 * cm
        cw_txt = W - (3 * cw_logo) - 4.5 * cm
        t_hdr = Table(
            [[logo_gore, bloque_texto, logo_gfp_h, logo_anp_h]],
            colWidths=[4.5 * cm, cw_txt, cw_logo, cw_logo],
        )
    else:
        logo_gore = celda_centro(img_rl(logo_path("logo_gore"), LW, LH, "GORE"), LW, LH)
        logo_ger = celda_centro(img_rl(logo_path("logo_grrnga"), LW, LH, "GRRNGA"), LW, LH)
        cw_logo = 2.25 * cm
        cw_txt = W - (4 * cw_logo)
        t_hdr = Table(
            [[logo_gore, logo_ger, bloque_texto, logo_gfp_h, logo_anp_h]],
            colWidths=[cw_logo, cw_logo, cw_txt, cw_logo, cw_logo],
        )
    t_hdr.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BOX", (0, 0), (-1, -1), 1.2, C_BORDE_EXT),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("BACKGROUND", (0, 0), (-1, -1), C_BLANCO),
    ]))
    story.append(t_hdr)
    story.append(Spacer(1, 0.4 * mm))

    t_titulo = Table([
        [_s("REPORTE TECNICO SOBRE ALERTA TEMPRANA DE DEFORESTACION",
            bold=True, tam=12, color=C_ROJO, align=TA_CENTER, leading=15)],
        [_s(nombre_acr.upper(), bold=True, tam=10, color=C_BLANCO, align=TA_CENTER)],
    ], colWidths=[W])
    t_titulo.setStyle(TableStyle([
        ("BACKGROUND", (0, 1), (-1, 1), C_ROJO),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("BOX", (0, 0), (-1, -1), 1.2, C_ROJO_D),
    ]))
    story.append(t_titulo)
    story.append(Spacer(1, 0.4 * mm))

    t_s1 = tabla_sec("1", "Ubicacion en circunscripcion", [
        ("Departamento:", cfg.get("departamento", "-")),
        ("Provincia:", provincia),
        ("Distrito:", distrito),
        ("Lugar Poblado Cercano:", lugar_poblado),
    ], W1, W2)
    t_s2 = tabla_sec("2", "Ubicacion en area de conservacion", [
        ("Nombre de ACR:", nombre_acr),
        ("Zonificacion:", zonif),
        ("Sector:", sector_rep),
        ("OLV Cercano:", olv_cercano),
    ], W1, W2)
    t_per = Table([[
        _s("Periodo de Monitoreo:", bold=True, tam=7.5),
        _s(f"{cfg['fecha_ini']} - {cfg['fecha_fin']}", tam=7.5),
    ]], colWidths=[W1, W2])
    t_per.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("BOX", (0, 0), (-1, -1), 1.2, C_BORDE_EXT),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, C_BORDE),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
    ]))
    col_izq = [t_s1, Spacer(1, 0.6 * mm), t_s2, Spacer(1, 0.6 * mm), t_per]
    alto_mapa = 6.55 * cm
    mapa_img = celda_centro(
        img_rl(mapa_path, ancho_mapa, alto_mapa, "Mapa ACR (modo estable)"),
        ancho_mapa, alto_mapa,
    )
    t_mapa_wrap = Table([[mapa_img]], colWidths=[ancho_mapa], rowHeights=[alto_mapa])
    t_mapa_wrap.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1.2, C_BORDE_EXT),
    ]))
    t_ficha = Table([[col_izq, "", t_mapa_wrap]],
                    colWidths=[W_COL_TABLAS, GAP_COL, ancho_mapa])
    t_ficha.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(t_ficha)
    story.append(Spacer(1, 0.4 * mm))

    t_ve_cab = Table([[
        _s("Vista Estatica de la Alerta Temprana de Deforestacion",
           bold=True, tam=8, color=C_BLANCO, align=TA_CENTER),
    ]], colWidths=[W])
    t_ve_cab.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_AZUL_GFP),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("BOX", (0, 0), (-1, -1), 1.2, C_BORDE_EXT),
    ]))
    story.append(t_ve_cab)
    story.append(Spacer(1, 0.3 * mm))

    AW = W / 2
    AH = 3.15 * cm

    def cab_img(texto):
        t = Table([[_s(texto, bold=True, tam=7.5, color=C_BLANCO, align=TA_CENTER)]],
                  colWidths=[AW])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), C_AZUL_CB),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        return t

    t_s2imgs = Table([
        [cab_img("Imagen A — antes del cambio"),
         cab_img("Imagen B — con el cambio detectado")],
        [celda_centro(img_rl(None, AW, AH, "Sin imagen A"), AW, AH),
         celda_centro(img_rl(None, AW, AH, "Sin imagen B"), AW, AH)],
    ], colWidths=[AW, AW], rowHeights=[None, AH + 2 * mm])
    t_s2imgs.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BOX", (0, 0), (-1, -1), 1.2, C_BORDE_EXT),
        ("LINEAFTER", (0, 0), (0, -1), 0.5, C_BORDE),
    ]))
    story.append(t_s2imgs)
    story.append(Spacer(1, 0.4 * mm))

    t_s3 = tabla_sec("3", "Datos de Monitoreo", [
        ("Codigo de Alerta:", cod_reporte),
        ("Periodo de Monitoreo:", f"{cfg['fecha_ini']} - {cfg['fecha_fin']}"),
        ("Nivel de confiabilidad:", confianza),
        ("Coordenada Este (m):", f"{float(este):,.1f}" if este else "-"),
        ("Coordenada Norte (m):", f"{float(norte):,.1f}" if norte else "-"),
    ], WA, WB)
    t_s4 = tabla_sec("4", "Datos de Afectacion", [
        ("Causa:", causa),
        ("Efecto:", "Perdida de Habitat"),
        ("Tipo de Bosque:", bosque),
        ("Superficie Afectada (ha):", f"{superficie:.2f}"),
        ("Codigo de Grilla:", grilla),
        ("Fecha imagen:", fecha_str),
    ], WA, WB)
    t_34 = Table([[t_s3, "", t_s4]], colWidths=[W_PAIR, GAP_COL, W_PAIR])
    t_34.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(t_34)
    story.append(Spacer(1, 0.35 * mm))

    t_s5 = tabla_sec("5", "Datos de Produccion", [
        ("Responsable:", cfg.get("responsable", "-")),
        ("Cargo:", cfg.get("cargo", "-")),
        ("Fecha de emision:", fecha_emision),
    ], WA, WB)
    t_s6 = tabla_sec_link("6", "Datos de Elaboracion", [
        ("Metodologia:", link_met),
        ("Procedimiento:", link_proc),
        ("Visualizacion:", link_vis),
    ], WA, WB)
    t_56 = Table([[t_s5, "", t_s6]], colWidths=[W_PAIR, GAP_COL, W_PAIR])
    t_56.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(t_56)

    logo_gfp2 = celda_centro(img_rl(logo_path("logo_gfp"), 3.2 * cm, 1.2 * cm, "GFP"),
                             3.4 * cm, 1.25 * cm)
    logo_seco = celda_centro(
        img_rl(logo_path("logo_seco"), 4.2 * cm, 1.2 * cm, "SECO"),
        4.4 * cm, 1.25 * cm,
    )
    t_footer = Table([[
        [_s("Con la asistencia", italic=True, tam=7, bold=True),
         _s("tecnica de:", italic=True, tam=7, bold=True)],
        logo_gfp2,
        logo_seco,
    ]], colWidths=[W * 0.25, W * 0.35, W * 0.40])
    t_footer.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BOX", (0, 0), (-1, -1), 1.2, C_BORDE_EXT),
        ("BACKGROUND", (0, 0), (-1, -1), C_GRIS_F),
    ]))
    story.append(t_footer)

    doc.build(story)
    return pdf_path


def main():
    _sanear_sys_path()
    job_path = sys.argv[1]
    with open(job_path, "r", encoding="utf-8") as f:
        job = json.load(f)
    out = generar_pdf_atd(job)
    print(out)


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
HTML interactivo swipe antes/despues con imagenes exportadas desde H2 (Visor Satelital).
"""
from __future__ import annotations

import os


def _html_escape(t):
    return (
        str(t or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _relpath_html(ruta_html: str, ruta_img: str) -> str:
    rel = os.path.relpath(
        os.path.abspath(ruta_img),
        os.path.dirname(os.path.abspath(ruta_html)),
    )
    return rel.replace("\\", "/")


def generar_html_swipe_local(
    ruta_html: str,
    ruta_img_antes: str,
    ruta_img_despues: str,
    *,
    fecha_antes: str = "-",
    fecha_despues: str = "-",
    sat_antes: str = "Imagen A",
    sat_despues: str = "Imagen B",
    cod_reporte: str = "",
    oid: int | str = "",
    url_eo_fallback: str = "",
) -> None:
    """Genera HTML con comparador swipe sobre PNG locales (H2 -> imagenes_sentinel/)."""
    src_a = _relpath_html(ruta_html, ruta_img_antes)
    src_d = _relpath_html(ruta_html, ruta_img_despues)
    titulo = f"Comparación ATD — OID {oid}" if oid else "Comparación ATD — Antes / Después"
    btn_eo = ""
    if url_eo_fallback and str(url_eo_fallback).startswith("http"):
        btn_eo = (
            f'<a class="btn secondary" href="{_html_escape(url_eo_fallback)}" '
            f'target="_blank" rel="noopener">Abrir EO Browser (alternativa)</a>'
        )

    cuerpo = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{_html_escape(titulo)}</title>
<style>
:root {{
  --azul:#2F5F8F; --rojo:#C41E3A; --gris:#F4F6F8; --texto:#1A2B3C; --borde:#B8C8D8;
}}
* {{ box-sizing: border-box; }}
body {{
  font-family: "Segoe UI", Arial, sans-serif;
  margin: 0; padding: 20px 24px 28px;
  color: var(--texto); background: #fff; line-height: 1.45;
}}
.tag {{
  display: inline-block; background: #E8EEF4; color: var(--azul);
  padding: 3px 10px; border-radius: 4px; font-size: 0.82em; margin-bottom: 10px;
}}
h1 {{
  color: var(--azul); font-size: 1.35em; margin: 0 0 8px;
  border-bottom: 3px solid var(--rojo); padding-bottom: 8px;
}}
.meta {{
  display: flex; flex-wrap: wrap; gap: 10px 18px; margin: 12px 0 16px;
  background: var(--gris); border-left: 4px solid var(--azul);
  padding: 10px 14px; font-size: 0.92em;
}}
.meta strong {{ color: var(--azul); }}
.note {{
  background: #fff8e8; border: 1px solid #e8d8a0; border-radius: 6px;
  padding: 8px 12px; margin: 0 0 14px; font-size: 0.88em;
}}
.compare-wrap {{
  max-width: 960px; margin: 0 auto 16px;
  border: 2px solid var(--borde); border-radius: 10px;
  overflow: hidden; background: #111;
  box-shadow: 0 4px 18px rgba(26,43,60,0.12);
}}
.compare {{
  position: relative; width: 100%; cursor: ew-resize;
  user-select: none; touch-action: none;
}}
.compare img.base {{
  display: block; width: 100%; height: auto; vertical-align: top;
}}
.compare .clip {{
  position: absolute; top: 0; left: 0; height: 100%;
  width: 50%; overflow: hidden; pointer-events: none;
}}
.compare .clip img {{
  position: absolute; top: 0; left: 0;
  max-width: none; object-fit: fill;
}}
.compare .handle {{
  position: absolute; top: 0; bottom: 0; left: 50%;
  width: 3px; margin-left: -1.5px;
  background: #fff; box-shadow: 0 0 0 1px rgba(0,0,0,0.35);
  pointer-events: none; z-index: 5;
}}
.compare .knob {{
  position: absolute; top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  width: 42px; height: 42px; border-radius: 50%;
  background: #fff; border: 3px solid var(--rojo);
  box-shadow: 0 2px 10px rgba(0,0,0,0.35);
  display: flex; align-items: center; justify-content: center;
  font-size: 16px; color: var(--rojo); font-weight: 700;
}}
.label {{
  position: absolute; top: 10px; z-index: 4;
  padding: 4px 10px; border-radius: 4px;
  font-size: 0.78em; font-weight: 700; letter-spacing: 0.04em;
  color: #fff; background: rgba(47,95,143,0.88);
}}
.label.before {{ left: 10px; }}
.label.after {{ right: 10px; background: rgba(196,30,58,0.88); }}
.btn {{
  display: inline-block; margin: 6px 10px 0 0; padding: 9px 16px;
  background: var(--azul); color: #fff; text-decoration: none;
  border-radius: 6px; font-weight: 600; font-size: 0.9em;
}}
.btn.secondary {{ background: #5a6a7a; }}
.footer {{ font-size: 0.82em; color: #5a6a7a; margin-top: 10px; }}
</style>
</head>
<body>
<span class="tag">GFP Subnacional · Visor ATD · Imágenes del proceso H2</span>
<h1>Comparación antes / después (swipe)</h1>
<p><strong>{_html_escape(cod_reporte)}</strong></p>

<div class="meta">
  <span><strong>Antes:</strong> {_html_escape(fecha_antes)} · {_html_escape(sat_antes)}</span>
  <span><strong>Después:</strong> {_html_escape(fecha_despues)} · {_html_escape(sat_despues)}</span>
</div>

<div class="note">
  Arrastre la barra central (o deslice con el dedo) para comparar la imagen
  <strong>sin cambios</strong> (izquierda) con la imagen <strong>con el cambio detectado</strong> (derecha).
  Estas imágenes provienen del Visor Satelital (H2).
</div>

<div class="compare-wrap">
  <div class="compare" id="compare" aria-label="Comparador swipe antes despues">
    <img class="base" id="imgBefore" src="{_html_escape(src_a)}" alt="Imagen antes"/>
    <div class="clip" id="clip">
      <img id="imgAfter" src="{_html_escape(src_d)}" alt="Imagen despues"/>
    </div>
    <span class="label before">ANTES</span>
    <span class="label after">DESPUÉS</span>
    <div class="handle" id="handle"><div class="knob">&#8644;</div></div>
  </div>
</div>

{btn_eo}
<p class="footer">Archivos: {_html_escape(os.path.basename(ruta_img_antes))} ·
{_html_escape(os.path.basename(ruta_img_despues))}</p>

<script>
(function() {{
  var cmp = document.getElementById("compare");
  var clip = document.getElementById("clip");
  var handle = document.getElementById("handle");
  var imgBefore = document.getElementById("imgBefore");
  var imgAfter = document.getElementById("imgAfter");
  var dragging = false;

  function syncAfterSize() {{
    var w = cmp.clientWidth;
    var h = imgBefore.clientHeight;
    clip.style.height = h + "px";
    handle.style.height = h + "px";
    imgAfter.style.width = w + "px";
    imgAfter.style.height = h + "px";
  }}

  function setPos(pct) {{
    pct = Math.max(2, Math.min(98, pct));
    clip.style.width = pct + "%";
    handle.style.left = pct + "%";
  }}

  function posFromEvent(ev) {{
    var rect = cmp.getBoundingClientRect();
    var x = (ev.touches ? ev.touches[0].clientX : ev.clientX) - rect.left;
    return (x / rect.width) * 100;
  }}

  function start(ev) {{ dragging = true; ev.preventDefault(); setPos(posFromEvent(ev)); }}
  function move(ev) {{ if (!dragging) return; ev.preventDefault(); setPos(posFromEvent(ev)); }}
  function end() {{ dragging = false; }}

  cmp.addEventListener("mousedown", start);
  window.addEventListener("mousemove", move);
  window.addEventListener("mouseup", end);
  cmp.addEventListener("touchstart", start, {{passive:false}});
  window.addEventListener("touchmove", move, {{passive:false}});
  window.addEventListener("touchend", end);

  imgBefore.addEventListener("load", syncAfterSize);
  imgAfter.addEventListener("load", syncAfterSize);
  window.addEventListener("resize", syncAfterSize);
  if (imgBefore.complete) syncAfterSize();
  setPos(50);
}})();
</script>
</body>
</html>"""
    os.makedirs(os.path.dirname(os.path.abspath(ruta_html)), exist_ok=True)
    with open(ruta_html, "w", encoding="utf-8") as f:
        f.write(cuerpo)


def puede_generar_swipe(ruta_a: str | None, ruta_d: str | None) -> bool:
    from atd_imagenes_h3 import png_valido

    return bool(png_valido(ruta_a) and png_valido(ruta_d))

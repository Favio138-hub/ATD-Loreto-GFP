# Si ArcGIS Pro se cierra al generar el reporte

## Por que pasa (no es que tu ArcGIS este "malo")

ArcGIS Pro usa **un solo proceso** para la ventana y para Python. Cuando la toolbox carga **GeoPandas + pyogrio + matplotlib** a la vez que **arcpy**, en muchos equipos Windows el programa **se cierra sin mensaje** ("Application has stopped working").

En tus pruebas anteriores aparecio **pyogrio en**:

`C:\Users\...\AppData\Roaming\Python\Python311\`

Eso es una instalacion **aparte** del Python de ArcGIS Pro y es la causa mas frecuente de estos cierres.

**Antes funcionaba** porque el flujo era mas simple o no se mezclaban esas librerias en el mismo proceso. Los cambios de layout/margenes no cierran Pro; el cierre viene de **cargar demasiadas DLL de GIS en un solo proceso**.

## Que hacer AHORA (orden)

### 1. Diagnostico de entorno

Doble clic en:

`DIAGNOSTICO_ENTORNO.bat`

Copia el resultado si pide ayuda.

### 2. Generar PDF completo sin cerrar Pro (v7.6+)

1. Actualizar toolbox en Pro (clic derecho > Actualizar).
2. **1. Diagnostico Pre-Vuelo**
3. **2. Generar Reporte ATD** — una alerta con `OID:123|...`, **Modo estable desmarcado**
4. En el panel vera: `PDF completo en subproceso` — el mapa e imagenes se generan **fuera** de Pro.
5. El PDF sale en `pdfs\` con mapa (y Sentinel si marco GEE).

Si falla el subproceso, marque **Modo estable** (PDF sin mapa, solo tablas).

### 3. Reparar Python (si quieres volver a mapa/GEE dentro de Pro)

Abrir **Python Command Prompt** (menu Inicio > ArcGIS):

```bat
python -m pip uninstall pyogrio fiona geopandas -y
python -m pip install geopandas fiona --no-user
```

Cerrar ArcGIS Pro por completo y abrirlo de nuevo.

### 4. Version de ArcGIS Pro

No necesitas la ultima version. Lo importante es **3.x** con licencia activa. Si acabas de actualizar Pro y empezo el problema, prueba el paso 3.

## Que incluye el PDF "seguro"

- Encabezado, ficha, tablas, enlaces HTML, logos
- Sin mapa matplotlib ni imagenes Sentinel generadas en la toolbox
- Mismo layout que antes del cambio de margenes alineados

Para mapas e imagenes use la **Herramienta 2 Visor Satelital** y pegue capturas si hace falta.

## Contacto / soporte

Si tras el paso 2 Pro **sigue** cerrandose, envie captura del panel Geoprocessing **hasta la ultima linea visible** y el resultado de `DIAGNOSTICO_ENTORNO.bat`.

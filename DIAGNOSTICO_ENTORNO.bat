@echo off
chcp 65001 >nul
echo.
echo === Diagnostico ATD (Python de ArcGIS Pro) ===
echo.

set "PY1=C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe"
set "PY2=C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3-clone\python.exe"
set "SCRIPT=%~dp0toolbox\diagnosticar_entorno_atd.py"

if exist "%PY1%" ("%PY1%" "%SCRIPT%" & goto fin)
if exist "%PY2%" ("%PY2%" "%SCRIPT%" & goto fin)

echo No se encontro Python de ArcGIS Pro.
echo Abra Python Command Prompt y ejecute:
echo   python "%SCRIPT%"

:fin
pause

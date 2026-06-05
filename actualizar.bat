@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Actualizando capitulos y panel...
python generate_feed.py --config series.yaml --output-dir docs --state state.json
if errorlevel 1 (
  echo.
  echo ERROR: necesitas Python instalado y, una sola vez:  pip install -r requirements.txt
  pause
  exit /b 1
)
start "" "%~dp0docs\s-bc954f33df291bf7\dashboard.html"

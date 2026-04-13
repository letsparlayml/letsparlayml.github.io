@echo off
setlocal EnableExtensions

set "REPO=C:\Docs\letsparlayml.github.io"
set "MLB_DATA=C:\python\mlb_data"
set "LIVE_START_DATE="

if defined CONDA_PREFIX (
  set "PYTHON_EXE=%CONDA_PREFIX%\python.exe"
) else (
  set "PYTHON_EXE=python"
)

if not exist "%REPO%\tools\build_mlb_results_json.py" (
  echo [ERROR] Missing results builder:
  echo         %REPO%\tools\build_mlb_results_json.py
  exit /b 1
)

if not exist "%REPO%\tools\build_mlb_prop_results_json.py" (
  echo [ERROR] Missing prop results builder:
  echo         %REPO%\tools\build_mlb_prop_results_json.py
  exit /b 1
)

if not exist "%MLB_DATA%" (
  echo [ERROR] Missing MLB data dir:
  echo         %MLB_DATA%
  exit /b 1
)

echo ==========================================================
echo   PREVIEW MLB RESULTS TEST
echo   SITE REPO : %REPO%
echo   MLB DATA  : %MLB_DATA%
echo   START     : %LIVE_START_DATE%
echo   PYTHON    : %PYTHON_EXE%
echo ==========================================================

echo.
echo Running MLB game results builder in preview test mode...
if defined LIVE_START_DATE (
  "%PYTHON_EXE%" "%REPO%\tools\build_mlb_results_json.py" --website-repo "%REPO%" --mlb-data-dir "%MLB_DATA%" --enable --allow-missing-lines --live-start-date "%LIVE_START_DATE%"
) else (
  "%PYTHON_EXE%" "%REPO%\tools\build_mlb_results_json.py" --website-repo "%REPO%" --mlb-data-dir "%MLB_DATA%" --enable --allow-missing-lines
)
if errorlevel 1 (
  echo.
  echo [ERROR] MLB preview game results build failed.
  exit /b 1
)

echo.
echo Running MLB prop results builder in preview test mode...
"%PYTHON_EXE%" "%REPO%\tools\build_mlb_prop_results_json.py" --website-repo "%REPO%" --mlb-data-dir "%MLB_DATA%" --enable
if errorlevel 1 (
  echo.
  echo [ERROR] MLB preview prop results build failed.
  exit /b 1
)

echo.
echo [OK] MLB preview game + prop results updated.
echo Check:
echo   %REPO%\data\results.json
echo   %REPO%\data\results_history.json
echo   %REPO%\data\results_summary.json
echo   %REPO%\data\mlb_prop_results_history.json
echo   %REPO%\data\mlb_prop_results_pending.json
echo   %REPO%\data\mlb_prop_results_summary.json

echo.
echo Local preview server command:
echo   python -m http.server 8000

echo Then open:
echo   http://localhost:8000/#results

endlocal
exit /b 0

@echo off
setlocal EnableExtensions

set "ROOT=C:\python"
set "REPO=C:\Docs\letsparlayml.github.io"
set "MLB_OUT=%ROOT%\mlb_model_outputs"
set "TOOLS=%REPO%\tools"

set "PY=python"
if defined CONDA_PREFIX if exist "%CONDA_PREFIX%\python.exe" set "PY=%CONDA_PREFIX%\python.exe"

if /I "%REPO%"=="C:\python\letsparlayml.github.io" (
  echo [ABORT] REPO points to live repo. This preview bat will not run.
  exit /b 1
)

set "SYNC_SCRIPT="
if exist "%ROOT%\website_sync_v10_fixed.py" set "SYNC_SCRIPT=%ROOT%\website_sync_v10_fixed.py"
if not defined SYNC_SCRIPT if exist "%ROOT%\website_sync_v10.py" set "SYNC_SCRIPT=%ROOT%\website_sync_v10.py"
if not defined SYNC_SCRIPT goto :missing_sync

set "RESULTS_ROLLUP="
if exist "%ROOT%\results_rollup_fixed.py" set "RESULTS_ROLLUP=%ROOT%\results_rollup_fixed.py"
if not defined RESULTS_ROLLUP if exist "%ROOT%\results_rollup.py" set "RESULTS_ROLLUP=%ROOT%\results_rollup.py"

set "WORKBOOK="
for /f "delims=" %%I in ('dir /s /b /o:-d "%ROOT%\props_all_in_one_*.xlsx" 2^>nul') do (
  set "WORKBOOK=%%I"
  goto :got_workbook
)
:got_workbook

set "UPCOMING="
for /f "delims=" %%I in ('dir /s /b /o:-d "%ROOT%\player_props_upcoming_*.csv" 2^>nul') do (
  set "UPCOMING=%%I"
  goto :got_upcoming
)
:got_upcoming

set "PLAYER_DF="
for /f "delims=" %%I in ('dir /s /b "%ROOT%\*player_df*.parquet" 2^>nul') do (
  set "PLAYER_DF=%%I"
  goto :got_playerdf
)
:got_playerdf

set "ANALYZER_SCRIPT="
if exist "%ROOT%\nba_props_analyzer_v11_improved_fix3_simbinconnect_fix.py" set "ANALYZER_SCRIPT=%ROOT%\nba_props_analyzer_v11_improved_fix3_simbinconnect_fix.py"

echo [1/10] Settle MLB game results from prior board...
if exist "%TOOLS%\build_mlb_results_json.py" (
  "%PY%" "%TOOLS%\build_mlb_results_json.py" --website-repo "%REPO%" --mlb-data-dir "%ROOT%\mlb_data" --enable --allow-statsapi-fallback --allow-missing-lines
  if errorlevel 1 echo [WARN] MLB results build failed. Continuing.
)

echo [2/10] Settle MLB prop results queue...
if exist "%TOOLS%\build_mlb_prop_results_json.py" (
  "%PY%" "%TOOLS%\build_mlb_prop_results_json.py" --website-repo "%REPO%" --mlb-data-dir "%ROOT%\mlb_data" --enable
  if errorlevel 1 echo [WARN] MLB prop results build failed. Continuing.
)

echo [3/10] Run core site sync into preview repo...
"%PY%" "%SYNC_SCRIPT%" --website-repo "%REPO%"
if errorlevel 1 exit /b 1

echo [4/10] Refresh market lines after core sync...
"%PY%" "%TOOLS%\refresh_all_market_lines.py" --root "%ROOT%" --website-repo "%REPO%" --mlb-out "%MLB_OUT%"
if errorlevel 1 exit /b 1

echo [5/10] Rebuild results history, summary, and archive...
if defined RESULTS_ROLLUP (
  "%PY%" "%RESULTS_ROLLUP%" --website-repo "%REPO%"
  if errorlevel 1 exit /b 1
)

echo [6/10] Rebuild NBA props lab...
if defined WORKBOOK if exist "%REPO%\tools\build_nba_props_lab.py" "%PY%" "%REPO%\tools\build_nba_props_lab.py" --website-repo "%REPO%" --workbook "%WORKBOOK%" --games-json "%REPO%\data\games.json"

echo [7/10] Rebuild NBA props analyzer...
if defined WORKBOOK if defined UPCOMING if defined PLAYER_DF if defined ANALYZER_SCRIPT if exist "%REPO%\tools\build_nba_props_analyzer_json.py" "%PY%" "%REPO%\tools\build_nba_props_analyzer_json.py" --website-repo "%REPO%" --workbook "%WORKBOOK%" --games-json "%REPO%\data\games.json" --player-df "%PLAYER_DF%" --upcoming "%UPCOMING%" --analyzer-script "%ANALYZER_SCRIPT%" --injuries-json "%REPO%\data\nba_injuries.json"

echo [8/10] Build MLB games + props into preview repo...
"%PY%" "%TOOLS%\build_mlb_site_json.py" --website-repo "%REPO%" --mlb-output-dir "%MLB_OUT%"
if errorlevel 1 exit /b 1

echo [9/10] Build MLB props analyzer and seed pending props...
if exist "%TOOLS%\build_mlb_props_analyzer_json.py" "%PY%" "%TOOLS%\build_mlb_props_analyzer_json.py" --website-repo "%REPO%" --mlb-data-dir "%ROOT%\mlb_data" --mlb-output-dir "%MLB_OUT%"
if exist "%TOOLS%\build_mlb_prop_results_json.py" "%PY%" "%TOOLS%\build_mlb_prop_results_json.py" --website-repo "%REPO%" --mlb-data-dir "%ROOT%\mlb_data" --enable

echo [10/10] Refresh results/archive after MLB board write...
if defined RESULTS_ROLLUP "%PY%" "%RESULTS_ROLLUP%" --website-repo "%REPO%"

echo [DONE] Preview update finished.
exit /b 0

:missing_sync
echo [ABORT] website_sync_v10(.py) not found.
exit /b 1

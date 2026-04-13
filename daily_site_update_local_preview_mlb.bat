@echo off
setlocal EnableExtensions

set "ROOT=C:\python"
set "REPO=C:\python\letsparlayml.github.io"
set "MLB_OUT=%ROOT%\mlb_model_outputs"
set "TOOLS=%REPO%\tools"

set "PY=python"
if defined CONDA_PREFIX if exist "%CONDA_PREFIX%\python.exe" set "PY=%CONDA_PREFIX%\python.exe"

set "SYNC_SCRIPT="
if exist "%ROOT%\website_sync_v10_fixed.py" set "SYNC_SCRIPT=%ROOT%\website_sync_v10_fixed.py"
if not defined SYNC_SCRIPT if exist "%ROOT%\website_sync_v10.py" set "SYNC_SCRIPT=%ROOT%\website_sync_v10.py"
if not defined SYNC_SCRIPT goto :missing_sync

set "RESULTS_ROLLUP="
if exist "%ROOT%\results_rollup_fixed.py" set "RESULTS_ROLLUP=%ROOT%\results_rollup_fixed.py"
if not defined RESULTS_ROLLUP if exist "%ROOT%\results_rollup.py" set "RESULTS_ROLLUP=%ROOT%\results_rollup.py"

echo [1/7] Settle MLB results and prop queue...
if exist "%TOOLS%\build_mlb_results_json.py" "%PY%" "%TOOLS%\build_mlb_results_json.py" --website-repo "%REPO%" --mlb-data-dir "%ROOT%\mlb_data" --enable --allow-statsapi-fallback --allow-missing-lines
if exist "%TOOLS%\build_mlb_prop_results_json.py" "%PY%" "%TOOLS%\build_mlb_prop_results_json.py" --website-repo "%REPO%" --mlb-data-dir "%ROOT%\mlb_data" --enable

echo [2/7] Run core site sync...
"%PY%" "%SYNC_SCRIPT%" --website-repo "%REPO%"
if errorlevel 1 exit /b 1

echo [3/7] Refresh market lines...
"%PY%" "%TOOLS%\refresh_all_market_lines.py" --root "%ROOT%" --website-repo "%REPO%" --mlb-out "%MLB_OUT%"
if errorlevel 1 exit /b 1

echo [4/7] Rebuild results rollups...
if defined RESULTS_ROLLUP "%PY%" "%RESULTS_ROLLUP%" --website-repo "%REPO%"

echo [5/7] Build MLB games + props...
"%PY%" "%TOOLS%\build_mlb_site_json.py" --website-repo "%REPO%" --mlb-output-dir "%MLB_OUT%"
if errorlevel 1 exit /b 1

echo [6/7] Build MLB analyzer / seed pending props...
if exist "%TOOLS%\build_mlb_props_analyzer_json.py" "%PY%" "%TOOLS%\build_mlb_props_analyzer_json.py" --website-repo "%REPO%" --mlb-data-dir "%ROOT%\mlb_data" --mlb-output-dir "%MLB_OUT%"
if exist "%TOOLS%\build_mlb_prop_results_json.py" "%PY%" "%TOOLS%\build_mlb_prop_results_json.py" --website-repo "%REPO%" --mlb-data-dir "%ROOT%\mlb_data" --enable

echo [7/7] Refresh results/archive after MLB board write...
if defined RESULTS_ROLLUP "%PY%" "%RESULTS_ROLLUP%" --website-repo "%REPO%"

echo [DONE] Local repo update finished.
exit /b 0

:missing_sync
echo [ABORT] website_sync_v10(.py) not found.
exit /b 1

@echo off
setlocal
set REPO=%~dp0
if "%REPO:~-1%"=="\" set REPO=%REPO:~0,-1%
set PY=C:\Users\andre\miniconda3\python.exe
set ROOT=C:\python

echo [1/7] Safe MLB results step...
%PY% "%REPO%\tools\build_mlb_results_json.py" --website-repo "%REPO%"
if errorlevel 1 goto :fail

echo [2/7] Core site sync into preview repo...
%PY% "%ROOT%\website_sync_v10_fixed.py" --website-repo "%REPO%"
if errorlevel 1 goto :fail

echo [3/7] Build pitcher averages JSON...
%PY% "%REPO%\tools\build_mlb_pitcher_averages_json.py" --mlb-output-dir "%ROOT%\mlb_model_outputs" --out "%REPO%\data\mlb_pitcher_averages.json"
if errorlevel 1 goto :fail

echo [4/7] Build MLB site JSON...
%PY% "%REPO%\tools\build_mlb_site_json.py" --website-repo "%REPO%"
if errorlevel 1 goto :fail

echo [5/7] Build MLB analyzer JSON...
%PY% "%REPO%\tools\build_mlb_props_analyzer_json.py" --website-repo "%REPO%"
if errorlevel 1 goto :fail

echo [6/7] Refresh results rollups without API hits...
%PY% "%ROOT%\results_rollup_fixed.py" --website-repo "%REPO%"
if errorlevel 1 goto :fail

echo [7/7] Done.
exit /b 0

:fail
echo Failed.
exit /b 1

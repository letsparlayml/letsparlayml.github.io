@echo off
setlocal EnableExtensions EnableDelayedExpansion

set ROOT=C:\python
set REPO=C:\python\letsparlayml.github.io
set MLB_OUTPUT_DIR=C:\python\mlb_model_outputs
set START_SERVER=0
if /I "%~1"=="serve" set START_SERVER=1

if exist "%ROOT%\website_sync_v10_fixed.py" (
  set SYNC_SCRIPT=%ROOT%\website_sync_v10_fixed.py
) else (
  set SYNC_SCRIPT=%ROOT%\website_sync_v10.py
)

if exist "%ROOT%\update_market_lines_v2_fixed.py" (
  set UPDATE_LINES=%ROOT%\update_market_lines_v2_fixed.py
) else (
  set UPDATE_LINES=%ROOT%\update_market_lines_v2.py
)

if exist "%ROOT%\results_rollup_fixed.py" (
  set RESULTS_ROLLUP=%ROOT%\results_rollup_fixed.py
) else (
  set RESULTS_ROLLUP=%ROOT%\results_rollup.py
)

for /f "delims=" %%I in ('dir /s /b /o:-d "%ROOT%\props_all_in_one_*.xlsx" 2^>nul') do (
  set WORKBOOK=%%I
  goto :got_workbook
)
:got_workbook

for /f "delims=" %%I in ('dir /s /b /o:-d "%ROOT%\player_props_upcoming_*.csv" 2^>nul') do (
  set UPCOMING=%%I
  goto :got_upcoming
)
:got_upcoming

for /f "delims=" %%I in ('dir /s /b "%ROOT%\*player_df*.parquet" 2^>nul') do (
  set PLAYER_DF=%%I
  goto :got_playerdf
)
:got_playerdf

if exist "%ROOT%\nba_props_analyzer_v11_improved_fix3_simbinconnect_fix.py" (
  set ANALYZER_SCRIPT=%ROOT%\nba_props_analyzer_v11_improved_fix3_simbinconnect_fix.py
)

echo [1/10] Build NBA injuries JSON (if workbook exists)...
if exist "%REPO%\tools\build_nba_injuries_json.py" if exist "%REPO%\data\nba_injuries.xlsx" (
  python "%REPO%\tools\build_nba_injuries_json.py" --website-repo "%REPO%" || exit /b 1
)

echo [2/10] Run core site sync...
python "%SYNC_SCRIPT%" || exit /b 1

echo [3/10] Refresh market lines for current target date...
python "%UPDATE_LINES%" --website-repo "%REPO%" --cbb-dir "%ROOT%\cbb_data" || exit /b 1

echo [4/10] Apply manual NHL lines when available...
if exist "%ROOT%\nhl_manual_lines_adapter.py" if exist "%REPO%\data\manual_nhl_lines.csv" (
  python "%ROOT%\nhl_manual_lines_adapter.py" --website-repo "%REPO%" || exit /b 1
)

echo [5/10] Rebuild results history and summary...
python "%RESULTS_ROLLUP%" --website-repo "%REPO%" || exit /b 1

echo [6/10] Rebuild nba_props_lab.json...
if defined WORKBOOK (
  python "%REPO%\tools\build_nba_props_lab.py" --website-repo "%REPO%" --workbook "%WORKBOOK%" --games-json "%REPO%\data\games.json" || exit /b 1
) else (
  echo WARNING: props_all_in_one workbook not found. Skipping nba_props_lab build.
)

echo [7/10] Rebuild analyzer index + detail files...
if defined WORKBOOK if defined PLAYER_DF if defined UPCOMING if defined ANALYZER_SCRIPT (
  python "%REPO%\tools\build_nba_props_analyzer_json.py" --website-repo "%REPO%" --workbook "%WORKBOOK%" --games-json "%REPO%\data\games.json" --player-df "%PLAYER_DF%" --upcoming "%UPCOMING%" --analyzer-script "%ANALYZER_SCRIPT%" --injuries-json "%REPO%\data\nba_injuries.json" || exit /b 1
) else (
  echo WARNING: missing one or more NBA analyzer inputs. Skipping analyzer rebuild.
)

echo [8/10] Build MLB local-preview JSON files when available...
if exist "%REPO%\tools\build_mlb_site_json.py" (
  python "%REPO%\tools\build_mlb_site_json.py" --website-repo "%REPO%" --mlb-output-dir "%MLB_OUTPUT_DIR%" || exit /b 1
) else (
  echo WARNING: build_mlb_site_json.py not found. Skipping MLB preview build.
)

echo [9/10] Local preview update finished. No git pull, commit, or push was performed.

echo [10/10] Repo ready for local preview.
if "%START_SERVER%"=="1" (
  echo Starting local server at http://localhost:8000 ...
  start "LetsParlay Local Preview" cmd /k "cd /d "%REPO%" && python -m http.server 8000"
) else (
  echo Run this from the repo folder to preview locally:
  echo   python -m http.server 8000
  echo Then open http://localhost:8000
)

echo SUCCESS: Local preview workflow completed.
endlocal

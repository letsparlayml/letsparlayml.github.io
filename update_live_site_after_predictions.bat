@echo off
setlocal EnableExtensions

set "ROOT=C:\python"
set "REPO=C:\python\letsparlayml.github.io"
set "TOOLS=%REPO%\tools"
set "MLB_OUT=%ROOT%\mlb_model_outputs"
set "NBA_MODELS=%ROOT%\data_nba\models_v1"
set "NBA_ANALYZER_BUILD=%TOOLS%\build_nba_props_analyzer_json_builtin_fix.py"
if not exist "%NBA_ANALYZER_BUILD%" set "NBA_ANALYZER_BUILD=%TOOLS%\build_nba_props_analyzer_json.py"

REM Prefer the patched root-level scripts when present, but fall back to tools\.
REM The MLB props analyzer builder must include the historical-context enrichment.
REM The player-day profile builder must run after the analyzer JSON so the multi-prop
REM board, row-level similarity colors, and readable summaries refresh every morning.
set "MLB_PROPS_ANALYZER_BUILD=%REPO%\build_mlb_props_analyzer_json.py"
if not exist "%MLB_PROPS_ANALYZER_BUILD%" set "MLB_PROPS_ANALYZER_BUILD=%TOOLS%\build_mlb_props_analyzer_json.py"

set "MLB_PLAYER_PROFILES_BUILD=%REPO%\build_mlb_player_day_profiles.py"
if not exist "%MLB_PLAYER_PROFILES_BUILD%" set "MLB_PLAYER_PROFILES_BUILD=%TOOLS%\build_mlb_player_day_profiles.py"

set "PY=C:\Users\andre\miniconda3\python.exe"
if defined CONDA_PREFIX if exist "%CONDA_PREFIX%\python.exe" set "PY=%CONDA_PREFIX%\python.exe"

set "SYNC_SCRIPT="
if exist "%ROOT%\website_sync_v10_fixed.py" set "SYNC_SCRIPT=%ROOT%\website_sync_v10_fixed.py"
if not defined SYNC_SCRIPT if exist "%ROOT%\website_sync_v10.py" set "SYNC_SCRIPT=%ROOT%\website_sync_v10.py"

if not defined SYNC_SCRIPT (
  echo ERROR: website_sync_v10_fixed.py or website_sync_v10.py not found in %ROOT%
  exit /b 1
)

set "ROLLUP_SCRIPT=%ROOT%\results_rollup_fixed.py"
if not exist "%ROLLUP_SCRIPT%" (
  echo ERROR: %ROLLUP_SCRIPT% not found.
  exit /b 1
)

if not exist "%MLB_PROPS_ANALYZER_BUILD%" (
  echo ERROR: MLB props analyzer builder not found.
  echo Checked:
  echo   %REPO%\build_mlb_props_analyzer_json.py
  echo   %TOOLS%\build_mlb_props_analyzer_json.py
  exit /b 1
)

if not exist "%MLB_PLAYER_PROFILES_BUILD%" (
  echo ERROR: MLB player-day profile builder not found.
  echo Checked:
  echo   %REPO%\build_mlb_player_day_profiles.py
  echo   %TOOLS%\build_mlb_player_day_profiles.py
  exit /b 1
)

echo ==========================================
echo UPDATE LIVE SITE AFTER PREDICTIONS
echo ROOT                  : %ROOT%
echo REPO                  : %REPO%
echo PYTHON                : %PY%
echo MLB PROPS BUILD       : %MLB_PROPS_ANALYZER_BUILD%
echo MLB PLAYER PROFILES   : %MLB_PLAYER_PROFILES_BUILD%
echo ==========================================

pushd "%REPO%"

echo.
echo [1/17] Rebuild NBA injuries JSON...
if exist "%REPO%\data\nba_injuries.xlsx" (
  "%PY%" "%TOOLS%\build_nba_injuries_json.py" --website-repo "%REPO%"
) else if exist "%REPO%\data\nba_injuries.csv" (
  "%PY%" "%TOOLS%\build_nba_injuries_json.py" --website-repo "%REPO%" --input "%REPO%\data\nba_injuries.csv"
) else (
  echo No nba injuries file found. Skipping.
)
if errorlevel 1 goto :fail

echo.
echo [2/17] Settle MLB game results from prior board...
"%PY%" "%TOOLS%\build_mlb_results_json.py" --website-repo "%REPO%" --mlb-data-dir "%ROOT%\mlb_data" --enable --allow-statsapi-fallback --allow-missing-lines
if errorlevel 1 goto :fail

echo.
echo [3/17] Settle MLB prop results / pending queue...
"%PY%" "%TOOLS%\build_mlb_prop_results_json.py" --website-repo "%REPO%" --mlb-data-dir "%ROOT%\mlb_data" --enable
if errorlevel 1 goto :fail

echo.
echo [4/17] Run core site sync...
"%PY%" "%SYNC_SCRIPT%" --website-repo "%REPO%"
if errorlevel 1 goto :fail

echo.
echo [5/17] Build NBA props lab JSON...
"%PY%" "%TOOLS%\build_nba_props_lab.py" --website-repo "%REPO%"
if errorlevel 1 goto :fail

echo.
echo [6/17] Build NBA props analyzer JSON...
"%PY%" "%NBA_ANALYZER_BUILD%" --website-repo "%REPO%" --player-df "%NBA_MODELS%\player_df.parquet"
if errorlevel 1 goto :fail

echo.
echo [7/17] Refresh market lines (NBA/NHL/MLB API only)...
"%PY%" "%TOOLS%\refresh_all_market_lines.py" --root "%ROOT%" --website-repo "%REPO%"
if errorlevel 1 goto :fail

echo.
echo [8/17] Refresh results rollup and line archive...
"%PY%" "%ROLLUP_SCRIPT%" --website-repo "%REPO%"
if errorlevel 1 goto :fail

echo.
echo [9/17] Build MLB site JSON...
"%PY%" "%TOOLS%\build_mlb_site_json.py" --website-repo "%REPO%"
if errorlevel 1 goto :fail

echo.
echo [10/17] Build MLB pitcher averages JSON...
"%PY%" "%TOOLS%\build_mlb_pitcher_averages_json.py" --out "%REPO%\data\mlb_pitcher_averages.json"
if errorlevel 1 goto :fail

echo.
echo [11/17] Build MLB props analyzer JSON with historical matchup enrichment...
"%PY%" "%MLB_PROPS_ANALYZER_BUILD%" --website-repo "%REPO%" --mlb-data-dir "%ROOT%\mlb_data"
if errorlevel 1 goto :fail

echo.
echo [12/17] Build MLB player-day profiles for multi-prop view and Similarity v2...
"%PY%" "%MLB_PLAYER_PROFILES_BUILD%" --data-dir "%REPO%\data" --all-dates
if errorlevel 1 goto :fail

echo.
echo [13/17] Re-settle MLB prop results after MLB refresh...
"%PY%" "%TOOLS%\build_mlb_prop_results_json.py" --website-repo "%REPO%" --mlb-data-dir "%ROOT%\mlb_data" --enable
if errorlevel 1 goto :fail

echo.
echo [14/17] Refresh results rollup again after MLB board write...
"%PY%" "%ROLLUP_SCRIPT%" --website-repo "%REPO%"
if errorlevel 1 goto :fail

echo.
echo [15/17] Build compact homepage top picks / parlay pool...
"%PY%" "%TOOLS%\build_home_top_picks_json.py"
if errorlevel 1 goto :fail

echo.
echo [16/17] Build pitcher first-inning lookup...
"%PY%" "%TOOLS%\build_pitcher_first_inning_lookup.py" --website-repo "%REPO%" --mlb-data-dir "%ROOT%\mlb_data"
if errorlevel 1 goto :fail

echo.
echo [17/17] Build MLB Game Intelligence reports...
"%PY%" "%TOOLS%\build_game_intelligence.py" --website-repo "%REPO%" --mlb-data-dir "%ROOT%\mlb_data"
if errorlevel 1 goto :fail

echo.
echo Commit and push if changed...
git add -A
git diff --cached --quiet
if errorlevel 1 (
  git commit -m "Daily live site update"
  git push
) else (
  echo No changes to commit.
)

popd
echo.
echo Daily live site update complete.
exit /b 0

:fail
echo.
echo FAILED.
popd
exit /b 1

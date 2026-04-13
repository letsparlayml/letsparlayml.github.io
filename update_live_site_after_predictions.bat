@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "REPO=C:\python\letsparlayml.github.io"
set "PYTHON_EXE=C:\Users\andre\miniconda3\python.exe"

echo ==========================================
echo LIVE SITE UPDATE AFTER PREDICTIONS
echo REPO   : %REPO%
echo PYTHON : %PYTHON_EXE%
echo ==========================================

if not exist "%REPO%\index.html" (
  echo ERROR: Repo not found: %REPO%
  exit /b 1
)
if not exist "%REPO%\daily_site_update_local_preview_mlb.bat" (
  echo ERROR: Missing update bat: %REPO%\daily_site_update_local_preview_mlb.bat
  exit /b 1
)

pushd "%REPO%"

echo.
echo [1/4] Rebuild NBA injuries JSON...
if exist "%REPO%\data\nba_injuries.xlsx" (
  "%PYTHON_EXE%" "%REPO%\tools\build_nba_injuries_json.py" --website-repo "%REPO%"
) else if exist "%REPO%\data\nba_injuries.csv" (
  "%PYTHON_EXE%" "%REPO%\tools\build_nba_injuries_json.py" --website-repo "%REPO%" --input "%REPO%\data\nba_injuries.csv"
) else (
  echo No nba_injuries.xlsx or nba_injuries.csv found. Skipping injuries rebuild.
)

echo.
echo [2/4] Run the full site update bat...
call "%REPO%\daily_site_update_local_preview_mlb.bat"
if errorlevel 1 (
  echo ERROR: daily_site_update_local_preview_mlb.bat failed.
  popd
  exit /b 1
)

echo.
echo [3/4] Commit changes...
git add -A
git diff --cached --quiet
if errorlevel 1 (
  git commit -m "Daily live site update"
) else (
  echo No changes to commit.
)

echo.
echo [4/4] Push...
git push

popd
echo.
echo Daily live update complete.
exit /b 0

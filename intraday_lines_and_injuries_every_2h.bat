@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "REPO=C:\python\letsparlayml.github.io"
set "PYTHON_EXE=C:\Users\andre\miniconda3\python.exe"

echo ==========================================
echo INTRADAY LINES + INJURIES REFRESH
echo REPO   : %REPO%
echo PYTHON : %PYTHON_EXE%
echo ==========================================

if not exist "%REPO%\index.html" (
  echo ERROR: Repo not found: %REPO%
  exit /b 1
)
if "%ODDS_API_KEY%"=="" (
  echo ERROR: ODDS_API_KEY is not set.
  exit /b 1
)
if not exist "%REPO%\tools\fetch_market_lines_the_odds_api.py" (
  echo ERROR: Missing %REPO%\tools\fetch_market_lines_the_odds_api.py
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
echo [2/4] Refresh API market lines...
"%PYTHON_EXE%" "%REPO%\tools\fetch_market_lines_the_odds_api.py" --api-key "%ODDS_API_KEY%" --website-repo "%REPO%"
if errorlevel 1 (
  echo ERROR: fetch_market_lines_the_odds_api.py failed.
  popd
  exit /b 1
)

echo.
echo [3/4] Commit changes if needed...
git add -A
git diff --cached --quiet
if errorlevel 1 (
  git commit -m "Intraday lines and injuries refresh"
) else (
  echo No changes to commit.
)

echo.
echo [4/4] Push...
git push

popd
echo.
echo Intraday refresh complete.
exit /b 0

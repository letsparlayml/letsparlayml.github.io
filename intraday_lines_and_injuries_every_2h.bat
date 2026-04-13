@echo off
setlocal EnableExtensions
set "ROOT=C:\python"
set "REPO=C:\python\letsparlayml.github.io"
set "TOOLS=%REPO%\tools"
set "PY=C:\Users\andre\miniconda3\python.exe"
if defined CONDA_PREFIX if exist "%CONDA_PREFIX%\python.exe" set "PY=%CONDA_PREFIX%\python.exe"
echo ==========================================
echo INTRADAY LINES + INJURIES REFRESH
echo ROOT   : %ROOT%
echo REPO   : %REPO%
echo PYTHON : %PY%
echo ==========================================
if "%ODDS_API_KEY%"=="" (
  echo ERROR: ODDS_API_KEY is not set.
  exit /b 1
)
pushd "%REPO%"
echo.
echo [1/3] Rebuild NBA injuries JSON...
if exist "%REPO%\data\nba_injuries.xlsx" (
  "%PY%" "%TOOLS%\build_nba_injuries_json.py" --website-repo "%REPO%"
) else if exist "%REPO%\data\nba_injuries.csv" (
  "%PY%" "%TOOLS%\build_nba_injuries_json.py" --website-repo "%REPO%" --input "%REPO%\data\nba_injuries.csv"
) else (
  echo No nba injuries file found. Skipping.
)
if errorlevel 1 goto :fail
echo.
echo [2/3] Refresh NBA/NHL/MLB API market lines...
"%PY%" "%TOOLS%\refresh_all_market_lines.py" --root "%ROOT%" --website-repo "%REPO%"
if errorlevel 1 goto :fail
echo.
echo [3/3] Commit and push if changed...
git add -A
git diff --cached --quiet
if errorlevel 1 (
  git commit -m "Intraday lines and injuries refresh"
  git push
) else (
  echo No changes to commit.
)
popd
echo.
echo Intraday refresh complete.
exit /b 0
:fail
echo.
echo FAILED.
popd
exit /b 1

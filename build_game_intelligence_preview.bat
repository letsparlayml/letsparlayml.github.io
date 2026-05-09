@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "REPO=%~dp0"
set "REPO=%REPO:~0,-1%"
set "PY=C:\Users\andre\miniconda3\python.exe"
if not exist "%PY%" set "PY=python"
set "MLB_DATA=C:\python\mlb_data"

echo ==========================================
echo BUILD GAME INTELLIGENCE - PREVIEW
echo REPO     : %REPO%
echo MLB DATA : %MLB_DATA%
echo PYTHON   : %PY%
echo ==========================================

"%PY%" "%REPO%\tools\build_pitcher_first_inning_lookup.py" --website-repo "%REPO%" --mlb-data-dir "%MLB_DATA%"
if errorlevel 1 (
  echo.
  echo FAILED building pitcher first-inning lookup.
  exit /b 1
)

"%PY%" "%REPO%\tools\build_game_intelligence.py" --website-repo "%REPO%" --mlb-data-dir "%MLB_DATA%"
if errorlevel 1 (
  echo.
  echo FAILED building Game Intelligence.
  exit /b 1
)

echo.
echo Game Intelligence build completed.
exit /b 0


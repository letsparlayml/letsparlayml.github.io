@echo off
setlocal
set REPO=%~dp0
if "%REPO:~-1%"=="\" set REPO=%REPO:~0,-1%
set PY=C:\Users\andre\miniconda3\python.exe

echo [1/2] Build NBA injuries JSON...
%PY% "%REPO%\tools\build_nba_injuries_json.py" --website-repo "%REPO%"
if errorlevel 1 exit /b %errorlevel%

echo [2/2] Run preview rebuild without API hits...
call "%REPO%\daily_site_update_preview_no_api_work.bat"
endlocal

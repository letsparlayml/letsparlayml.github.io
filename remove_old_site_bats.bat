@echo off
setlocal EnableExtensions

set "REPO=C:\python\letsparlayml.github.io"

echo Removing old preview/test bat files from %REPO% ...

del "%REPO%\daily_site_update_local_preview_mlb.bat" 2>nul
del "%REPO%\daily_site_update_preview_docs_auto_lines_fixed3.bat" 2>nul
del "%REPO%\daily_site_update_preview_no_api_work.bat" 2>nul
del "%REPO%\rebuild_injuries_then_preview_no_api.bat" 2>nul
del "%REPO%\run_mlb_results_preview_test.bat" 2>nul
del "%REPO%\daily_live_update_wrapper.bat" 2>nul
del "%REPO%\deploy_preview_to_live_and_push.bat" 2>nul
del "%REPO%\intraday_refresh_every_2h.bat" 2>nul
del "%REPO%\go_live_from_preview_and_push.bat" 2>nul

echo Done.

@echo off
title Neighbourhood Builder - 127.0.0.1:8196
REM Starts the "type a sentence, get a neighbourhood" page on http://127.0.0.1:8196/ and opens it
REM in work Chrome. Leave this window open while you use the page; closing it stops the service.
REM Needs: Python 3, the UPBGE 0.50 portable install, and Ollama running (falls back to word rules without it).
cd /d "%~dp0"
set "OPENER=C:\Users\JohnM\Artificial Intelligence\Projects\CEO-of-My-Life-Inc\OPEN-IN-WORK-CHROME.bat"
where py >nul 2>&1
if not errorlevel 1 goto usepy
where python >nul 2>&1
if not errorlevel 1 goto usepython
echo Python was not found. Looked for: py (Windows launcher) and python on PATH.
pause
exit /b 1

:usepy
if exist "%OPENER%" start "" /min "%OPENER%" "http://127.0.0.1:8196/" 4
if not exist "%OPENER%" echo Open http://127.0.0.1:8196/ in your browser.
py -3 "%~dp0neighbourhood-service.py"
goto done

:usepython
if exist "%OPENER%" start "" /min "%OPENER%" "http://127.0.0.1:8196/" 4
if not exist "%OPENER%" echo Open http://127.0.0.1:8196/ in your browser.
python "%~dp0neighbourhood-service.py"
goto done

:done
echo.
echo The Neighbourhood Builder has stopped. Run this again to restart it.
pause
exit /b 0

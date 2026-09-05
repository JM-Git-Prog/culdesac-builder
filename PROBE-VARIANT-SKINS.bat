@echo off
setlocal
title Probe: reproduce the exploded kit props (hydrant caps, trash-can handles) in headless UPBGE

REM PROBE-VARIANT-SKINS.bat  -  2026-09-03
REM Rebuilds job 20260903-155702 (Mr. John's Neighborhood v1, the one that is broken today) inside
REM headless UPBGE and inspects the scene WITHOUT exporting - no world folder is touched, nothing
REM is written except jobs\20260903-155702\probe-variant-skins.txt. Takes about a minute.
REM UPBGE is detected the same way neighbourhood-service.py detects it, never hard-coded blindly.
REM Batch rules: no call :label, no parenthesised blocks, every exit prints and pauses,
REM no redirect characters except intended file redirects.

set "HERE=%~dp0"
set "HERE=%HERE:~0,-1%"
set "JOB=%HERE%\jobs\20260903-155702"
if not "%~1"=="" set "JOB=%~1"
set "C1=C:\Users\JohnM\Artificial Intelligence\UPBGE\upbge-0.50-windows-x64\blender.exe"
set "C2=%HERE%\..\..\01 Engines\UPBGE 0.50\blender.exe"
set "BL="
if exist "%C1%" set "BL=%C1%"
if not defined BL if exist "%C2%" set "BL=%C2%"
if not defined BL goto noblender
if not exist "%JOB%\brief.json" goto nojob

echo.
echo  ============================================================
echo   PROBE VARIANT SKINS  -  reproduce, touch nothing
echo   UPBGE: %BL%
echo   Job:   %JOB%
echo  ============================================================
echo.
"%BL%" --background --factory-startup -noaudio --python "%HERE%\probe-variant-skins.py" -- "%JOB%"
if errorlevel 1 goto failed
if not exist "%JOB%\probe-variant-skins.txt" goto noreport

echo.
echo  ------------------------------------------------------------
echo   Report: %JOB%\probe-variant-skins.txt
echo   Look for the RESULT line above: REPRODUCED means the defects are in the
echo   build itself (before any export), CLEAN means this brief builds clean.
echo  ------------------------------------------------------------
echo.
pause
exit /b 0

:noreport
echo.
echo   RESULT: FAILED - UPBGE ran but wrote no report. Read the lines above; the layer
echo   that failed is probe-variant-skins.py inside UPBGE.
echo.
pause
exit /b 1

:failed
echo.
echo   RESULT: FAILED - UPBGE exited with an error (see above). Layer: headless UPBGE.
echo.
pause
exit /b 1

:nojob
echo.
echo   STOP: no brief.json in %JOB%
echo.
pause
exit /b 1

:noblender
echo.
echo   STOP: UPBGE not found. Looked in:
echo     1. %C1%
echo     2. %C2%
echo.
pause
exit /b 1

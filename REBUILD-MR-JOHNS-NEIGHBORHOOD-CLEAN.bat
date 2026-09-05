@echo off
setlocal
title Rebuild Mr. John's Neighborhood as a new clean version (same brief, fixed builder)

REM REBUILD-MR-JOHNS-NEIGHBORHOOD-CLEAN.bat  -  2026-09-03  (John's call: "rebuild the live one now")
REM Rebuilds the live place from the SAME brief that made version 1 (job 20260903-155702), through
REM run-brief.py --slug mr-johns-neighborhood, so it lands as the NEXT version of that place.
REM Earlier versions stay on disk untouched (run-brief refuses to overwrite). The viewer loads the
REM highest version by default, so opening /mr-johns-neighborhood with no ?v shows the new one.
REM Then the GLB is read back and checked: one skin per prop, bodies present.
REM Batch rules: no call :label, no parenthesised blocks, every exit prints and pauses,
REM no redirect characters except intended file redirects.

set "HERE=%~dp0"
set "HERE=%HERE:~0,-1%"
set "SRC=%HERE%\jobs\20260903-155702"
set "JOB=%HERE%\jobs\rebuild-mr-johns-clean"
set "PLACE=C:\Users\JohnM\Artificial Intelligence\Projects\CEO-of-My-Life-Inc\CEO-3D-World\worlds\mr-johns-neighborhood\output\world"
set "C1=C:\Users\JohnM\Artificial Intelligence\UPBGE\upbge-0.50-windows-x64\blender.exe"
set "C2=%HERE%\..\..\01 Engines\UPBGE 0.50\blender.exe"
set "BL="
if exist "%C1%" set "BL=%C1%"
if not defined BL if exist "%C2%" set "BL=%C2%"
if not defined BL goto noblender
if not exist "%SRC%\brief.json" goto nosrc
if not exist "%PLACE%" goto noplace
if exist "%JOB%\status.json" goto already

echo.
echo  ============================================================
echo   REBUILD Mr. John's Neighborhood  -  new clean version
echo   UPBGE: %BL%
echo   Place: %PLACE%
echo  ============================================================
echo.
echo  [1/2] Building (about 2 minutes)...
mkdir "%JOB%"
copy /Y "%SRC%\brief.json" "%JOB%\brief.json"
"%BL%" --background --factory-startup -noaudio --python "%HERE%\run-brief.py" -- "%JOB%" --slug mr-johns-neighborhood
if errorlevel 1 goto buildfail

echo.
echo  [2/2] Checking the newest version's GLB - one skin per prop, bodies present
"%BL%" --background --factory-startup -noaudio --python "%HERE%\check-world-glb.py" -- "%PLACE%"
if errorlevel 1 goto glbdirty

echo.
echo  ------------------------------------------------------------
echo   RESULT: OK - Mr. John's Neighborhood has a new clean version.
echo   See it: open http://localhost:5173/mr-johns-neighborhood (no ?v) or refresh
echo   V17's pane. Version 1 (the exploded one) is still on disk, untouched.
echo   Log: %JOB%\build-log.txt
echo  ------------------------------------------------------------
echo.
pause
exit /b 0

:glbdirty
echo.
echo   RESULT: FAILED - the new version's GLB still shows a defect (see the DEFECT lines).
echo   Layer: the builder fix did not cover this case. Version 1 is untouched.
echo.
pause
exit /b 1

:buildfail
echo.
echo   RESULT: FAILED - headless UPBGE exited with an error. Read %JOB%\build-log.txt
echo   and the lines above. Layer: run-brief.py inside UPBGE. Nothing replaced.
echo.
pause
exit /b 1

:already
echo.
echo   STOP: %JOB% already holds a run. Delete or rename that folder to rebuild again.
echo.
pause
exit /b 1

:noplace
echo.
echo   STOP: the place folder was not found: %PLACE%
echo.
pause
exit /b 1

:nosrc
echo.
echo   STOP: the version-1 brief is missing: %SRC%\brief.json
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

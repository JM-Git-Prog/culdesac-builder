@echo off
setlocal
title After the fix: rebuild the broken brief and prove the GLB has one skin per prop

REM REBUILD-AND-CHECK-VARIANT-SKINS.bat  -  2026-09-03
REM Proves the two fixes on the SAME brief that was broken (job 20260903-155702, Mr. John's
REM Neighborhood v1 - the seed is the brief's checksum, so the same skins get picked again):
REM   1. probe the built scene in headless UPBGE (expect RESULT: CLEAN)
REM   2. run the real production path (run-brief.py) into a DISPOSABLE place called
REM      variant-skin-check - the live neighbourhood is not touched; delete that folder any time
REM   3. read the exported GLB back and check every prop: one skin, body present
REM Batch rules: no call :label, no parenthesised blocks, every exit prints and pauses,
REM no redirect characters except intended file redirects.

set "HERE=%~dp0"
set "HERE=%HERE:~0,-1%"
set "SRC=%HERE%\jobs\20260903-155702"
set "JOB=%HERE%\jobs\variant-skin-check"
set "WORLDS=C:\Users\JohnM\Artificial Intelligence\Projects\CEO-of-My-Life-Inc\CEO-3D-World\worlds"
set "PLACE=%WORLDS%\variant-skin-check\output\world"
set "GLB=%PLACE%\0-world.glb"
set "C1=C:\Users\JohnM\Artificial Intelligence\UPBGE\upbge-0.50-windows-x64\blender.exe"
set "C2=%HERE%\..\..\01 Engines\UPBGE 0.50\blender.exe"
set "BL="
if exist "%C1%" set "BL=%C1%"
if not defined BL if exist "%C2%" set "BL=%C2%"
if not defined BL goto noblender
if not exist "%SRC%\brief.json" goto nosrc
if not exist "%WORLDS%" goto noworlds
if exist "%GLB%" goto already

echo.
echo  ============================================================
echo   REBUILD AND CHECK  -  variant skins, after the fix
echo   UPBGE: %BL%
echo  ============================================================
echo.
echo  [1/3] Probe the built scene (same brief, same seed) - expect RESULT: CLEAN
"%BL%" --background --factory-startup -noaudio --python "%HERE%\probe-variant-skins.py" -- "%SRC%"
if errorlevel 1 goto probefail
findstr /C:"RESULT: CLEAN" "%SRC%\probe-variant-skins.txt"
if errorlevel 1 goto probedirty

echo.
echo  [2/3] Real build through run-brief.py into the disposable place "variant-skin-check" (about 2 minutes)
if not exist "%JOB%" mkdir "%JOB%"
copy /Y "%SRC%\brief.json" "%JOB%\brief.json"
if not exist "%PLACE%" mkdir "%PLACE%"
"%BL%" --background --factory-startup -noaudio --python "%HERE%\run-brief.py" -- "%JOB%" --slug variant-skin-check
if errorlevel 1 goto buildfail
if not exist "%GLB%" goto noglb

echo.
echo  [3/3] Read the GLB back - one skin per prop, bodies present
"%BL%" --background --factory-startup -noaudio --python "%HERE%\check-world-glb.py" -- "%GLB%"
if errorlevel 1 goto glbdirty

echo.
echo  ------------------------------------------------------------
echo   RESULT: OK - the same brief that built the exploded hydrant and floating
echo   handles now builds clean, all the way through the production exporter.
echo   Evidence: %JOB%\build-log.txt  (look for "kept metal_trash_can_rust")
echo             %SRC%\probe-variant-skins.txt
echo   The place "variant-skin-check" is disposable - delete its folder when done:
echo   %WORLDS%\variant-skin-check
echo  ------------------------------------------------------------
echo.
pause
exit /b 0

:glbdirty
echo.
echo   RESULT: FAILED - the rebuilt GLB still has a defect (see the DEFECT lines above).
echo   Layer: the fix in build-neighbourhood.py / run-brief.py did not cover this case.
echo.
pause
exit /b 1

:noglb
echo.
echo   RESULT: FAILED - run-brief.py finished but wrote no GLB at %GLB%
echo   Read %JOB%\build-log.txt. Layer: run-brief.py export.
echo.
pause
exit /b 1

:buildfail
echo.
echo   RESULT: FAILED - headless UPBGE exited with an error during the real build.
echo   Read %JOB%\build-log.txt and the lines above. Layer: run-brief.py inside UPBGE.
echo.
pause
exit /b 1

:probedirty
echo.
echo   RESULT: FAILED - the probe still says REPRODUCED after the fix. Nothing was built.
echo   Read %SRC%\probe-variant-skins.txt. Layer: build-neighbourhood.py place() filter.
echo.
pause
exit /b 1

:probefail
echo.
echo   RESULT: FAILED - the probe itself errored inside UPBGE (see above). Nothing was built.
echo.
pause
exit /b 1

:already
echo.
echo   STOP: %GLB% already exists - a previous check run left it. Delete the folder
echo   %WORLDS%\variant-skin-check and run again (run-brief refuses to overwrite).
echo.
pause
exit /b 1

:noworlds
echo.
echo   STOP: the world folder was not found: %WORLDS%
echo.
pause
exit /b 1

:nosrc
echo.
echo   STOP: the broken job is missing: %SRC%\brief.json
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

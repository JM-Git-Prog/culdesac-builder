@echo off
setlocal
title Rebuild Mr. John's Neighborhood as version 8 - the Phase 1 plat

REM REBUILD-V8-STREET-AHEAD.bat  -  2026-09-10 (Fable session, decision 25)
REM Rebuilds the live place from the SAME brief that made version 7 (jobs\v8-street-ahead\brief.json,
REM copied from 7-world.json) so it lands as the NEXT version. What is new in the builder since v7:
REM the Phase 1 plat: the main street runs south to a T, a cross street, twelve empty lots with road,
REM curb and sidewalk, a signboard on every empty lot, and every lot listed in the world file (decision 25).
REM Versions 0-7 stay on disk untouched. The viewer loads the highest version, so V17's pane shows v8.
REM Batch rules: no call :label, no parenthesised blocks, every exit prints and pauses,
REM no redirect characters except intended file redirects.

REM The builder lives on the E: drive. This card may be double-clicked from wherever it was saved
REM (Claude outputs, Downloads...), so find the builder folder first, then work there.
set "HERE=%~dp0"
set "HERE=%HERE:~0,-1%"
set "B1=E:\Software Development\Video Game Development\03 Projects\Cul-de-sac"
if exist "%B1%\run-brief.py" set "HERE=%B1%"
if not exist "%HERE%\run-brief.py" echo  The Neighbourhood Builder folder was not found. Looked in: %B1% and %~dp0 - nothing was run. && pause && exit /b 1
set "JOB=%HERE%\jobs\v8-street-ahead"
set "PLACE=C:\Users\JohnM\Artificial Intelligence\Projects\CEO-of-My-Life-Inc\CEO-3D-World\worlds\mr-johns-neighborhood\output\world"
set "C1=C:\Users\JohnM\Artificial Intelligence\UPBGE\upbge-0.50-windows-x64\blender.exe"
set "C2=%HERE%\..\..\01 Engines\UPBGE 0.50\blender.exe"
set "BL="
if exist "%C1%" set "BL=%C1%"
if not defined BL if exist "%C2%" set "BL=%C2%"
if not defined BL echo  UPBGE not found. Looked in: %C1% and %C2%. Nothing was run. && pause && exit /b 1
if not exist "%JOB%\brief.json" echo  Missing %JOB%\brief.json - the v7 brief copy is not there. Nothing was run. && pause && exit /b 1
if not exist "%PLACE%" echo  The neighborhood folder was not found: %PLACE% - nothing was run. && pause && exit /b 1
if exist "%JOB%\status.json" echo  This job already ran once - status.json exists. Delete jobs\v8-street-ahead\status.json to run it again. && pause && exit /b 1

echo.
echo  ============================================================
echo   REBUILD Mr. John's Neighborhood  -  version 8, the Phase 1 plat
echo   UPBGE: %BL%
echo   Place: %PLACE%
echo  ============================================================
echo.
echo  [1/2] Building (about 2 minutes)...
"%BL%" --background --factory-startup -noaudio --python "%HERE%\run-brief.py" -- "%JOB%" --slug mr-johns-neighborhood
if errorlevel 1 echo. && echo  RESULT: FAILED inside UPBGE - read %JOB%\build-log.txt and upbge-console.txt. && pause && exit /b 1

echo.
echo  [2/2] Checking the newest version's GLB - one skin per prop, bodies present
"%BL%" --background --factory-startup -noaudio --python "%HERE%\check-world-glb.py" -- "%PLACE%"
if errorlevel 1 echo. && echo  RESULT: the build landed but the GLB check found a defect - see the DEFECT lines above. && pause && exit /b 1

echo.
echo  ------------------------------------------------------------
echo   RESULT: OK - version 8 is on disk. Same eight houses, the street runs to a T,
echo   twelve empty lots with signboards, every lot listed in 8-world.json.
echo   See it: refresh V17's pane, or open http://localhost:5173/mr-johns-neighborhood
echo   Log: %JOB%\build-log.txt
echo  ------------------------------------------------------------
echo.
pause
exit /b 0

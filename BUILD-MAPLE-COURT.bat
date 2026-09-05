@echo off
title Build Maple Court - no window
REM Builds the cul-de-sac in the background: UPBGE runs with no window, renders six pictures
REM (aerial, street, one per house) and saves a .blend into renders\headless-STAMP\.
REM Nothing from earlier runs is touched. Nothing else needs to be open.
cd /d "%~dp0"
set "B1=C:\Users\JohnM\Artificial Intelligence\UPBGE\upbge-0.50-windows-x64\blender.exe"
set "B2=%~dp0..\..\01 Engines\UPBGE 0.50\blender.exe"
set "BLENDER="
if exist "%B1%" set "BLENDER=%B1%"
if not defined BLENDER if exist "%B2%" set "BLENDER=%B2%"
if not defined BLENDER goto missing
echo.
echo === Maple Court - building in the background, no window. About one to two minutes. ===
echo.
"%BLENDER%" --background --factory-startup -noaudio --python "%~dp0build-headless.py"
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" echo FAILED - open the newest renders\headless-* folder and read headless-log.txt
if "%RC%"=="0" echo Done. The six pictures and maple-court.blend are in the newest renders\headless-* folder.
pause
exit /b %RC%

:missing
echo UPBGE was not found. Looked in:
echo   %B1%
echo   %B2%
pause
exit /b 1

@echo off
title Save the builder to git, then reload it

REM ==========================================================================
REM  2026-09-04. One click, two jobs, in this order on purpose:
REM
REM    1. INIT-BUILDER-REPO.bat        - makes this folder a git repository and
REM                                      takes the first commit. Running it FIRST
REM                                      means today's candidate fix is captured
REM                                      in the very first line of history.
REM    2. RESTART-NEIGHBOURHOOD-BUILDER.bat - the service loaded its Python at
REM                                      start-up, so the fix is on disk but NOT
REM                                      running until it is restarted.
REM
REM  Today's fix, for the record: candidates_brief asked the model to "vary the
REM  style, wall colour and roof" - the very things John's sentence had just
REM  fixed - so a colonial order came back as one colonial plus a ranch and a
REM  modern. Two of three renders were wasted every time. The prompt now holds
REM  whatever the sentence fixed identical across all three, and normalise's
REM  variety guard is skipped on the candidates path so it cannot undo that.
REM
REM  Both scripts below verify their own result and say so. Neither pushes to
REM  GitHub - that needs John's account, and the commands are printed for him.
REM ==========================================================================

cd /d "%~dp0"

echo.
echo ==================================================================
echo   STEP 1 of 2 - PUT THE BUILDER UNDER VERSION CONTROL
echo ==================================================================
echo.

if not exist "INIT-BUILDER-REPO.bat" goto missinginit
call "%~dp0INIT-BUILDER-REPO.bat"
set "INITCODE=%ERRORLEVEL%"

echo.
echo ==================================================================
echo   STEP 2 of 2 - RELOAD THE BUILDER SO THE FIX IS ACTUALLY RUNNING
echo ==================================================================
echo.

if not exist "RESTART-NEIGHBOURHOOD-BUILDER.bat" goto missingrestart
call "%~dp0RESTART-NEIGHBOURHOOD-BUILDER.bat"
set "RESTARTCODE=%ERRORLEVEL%"

echo.
echo ==================================================================
echo   BOTH STEPS FINISHED
echo ==================================================================
echo.
echo   Version control step exit code: %INITCODE%   ^(0 means it worked^)
echo   Builder reload step exit code:  %RESTARTCODE%   ^(0 means it worked^)
echo.
if not "%INITCODE%"=="0" echo   *** STEP 1 REPORTED A PROBLEM - scroll up and read it. ***
if not "%RESTARTCODE%"=="0" echo   *** STEP 2 REPORTED A PROBLEM - scroll up and read it. ***
if "%INITCODE%"=="0" if "%RESTARTCODE%"=="0" echo   Both clean. The builder is saved and running the new code.
echo.
echo   You can close this window.
echo.
pause
exit /b 0

:missinginit
echo   *** INIT-BUILDER-REPO.bat IS NOT IN THIS FOLDER ***
echo   Nothing was changed. Expected it beside this script in:
echo   %CD%
echo.
pause
exit /b 1

:missingrestart
echo   *** RESTART-NEIGHBOURHOOD-BUILDER.bat IS NOT IN THIS FOLDER ***
echo   Version control step already ran; the builder was NOT reloaded.
echo   Expected the restart script beside this one in:
echo   %CD%
echo.
pause
exit /b 1

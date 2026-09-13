@echo off
title Save the house builder - commit today's work and push it
setlocal

REM ==========================================================================
REM  2026-09-13. The builder repo and its GitHub home BOTH already exist, and
REM  the first three commits were pushed on 2026-09-05 - read from .git, not
REM  assumed. What was never saved is everything since: decisions 25, 26 and 28
REM  (four real candidates, the choice on the lot, the red-door paint fix, the
REM  16-lot plat, per-house seeds, /api/rebuild and the UPBGE watchdog).
REM
REM  So this COMMITS and PUSHES. It does not create anything on GitHub - there
REM  is nothing left to create.
REM
REM  Modelled on SAVE-V17.bat: shows what will be saved before saving it,
REM  safety-stops on mass deletion, takes its message from COMMIT-MSG.txt and
REM  consumes it, verifies the commit landed, and asks GitHub whether the
REM  branch really arrived before claiming success.
REM ==========================================================================

REM --- find the folder by its known path first; the card you clicked is a copy.
set "PROJ=E:\Software Development\Video Game Development\03 Projects\Cul-de-sac"
if not exist "%PROJ%\build-neighbourhood.py" set "PROJ=%~dp0"
if not exist "%PROJ%\build-neighbourhood.py" goto nofolder
cd /d "%PROJ%"

REM --- find git; never assume where it lives.
set "GIT="
if exist "C:\Program Files\Git\cmd\git.exe" set "GIT=C:\Program Files\Git\cmd\git.exe"
if not defined GIT if exist "C:\Program Files (x86)\Git\cmd\git.exe" set "GIT=C:\Program Files (x86)\Git\cmd\git.exe"
if not defined GIT for /f "delims=" %%G in ('where git 2^>nul') do if not defined GIT set "GIT=%%G"
if not defined GIT goto nogit

echo.
echo ================================================================
echo   SAVE THE HOUSE BUILDER
echo ================================================================
echo.
echo   Folder: %PROJ%
echo   Git:    %GIT%
echo.

if not exist ".git" goto norepo

set "BR="
for /f "delims=" %%b in ('"%GIT%" rev-parse --abbrev-ref HEAD') do set "BR=%%b"
if not defined BR goto norepo
echo   Branch: %BR%
echo.

echo   [1 of 5] Staging everything that changed...
"%GIT%" add -A
if errorlevel 1 goto addfailed

echo.
echo   [2 of 5] Here is what will be saved:
"%GIT%" status --short
echo.

set "DEL=0"
for /f %%n in ('"%GIT%" diff --cached --name-only --diff-filter^=D ^| find /c /v ""') do set "DEL=%%n"
if %DEL% GTR 50 goto massdelete
echo   %DEL% file^(s^) staged as deleted - under the safety limit of 50.
echo.

"%GIT%" diff --cached --quiet
if not errorlevel 1 goto nothingtodo

set "MSG="
if exist "COMMIT-MSG.txt" set /p MSG=<COMMIT-MSG.txt
if not defined MSG set "MSG=save: builder snapshot %DATE% %TIME% - no COMMIT-MSG.txt supplied"
echo   [3 of 5] Commit message:
echo     %MSG%
echo.

"%GIT%" commit -m "%MSG%"
if errorlevel 1 goto commitfailed

REM Verify the commit REALLY landed - never print success after an error.
"%GIT%" diff --cached --quiet
if errorlevel 1 goto stillstaged
echo   [4 of 5] Commit recorded:
"%GIT%" log -1 --oneline
echo.

REM Consume the message so the next save cannot silently reuse these words.
if exist "COMMIT-MSG.txt" del "COMMIT-MSG.txt"

echo   [5 of 5] Pushing branch %BR% and asking GitHub whether it arrived...
"%GIT%" push origin "%BR%"
if errorlevel 1 goto pushfailed

set "LANDED="
for /f "delims=" %%h in ('"%GIT%" ls-remote --heads origin "%BR%"') do set "LANDED=%%h"
if not defined LANDED goto notlanded

echo.
echo ================================================================
echo   SAFE. The builder's new work is off this disk.
echo ================================================================
echo   Remote branch: %LANDED%
echo.
pause
exit /b 0

:nothingtodo
echo   Nothing has changed since the last save - nothing to commit.
echo   If you expected changes, the work may already be saved.
echo.
pause
exit /b 0

:notlanded
echo.
echo   ***  PUSH REPORTED SUCCESS BUT GITHUB HAS NO %BR% BRANCH  ***
echo   Treat this as a FAILED save. The new commit is on this disk only.
echo.
pause
exit /b 1

:massdelete
echo.
echo   ***  STOPPED - %DEL% FILES ARE STAGED AS DELETED  ***
echo   That is over the safety limit of 50. Nothing has been committed.
echo   Read the list above. If those deletions are real and wanted, commit
echo   them yourself; if not, run: git reset
echo.
pause
exit /b 1

:addfailed
echo.
echo   ***  git add FAILED - nothing was committed.  ***
echo   Read the error above and send it to Claude.
echo.
pause
exit /b 1

:commitfailed
echo.
echo   ***  git commit FAILED - NOTHING WAS SAVED.  ***
echo   Your files are still on disk and still staged; nothing was lost.
echo.
pause
exit /b 1

:stillstaged
echo.
echo   ***  git said it committed but changes are STILL staged.  ***
echo   Treat this as a FAILED save. Nothing was pushed.
echo.
pause
exit /b 1

:pushfailed
echo.
echo   ***  THE COMMIT SAVED LOCALLY BUT THE PUSH FAILED.  ***
echo   Your work IS committed on this machine on branch %BR%, but it is
echo   not on GitHub yet. Most often this is a sign-in prompt - read the
echo   error above, then run this card again.
echo.
pause
exit /b 1

:norepo
echo.
echo   ***  THIS FOLDER IS NOT A GIT REPOSITORY  ***
echo   Expected a .git folder in %PROJ%. Nothing was changed.
echo.
pause
exit /b 1

:nogit
echo.
echo   ***  GIT WAS NOT FOUND  ***
echo   I looked in:
echo     C:\Program Files\Git\cmd\git.exe
echo     C:\Program Files (x86^)\Git\cmd\git.exe
echo     and every folder on your PATH
echo   Nothing was changed.
echo.
pause
exit /b 1

:nofolder
echo.
echo   ***  I CANNOT FIND THE BUILDER FOLDER  ***
echo   I looked for build-neighbourhood.py in:
echo     E:\Software Development\Video Game Development\03 Projects\Cul-de-sac
echo     %~dp0
echo   If the project moved, tell Claude the new path.
echo.
pause
exit /b 1

@echo off
title Push the Neighbourhood Builder to GitHub

REM ==========================================================================
REM  2026-09-04. STEP 3, after SAVE-THEN-RELOAD-BUILDER.bat.
REM
REM  git init gave this folder history. History on the SAME DISK dies with the
REM  disk, so this puts it somewhere else. It does not guess: it checks the
REM  repo exists, checks a remote is not already set, pushes, and then asks
REM  GitHub whether the branch really arrived before it claims success.
REM
REM  BEFORE RUNNING: create an EMPTY repository on GitHub named
REM  culdesac-builder - no README, no .gitignore, no licence. An empty repo is
REM  required; anything pre-filled makes the first push conflict.
REM
REM  This uses whatever GitHub account git is already signed in as on this
REM  machine. If it asks you to sign in, that is git's own prompt, not ours.
REM ==========================================================================

cd /d "%~dp0"

set "REPO=https://github.com/JM-Git-Prog/culdesac-builder.git"

echo.
echo ==================================================================
echo   PUSHING THE BUILDER OFF THIS DISK
echo ==================================================================
echo.
echo   Folder: %CD%
echo   Remote: %REPO%
echo.

where git.exe
if errorlevel 1 goto nogit

if not exist ".git" goto norepo

set "HASREMOTE="
for /f "delims=" %%r in ('git remote') do set "HASREMOTE=%%r"
if defined HASREMOTE goto haveremote

echo   Adding the remote...
git remote add origin "%REPO%"
if errorlevel 1 goto addfailed
goto dopush

:haveremote
echo   A remote is already set on this repo:
git remote -v
echo.
echo   Not changing it. Pushing to what is already there.
echo.

:dopush
echo.
echo   Pushing main...
git push -u origin main
if errorlevel 1 goto pushfailed

echo.
echo   Asking GitHub whether main really arrived...
set "LANDED="
for /f "delims=" %%h in ('git ls-remote --heads origin main') do set "LANDED=%%h"
if not defined LANDED goto notlanded

echo.
echo ==================================================================
echo   SAFE. The builder now exists somewhere other than this disk.
echo ==================================================================
echo   Remote branch: %LANDED%
echo.
echo   From now on, saving is just: git add -A ^& git commit -m "..." ^& git push
echo.
pause
exit /b 0

:notlanded
echo.
echo   *** PUSH REPORTED SUCCESS BUT GITHUB HAS NO main BRANCH ***
echo   Treat this as a FAILED save. The code is still only on this disk.
echo.
pause
exit /b 1

:pushfailed
echo.
echo   *** git push FAILED - read the error above. ***
echo   Most common causes, in order:
echo     1. The GitHub repo does not exist yet, or is not named culdesac-builder.
echo     2. The repo was created WITH a README, so it already has commits.
echo     3. Git is not signed in to the account that owns it.
echo   Nothing was lost - your local history is intact.
echo.
pause
exit /b 1

:addfailed
echo.
echo   *** Could not add the remote. Nothing was pushed. ***
echo.
pause
exit /b 1

:norepo
echo   *** THIS FOLDER IS NOT A GIT REPOSITORY YET ***
echo   Run SAVE-THEN-RELOAD-BUILDER.bat first - it creates the repo and takes
echo   the first commit. Nothing was changed.
echo.
pause
exit /b 1

:nogit
echo.
echo   *** git.exe WAS NOT FOUND ON THE PATH ***
echo   Nothing was changed.
echo.
pause
exit /b 1

@echo off
title Put the Neighbourhood Builder under version control

REM ==========================================================================
REM  2026-09-04. This folder holds build-neighbourhood.py and
REM  neighbourhood-service.py - the thing that turns John's sentence into a
REM  house - and it has NEVER been a git repository. Every other part of the
REM  project has history and a remote; this one had one copy on one disk.
REM
REM  Today alone it gained: the georgian style, the bay grid that gives a
REM  facade a governing order, height-proportional columns, the centred door,
REM  and the swap ledger. All of that existed only here.
REM
REM  This makes it a repo and takes the first commit. .gitignore keeps the
REM  5.5 GB of job renders out - they are regenerable; the code is not.
REM  It does NOT push: adding a GitHub remote is one command, printed at the
REM  end, and needs John's account rather than a script's guess.
REM ==========================================================================

cd /d "%~dp0"

echo.
echo ==================================================================
echo   PUTTING THE NEIGHBOURHOOD BUILDER UNDER VERSION CONTROL
echo ==================================================================
echo.
echo   Folder: %CD%
echo.

where git.exe
if errorlevel 1 goto nogit

if exist ".git" goto already

if not exist ".gitignore" goto noignore

echo   Creating the repository...
git init -b main
if errorlevel 1 goto initfailed

echo.
echo   Staging the code ^(job renders are excluded by .gitignore^)...
git add -A
if errorlevel 1 goto addfailed

echo.
echo   This is what will be saved:
git status --short
echo.

git diff --cached --quiet
if not errorlevel 1 goto nothing

git commit -m "The Neighbourhood Builder, finally under version control. sentence to order form (Ollama, cloud tag first) to a house raised headlessly in UPBGE. Carries 2026-09-04's work: a georgian style (3 storeys, hipped roof, white trim, 15-18m) so a mansion outsizes its neighbours; bay_grid, an odd symmetric set of bays computed before anything is placed, so the door sits at the centre bay, the portico is square about it, windows land on bay lines and the canopy no longer cuts through the columns; columns whose thickness follows their height; a centred front door; and a swap ledger that records every word the order form had to replace instead of silently defaulting to colonial."
if errorlevel 1 goto commitfailed

git diff --cached --quiet
if errorlevel 1 goto stillstaged

echo.
echo   COMMITTED. History starts here:
git log -1 --oneline
echo.
echo ==================================================================
echo   ONE THING LEFT - a remote, so it is off this disk
echo ==================================================================
echo.
echo   Create an empty repo on GitHub ^(no README^), then run these two:
echo.
echo     git remote add origin https://github.com/JM-Git-Prog/culdesac-builder.git
echo     git push -u origin main
echo.
echo   Until then the history is real but it lives on this disk only.
echo.
pause
exit /b 0

:already
echo   This folder is ALREADY a git repository - nothing to do.
echo   Current state:
git log -1 --oneline
echo.
pause
exit /b 0

:nothing
echo   Nothing to commit - .gitignore may be excluding everything.
echo   No repository damage; check .gitignore and run again.
echo.
pause
exit /b 1

:noignore
echo   *** .gitignore IS MISSING ***
echo   Without it this commit would try to swallow 5.5 GB of job renders.
echo   Nothing was created. Restore .gitignore and run again.
echo.
pause
exit /b 1

:initfailed
echo.
echo   *** git init FAILED - read the error above. Nothing was changed. ***
echo.
pause
exit /b 1

:addfailed
echo.
echo   *** git add FAILED - the repo exists but nothing was committed. ***
echo.
pause
exit /b 1

:commitfailed
echo.
echo   *** git commit FAILED - NOTHING WAS SAVED. Read the error above. ***
echo   Your files are untouched and still staged.
echo.
pause
exit /b 1

:stillstaged
echo.
echo   *** git said it committed but changes are STILL staged. ***
echo   Treat this as a FAILED save.
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

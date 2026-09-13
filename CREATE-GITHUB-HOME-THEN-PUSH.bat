@echo off
title Give the builder a home on GitHub, then push it there

REM ==========================================================================
REM  2026-09-05. One click, two halves, with you in the middle.
REM
REM  Half 1 - this opens the GitHub "new repository" page in your work Chrome
REM           with the name already filled in. Creating it is yours to do; it
REM           is your account and your sign-in.
REM
REM  Half 2 - when you come back and press a key, this runs the existing
REM           PUSH-BUILDER-TO-GITHUB.bat, which pushes and then asks GitHub
REM           whether the branch really arrived before claiming success.
REM
REM  ON THE PAGE, four things must be true or the push will fail:
REM     Owner  must be  JM-Git-Prog     - that is what the remote points at
REM     Name   must be  culdesac-builder - exactly, no capitals, no spaces
REM     Private is fine and recommended
REM     Add a README / .gitignore / licence must ALL be left UNTICKED.
REM         An empty repo is required. Anything pre-filled gives it a commit
REM         of its own and the first push collides with it.
REM ==========================================================================

cd /d "%~dp0"

set "OPENER=C:\Users\JohnM\Artificial Intelligence\Projects\CEO-of-My-Life-Inc\OPEN-IN-WORK-CHROME.bat"
set "URL=https://github.com/new?name=culdesac-builder&visibility=private"
set "PUSHER=%~dp0PUSH-BUILDER-TO-GITHUB.bat"

echo.
echo ==================================================================
echo   STEP 1 of 2 - CREATE THE EMPTY REPOSITORY
echo ==================================================================
echo.
echo   Opening the GitHub new-repository page in your work Chrome.
echo.
echo   Check these four things on the page:
echo      Owner:    JM-Git-Prog
echo      Name:     culdesac-builder
echo      Private:  yes
echo      README, .gitignore, licence:  ALL UNTICKED
echo.
echo   Then click Create repository.
echo.

if not exist "%OPENER%" goto noopener
call "%OPENER%" "%URL%"

echo   When the repository exists and is empty, press any key here.
echo   Nothing has been pushed yet, so it is safe to close this window
echo   instead if you changed your mind.
echo.
pause

echo.
echo ==================================================================
echo   STEP 2 of 2 - PUSH THE BUILDER OFF THIS DISK
echo ==================================================================
echo.

if not exist "%PUSHER%" goto nopusher
call "%PUSHER%"
set "PUSHCODE=%ERRORLEVEL%"

echo.
echo ==================================================================
echo   RESULT
echo ==================================================================
echo.
if not "%PUSHCODE%"=="0" goto pushfailed
echo   Done. The builder now exists somewhere other than this disk.
echo.
echo   From tonight, the Nightly Safety Net keeps it that way and will
echo   write ALL SAFE or NOT SAFE into BACKUP-STATUS.txt in your
echo   Artificial Intelligence folder every night at 11:15 PM.
echo.
echo   You can close this window.
echo.
pause
exit /b 0

:pushfailed
echo   *** THE PUSH DID NOT SUCCEED - exit code %PUSHCODE% ***
echo   Scroll up. The push script prints the reason and the usual causes.
echo   Nothing was lost. Your work is still here on this disk, and its
echo   local history is intact.
echo.
pause
exit /b 1

:noopener
echo   *** COULD NOT FIND YOUR CHROME OPENER ***
echo   Looked for it at:
echo   %OPENER%
echo.
echo   Nothing was changed. Open this address yourself instead:
echo   %URL%
echo.
pause
exit /b 1

:nopusher
echo   *** PUSH-BUILDER-TO-GITHUB.bat IS NOT IN THIS FOLDER ***
echo   Looked for it beside this script in:
echo   %CD%
echo.
echo   Nothing was pushed.
echo.
pause
exit /b 1

@echo off
title Typecheck THE world (tsc --noEmit)
REM Runs the world app's TypeScript check (the E5 ship rule: zero new errors) and leaves the result on screen.
REM Read-only: compiles nothing to disk, changes nothing.
set "APP=C:\Users\JohnM\Artificial Intelligence\Projects\CEO-of-My-Life-Inc\CEO-3D-World\app"
set "LOG=%~dp0tsc-log.txt"
if not exist "%APP%\package.json" goto missing
where npx >nul 2>&1
if errorlevel 1 goto nonode
echo Checking types in %APP% ...
echo (about 30-60 seconds)
cd /d "%APP%"
call npx tsc --noEmit --pretty false > "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
echo.
type "%LOG%"
echo.
if "%RC%"=="0" echo RESULT: PASS - zero type errors.
if not "%RC%"=="0" echo RESULT: FAIL - tsc exit code %RC% (errors listed above, also in %LOG%).
echo EXIT %RC% >> "%LOG%"
pause
exit /b %RC%

:missing
echo The world app was not found at %APP%
pause
exit /b 1

:nonode
echo npx (Node.js) was not found on PATH. Looked for: npx on PATH.
pause
exit /b 1

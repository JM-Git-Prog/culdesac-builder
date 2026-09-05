@echo off
title Restart the Neighbourhood Builder (8196)
REM 2026-09-03 - the running builder predates today's code (every job on disk is a
REM fresh build; the "next version of a place" path was never exercised), so the
REM neighbourhood (decision 22) needs the service restarted from disk.
REM Kills ONLY the process listening on 8196 (its PID captured first), re-checks the
REM port really cleared, then starts the builder through its own START bat.
cd /d "%~dp0"
set "PID="
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8196 " ^| findstr LISTENING') do set "PID=%%p"
if not defined PID goto startit
echo The builder is listening on 8196 as PID %PID% - stopping that process only...
taskkill /PID %PID% /T /F
timeout /t 2 /nobreak
set "STILL="
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8196 " ^| findstr LISTENING') do set "STILL=%%p"
if defined STILL echo Port 8196 is STILL held by PID %STILL% - the kill did not clear it. Close that window by hand, then run this again.
if defined STILL pause
if defined STILL exit /b 1
echo Port 8196 is clear.
:startit
echo Starting the Neighbourhood Builder from disk in its own window...
start "Neighbourhood Builder - 127.0.0.1:8196" cmd /c call "%~dp0START-NEIGHBOURHOOD-BUILDER.bat"
timeout /t 6 /nobreak
set "UP="
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8196 " ^| findstr LISTENING') do set "UP=%%p"
if defined UP echo The builder is back on 8196 as PID %UP%. Done - you can close this window.
if not defined UP echo The builder is not listening on 8196 yet - read the window that just opened for the reason.
pause
exit /b 0

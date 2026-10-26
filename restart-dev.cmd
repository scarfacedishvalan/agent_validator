@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0restart-dev.ps1" %*
set "restartExitCode=%ERRORLEVEL%"
if not "%restartExitCode%"=="0" echo Restart failed with exit code %restartExitCode%. Review the output above.
pause
exit /b %restartExitCode%

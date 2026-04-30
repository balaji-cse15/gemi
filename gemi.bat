@echo off
REM Gemi - unified launcher (Windows shim).
REM Forwards everything to gemi.ps1.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0gemi.ps1" %*

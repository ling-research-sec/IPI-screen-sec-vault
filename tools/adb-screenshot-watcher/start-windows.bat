@echo off
cd /d "%~dp0"
if "%ADB%"=="" set "ADB=adb"
py -3 -m screenshot_watcher --adb "%ADB%" gui %*
if errorlevel 1 pause

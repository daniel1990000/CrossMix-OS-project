@echo off
setlocal
cd /d "%~dp0"
:menu
cls
echo Smart Pro - custom RetroPass PSP project
echo.
echo 1. Back up the current card and verify the copy
echo 2. Inspect PPSSPP startup and controller settings (read-only)
echo 3. Prepare the pinned base and game files on the laptop
echo Q. Quit
echo.
echo These tools do not install or activate the custom OS on your handheld.
echo.
choice /C 123Q /N /M "Choose 1, 2, 3 or Q: "
if errorlevel 4 exit /b 0
if errorlevel 3 goto prepare
if errorlevel 2 goto inspect
if errorlevel 1 goto backup
exit /b 1
:backup
call "%~dp0START-HERE.cmd"
goto menu
:inspect
call "%~dp0INSPECT-RECOVERY.cmd"
goto menu
:prepare
call "%~dp0PREPARE-INSTALL.cmd"
goto menu

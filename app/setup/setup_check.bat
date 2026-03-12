@echo off
setlocal
if /I "%~1" NEQ "run" (
  start "" cmd /k ""%~f0" run"
  exit /b
)

title Line Tracker Setup
set "LOG=%TEMP%\line_tracker_setup.log"
set "APP_ROOT=%~dp0.."
set "APP_EXE=%APP_ROOT%\LineTracker.exe"
set "SOURCE_LAUNCHER=%APP_ROOT%\line_tracker_ui_click.vbs"
set "BUNDLED_GIT=%APP_ROOT%\PortableGit\cmd\git.exe"
set "APP_TARGET="
set "APP_MODE="
set "GIT_CMD="
set "GIT_SOURCE="

echo [Line Tracker] Setup log: %LOG%
echo [%DATE% %TIME%] Started > "%LOG%"

if exist "%APP_EXE%" (
  set "APP_TARGET=%APP_EXE%"
  set "APP_MODE=Bundled EXE"
) else if exist "%SOURCE_LAUNCHER%" (
  set "APP_TARGET=%SOURCE_LAUNCHER%"
  set "APP_MODE=Source launcher (Python required)"
)

if exist "%BUNDLED_GIT%" (
  set "GIT_CMD=%BUNDLED_GIT%"
  set "GIT_SOURCE=Bundled PortableGit"
) else (
  git --version >nul 2>nul
  if not errorlevel 1 (
    set "GIT_CMD=git"
    set "GIT_SOURCE=System PATH"
  )
)

>>"%LOG%" echo App mode: %APP_MODE%
>>"%LOG%" echo Git source: %GIT_SOURCE%

echo ============================
echo  Line Tracker Setup
echo ============================
echo.

echo App:
if defined APP_TARGET (
  echo   OK - %APP_MODE%
) else (
  echo   NOT FOUND
)
echo.

echo Git:
if defined GIT_CMD (
  "%GIT_CMD%" --version
  echo   Source: %GIT_SOURCE%
) else (
  echo   NOT FOUND
)
echo.

if defined APP_TARGET if defined GIT_CMD (
  echo Ready to run.
  echo.
  echo Launch Line Tracker now? (Y/N)
  set /p RUNAPP=^> 
  if /I "%RUNAPP%"=="Y" (
    start "" "%APP_TARGET%"
  )
  goto :end
)

if not defined APP_TARGET (
  echo App executable or launcher not found.
  echo Reinstall Line Tracker or rebuild the package.
  echo.
)

if not defined GIT_CMD (
  echo Git is missing.
  echo Install Git for Windows, or rebuild the installer with vendor\PortableGit bundled.
  echo.
  echo Open Git for Windows download page? (Y/N)
  set /p OPENPAGES=^> 
  if /I "%OPENPAGES%"=="Y" (
    start "" "https://git-scm.com/download/win"
  )
)

:end
echo.
pause
endlocal

@echo off
setlocal
set "ROOT=%~dp0"

echo [Line Tracker] Build Installer
echo.

where py >nul 2>nul
if errorlevel 1 (
  echo Python launcher (py) not found.
  echo Install Python 3.10+ and ensure py.exe is available.
  exit /b 1
)

echo Installing build deps...
py -3 -m pip install -r "%ROOT%requirements-build.txt"
if errorlevel 1 exit /b 1

echo.
echo Building app with PyInstaller...
py -3 -m PyInstaller --noconfirm --clean --noconsole ^
  --name "LineTracker" ^
  --distpath "%ROOT%dist" ^
  --workpath "%ROOT%build" ^
  --specpath "%ROOT%build" ^
  "%ROOT%app\line_tracker_ui.pyw"
if errorlevel 1 exit /b 1

echo.
echo Checking Inno Setup (iscc)...
where iscc >nul 2>nul
if errorlevel 1 (
  echo Inno Setup not found.
  echo Install Inno Setup and add iscc.exe to PATH.
  exit /b 1
)

echo.
echo Building installer...
iscc "%ROOT%installer\LineTracker.iss"
if errorlevel 1 exit /b 1

echo.
echo Done.
pause
endlocal

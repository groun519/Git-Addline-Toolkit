@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
for %%I in ("%SCRIPT_DIR%\..") do set "ROOT=%%~fI"
set "BUILD_ROOT=%SCRIPT_DIR%\build"
set "DIST_ROOT=%SCRIPT_DIR%\dist"
set "PORTABLE_GIT_SRC=%ROOT%\vendor\PortableGit"
set "PORTABLE_GIT_DST=%DIST_ROOT%\LineTracker\PortableGit"
set "PY_CMD="
set "PY_ARGS="
set "ISCC_CMD="

pushd "%ROOT%" >nul

echo [Line Tracker] Build Installer
echo.

py -3 -V >nul 2>nul
if not errorlevel 1 (
  set "PY_CMD=py"
  set "PY_ARGS=-3"
)

if not defined PY_CMD (
  python -V >nul 2>nul
  if not errorlevel 1 set "PY_CMD=python"
)

if not defined PY_CMD (
  echo Python launcher ^(py^) or python not found.
  echo Install Python 3.10+ and ensure one of them is available in PATH.
  exit /b 1
)

echo Running test suite...
%PY_CMD% %PY_ARGS% -m unittest discover -s tests -t . -v
if errorlevel 1 (
  echo.
  echo Tests failed. Aborting build.
  exit /b 1
)

echo.
echo Installing build deps...
%PY_CMD% %PY_ARGS% -m pip install -r "%SCRIPT_DIR%\requirements-build.txt"
if errorlevel 1 exit /b 1

echo.
echo Building app with PyInstaller...
%PY_CMD% %PY_ARGS% -m PyInstaller --noconfirm --clean --noconsole ^
  --name "LineTracker" ^
  --distpath "%DIST_ROOT%" ^
  --workpath "%BUILD_ROOT%" ^
  --specpath "%BUILD_ROOT%" ^
  "%ROOT%\app\line_tracker_ui.pyw"
if errorlevel 1 exit /b 1

echo.
echo Building CLI with PyInstaller...
%PY_CMD% %PY_ARGS% -m PyInstaller --noconfirm --clean --onefile ^
  --name "LineTrackerCli" ^
  --distpath "%DIST_ROOT%" ^
  --workpath "%BUILD_ROOT%\cli" ^
  --specpath "%BUILD_ROOT%" ^
  "%ROOT%\app\line_tracker.py"
if errorlevel 1 exit /b 1

if exist "%PORTABLE_GIT_DST%" (
  echo Removing stale PortableGit bundle...
  rmdir /s /q "%PORTABLE_GIT_DST%"
)

if exist "%PORTABLE_GIT_SRC%\cmd\git.exe" (
  echo.
  echo Bundling PortableGit from "%PORTABLE_GIT_SRC%"
  xcopy "%PORTABLE_GIT_SRC%" "%PORTABLE_GIT_DST%\" /E /I /Q /Y >nul
  if errorlevel 1 exit /b 1
) else (
  echo.
  echo PortableGit bundle not found.
  echo To ship a self-contained installer, extract PortableGit to "%PORTABLE_GIT_SRC%"
  echo Installer will require Git for Windows in PATH on the target PC.
)

echo.
echo Checking Inno Setup ^(iscc^)...
iscc /? >nul 2>nul
if not errorlevel 1 set "ISCC_CMD=iscc"

if not defined ISCC_CMD if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC_CMD=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not defined ISCC_CMD if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC_CMD=C:\Program Files\Inno Setup 6\ISCC.exe"
if not defined ISCC_CMD if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC_CMD=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"

if not defined ISCC_CMD (
  echo Inno Setup not found.
  echo Install Inno Setup or add iscc.exe to PATH.
  exit /b 1
)

echo.
echo Building installer...
"%ISCC_CMD%" "%SCRIPT_DIR%\LineTracker.iss"
if errorlevel 1 exit /b 1

if /i not "%LINE_TRACKER_SKIP_SMOKE%"=="1" (
  echo.
  echo Running installer smoke test...
  call "%SCRIPT_DIR%\smoke_test_installer.bat" "%DIST_ROOT%\LineTrackerSetup.exe" "%ROOT%" "%BUILD_ROOT%\_smoke_install"
  if errorlevel 1 exit /b 1
)

echo.
echo Done.
if /i not "%LINE_TRACKER_NO_PAUSE%"=="1" pause
popd >nul
endlocal

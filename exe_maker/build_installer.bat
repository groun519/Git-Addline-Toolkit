@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
for %%I in ("%SCRIPT_DIR%\..") do set "ROOT=%%~fI"
set "BUILD_ROOT=%SCRIPT_DIR%\build"
set "DIST_ROOT=%SCRIPT_DIR%\dist"
set "PORTABLE_GIT_SRC=%ROOT%\vendor\PortableGit"
set "PORTABLE_GIT_DST=%DIST_ROOT%\LineTracker\PortableGit"
set "ICON_FILE=%ROOT%\assets\line_tracker.ico"
set "APP_VERSION="
set "PY_CMD="
set "PY_ARGS="
set "PY_EXE="
set "PY_HOME="
set "BUILD_VENV=%SCRIPT_DIR%\.build-venv"
set "ORIGINAL_PATH=%PATH%"
set "ISCC_CMD="

pushd "%ROOT%" >nul

if not exist "%ROOT%\VERSION" (
  echo VERSION file not found.
  exit /b 1
)

set /p APP_VERSION=<"%ROOT%\VERSION"
if not defined APP_VERSION (
  echo VERSION file is empty.
  exit /b 1
)

echo [Line Tracker %APP_VERSION%] Build Installer
echo.

if exist "%ROOT%\.venv\Scripts\python.exe" set "PY_EXE=%ROOT%\.venv\Scripts\python.exe"

if not defined PY_EXE if exist "%BUILD_VENV%\Scripts\python.exe" set "PY_EXE=%BUILD_VENV%\Scripts\python.exe"

if not defined PY_EXE (
  py -3 -V >nul 2>nul
  if not errorlevel 1 (
    set "PY_CMD=py"
    set "PY_ARGS=-3"
  )
)

if not defined PY_EXE (
  if not defined PY_CMD (
    python -V >nul 2>nul
    if not errorlevel 1 set "PY_CMD=python"
  )

  if not defined PY_CMD (
    echo Python launcher ^(py^) or python not found.
    echo Install Python 3.10+ and ensure one of them is available in PATH.
    exit /b 1
  )

  echo Creating isolated build environment...
  %PY_CMD% %PY_ARGS% -m venv "%BUILD_VENV%"
  if errorlevel 1 exit /b 1
  set "PY_EXE=%BUILD_VENV%\Scripts\python.exe"
)
for %%I in ("%PY_EXE%") do set "PY_HOME=%%~dpI"

echo Installing build deps...
"%PY_EXE%" -m pip install -r "%SCRIPT_DIR%\requirements-build.txt"
if errorlevel 1 exit /b 1

echo Verifying Qt runtime...
"%PY_EXE%" -c "from PySide6 import QtCore; print('PySide6', QtCore.__version__)"
if errorlevel 1 (
  echo PySide6 runtime verification failed. Aborting build.
  exit /b 1
)

echo.
echo Preparing bundled Git runtime...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%\ensure_portable_git.ps1"
if errorlevel 1 (
  echo Bundled Git provisioning failed. Aborting build.
  exit /b 1
)

echo.
echo Running test suite...
"%PY_EXE%" -m unittest discover -s tests -t . -v
if errorlevel 1 (
  echo.
  echo Tests failed. Aborting build.
  exit /b 1
)

echo.
echo Building app with PyInstaller...
rem Keep PyInstaller from collecting incompatible ICU DLLs from Anaconda or other PATH entries.
set "PATH=%PY_HOME%;%SystemRoot%\System32;%SystemRoot%;%SystemRoot%\System32\Wbem;%SystemRoot%\System32\WindowsPowerShell\v1.0"
if exist "%ICON_FILE%" (
  "%PY_EXE%" -m PyInstaller --noconfirm --clean --noconsole ^
    --name "LineTracker" ^
    --icon "%ICON_FILE%" ^
    --add-data "%ROOT%\VERSION;." ^
    --add-data "%ROOT%\assets;assets" ^
    --distpath "%DIST_ROOT%" ^
    --workpath "%BUILD_ROOT%" ^
    --specpath "%BUILD_ROOT%" ^
    "%ROOT%\app\line_tracker_ui.pyw"
) else (
  "%PY_EXE%" -m PyInstaller --noconfirm --clean --noconsole ^
    --name "LineTracker" ^
    --add-data "%ROOT%\VERSION;." ^
    --distpath "%DIST_ROOT%" ^
    --workpath "%BUILD_ROOT%" ^
    --specpath "%BUILD_ROOT%" ^
    "%ROOT%\app\line_tracker_ui.pyw"
)
if errorlevel 1 exit /b 1

echo.
echo Building CLI with PyInstaller...
if exist "%ICON_FILE%" (
  "%PY_EXE%" -m PyInstaller --noconfirm --clean --onefile ^
    --name "LineTrackerCli" ^
    --icon "%ICON_FILE%" ^
    --distpath "%DIST_ROOT%" ^
    --workpath "%BUILD_ROOT%\cli" ^
    --specpath "%BUILD_ROOT%" ^
    "%ROOT%\app\line_tracker.py"
) else (
  "%PY_EXE%" -m PyInstaller --noconfirm --clean --onefile ^
    --name "LineTrackerCli" ^
    --distpath "%DIST_ROOT%" ^
    --workpath "%BUILD_ROOT%\cli" ^
    --specpath "%BUILD_ROOT%" ^
    "%ROOT%\app\line_tracker.py"
)
if errorlevel 1 exit /b 1
set "PATH=%ORIGINAL_PATH%"

if exist "%DIST_ROOT%\LineTracker\_internal\icuuc.dll" (
  echo Unexpected ICU DLL was bundled with the Qt app.
  echo Check PATH for Anaconda or another third-party ICU installation.
  exit /b 1
)

if exist "%PORTABLE_GIT_DST%" (
  echo Removing stale PortableGit bundle...
  rmdir /s /q "%PORTABLE_GIT_DST%"
)

if not exist "%PORTABLE_GIT_SRC%\cmd\git.exe" (
  echo Bundled Git runtime not found after provisioning.
  exit /b 1
)

echo.
echo Bundling MinGit from "%PORTABLE_GIT_SRC%"
xcopy "%PORTABLE_GIT_SRC%" "%PORTABLE_GIT_DST%\" /E /I /Q /Y >nul
if errorlevel 1 exit /b 1

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
if exist "%ICON_FILE%" (
  "%ISCC_CMD%" /DAppVersion=%APP_VERSION% /DAppIconPath="%ICON_FILE%" "%SCRIPT_DIR%\LineTracker.iss"
) else (
  "%ISCC_CMD%" /DAppVersion=%APP_VERSION% "%SCRIPT_DIR%\LineTracker.iss"
)
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

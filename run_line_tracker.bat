@echo off
setlocal
set "ROOT=%~dp0"
set "ENTRY=%ROOT%app\line_tracker_ui.pyw"
set "VENV_PYTHONW=%ROOT%.venv\Scripts\pythonw.exe"
set "BUILT_APP=%ROOT%exe_maker\dist\LineTracker\LineTracker.exe"

if not exist "%ENTRY%" (
  echo Line Tracker entry point not found:
  echo "%ENTRY%"
  pause
  exit /b 1
)

if exist "%VENV_PYTHONW%" (
  start "" /D "%ROOT%" "%VENV_PYTHONW%" "%ENTRY%"
  exit /b 0
)

if exist "%BUILT_APP%" (
  start "" /D "%ROOT%" "%BUILT_APP%"
  exit /b 0
)

where pythonw.exe >nul 2>nul
if not errorlevel 1 (
  start "" /D "%ROOT%" pythonw.exe "%ENTRY%"
  exit /b 0
)

echo Python environment or built Line Tracker executable not found.
echo Create .venv and install requirements, or run exe_maker\build_installer.bat.
pause
exit /b 1

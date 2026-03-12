@echo off
setlocal
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "INSTALLER=%~1"
set "REPO_PATH=%~2"
set "INSTALL_ROOT=%~3"
set "INSTALL_DIR="
set "APP_EXE="
set "CLI_EXE="
set "SETUP_CHECK="
set "APP_PID="

if not defined INSTALLER set "INSTALLER=%ROOT%\dist\LineTrackerSetup.exe"
if not defined REPO_PATH set "REPO_PATH=%ROOT%"
if not defined INSTALL_ROOT set "INSTALL_ROOT=%ROOT%\build\_smoke_install"

call :make_install_dir
if errorlevel 1 exit /b 1

echo [Line Tracker] Installer Smoke Test
echo.

if not exist "%INSTALLER%" (
  echo Installer not found: "%INSTALLER%"
  exit /b 1
)

if not exist "%REPO_PATH%" (
  echo Repo path not found: "%REPO_PATH%"
  exit /b 1
)

echo Installing silently to "%INSTALL_DIR%"...
start "" /wait "%INSTALLER%" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /DIR="%INSTALL_DIR%"
if errorlevel 1 (
  echo Silent installer run failed.
  exit /b 1
)

set "APP_EXE=%INSTALL_DIR%\LineTracker.exe"
set "CLI_EXE=%INSTALL_DIR%\LineTrackerCli.exe"
set "SETUP_CHECK=%INSTALL_DIR%\setup\setup_check.bat"

if not exist "%APP_EXE%" (
  echo Installed app not found: "%APP_EXE%"
  exit /b 1
)

if not exist "%SETUP_CHECK%" (
  echo Setup check file not found: "%SETUP_CHECK%"
  exit /b 1
)

echo Running installed app smoke check...
if exist "%CLI_EXE%" (
  "%CLI_EXE%" --repo "%REPO_PATH%"
  if errorlevel 1 (
    echo Installed CLI smoke check failed.
    exit /b 1
  )
) else (
  start "" "%APP_EXE%" --once --repo "%REPO_PATH%"
  if errorlevel 1 (
    echo Failed to launch installed app.
    exit /b 1
  )

  C:\Windows\System32\timeout.exe /t 5 /nobreak >nul

  call :find_app_pid
  if defined APP_PID (
    echo Smoke app still running, terminating PID %APP_PID%...
    C:\Windows\System32\taskkill.exe /PID %APP_PID% /T /F >nul 2>nul
    if errorlevel 1 (
      echo Failed to terminate smoke app PID %APP_PID%.
      exit /b 1
    )
  )
)

C:\Windows\System32\timeout.exe /t 1 /nobreak >nul
echo Cleaning smoke install...
rmdir /s /q "%INSTALL_DIR%"
if exist "%INSTALL_DIR%" (
  echo Warning: smoke install dir not removed: "%INSTALL_DIR%"
)

echo.
echo Smoke test passed.
echo Installed app: "%APP_EXE%"
exit /b 0

:make_install_dir
set "INSTALL_DIR=%INSTALL_ROOT%\run_%RANDOM%_%RANDOM%"
if exist "%INSTALL_DIR%" goto :make_install_dir
exit /b 0

:find_app_pid
set "APP_PID="
set "APP_EXE_WMI=%APP_EXE:\=\\%"
for /f "tokens=2 delims==" %%I in ('C:\Windows\System32\wbem\WMIC.exe process where "ExecutablePath='%APP_EXE_WMI%'" get ProcessId /value ^| C:\Windows\System32\findstr.exe /b ProcessId') do (
  set "APP_PID=%%I"
)
set "APP_PID=%APP_PID:;=%"
exit /b 0

@echo off
setlocal
title Line Tracker Setup

echo ============================
echo  Line Tracker Setup (CMD)
echo ============================
echo.

set "PY_CMD="
set "PY_ARGS="
set "PY_MISSING=0"
set "GIT_MISSING=0"
set "TK_MISSING=0"

py -3 --version >nul 2>nul
if not errorlevel 1 (
  set "PY_CMD=py"
  set "PY_ARGS=-3"
)
if not defined PY_CMD (
  python --version >nul 2>nul
  if not errorlevel 1 set "PY_CMD=python"
)
if not defined PY_CMD (
  pythonw --version >nul 2>nul
  if not errorlevel 1 set "PY_CMD=pythonw"
)
if not defined PY_CMD (
  for /d %%D in ("%LocalAppData%\Programs\Python\Python*") do (
    if exist "%%D\python.exe" (
      set "PY_CMD=%%D\python.exe"
      goto :py_found
    )
  )
  for /d %%D in ("%ProgramFiles%\Python*") do (
    if exist "%%D\python.exe" (
      set "PY_CMD=%%D\python.exe"
      goto :py_found
    )
  )
  for /d %%D in ("%ProgramFiles(x86)%\Python*") do (
    if exist "%%D\python.exe" (
      set "PY_CMD=%%D\python.exe"
      goto :py_found
    )
  )
  if exist "%UserProfile%\anaconda3\python.exe" set "PY_CMD=%UserProfile%\anaconda3\python.exe"
  if exist "%UserProfile%\miniconda3\python.exe" set "PY_CMD=%UserProfile%\miniconda3\python.exe"
)
:py_found
if not defined PY_CMD (
  set "PY_MISSING=1"
)

git --version >nul 2>nul
if errorlevel 1 (
  set "GIT_MISSING=1"
)

echo Python:
if "%PY_MISSING%"=="1" (
  echo   NOT FOUND
) else (
  "%PY_CMD%" %PY_ARGS% --version
)
echo.

echo Git:
if "%GIT_MISSING%"=="1" (
  echo   NOT FOUND
) else (
  git --version
)
echo.

echo Tkinter:
if "%PY_MISSING%"=="1" (
  echo   (skipped - python missing)
  set "TK_MISSING=1"
) else (
  "%PY_CMD%" %PY_ARGS% -c "import tkinter; print('tkinter OK')" 2>nul
  if errorlevel 1 (
    echo   NOT FOUND
    set "TK_MISSING=1"
  )
)
echo.

if "%PY_MISSING%"=="0" if "%GIT_MISSING%"=="0" if "%TK_MISSING%"=="0" (
  echo All OK.
  echo.
  echo Launch Line Tracker now? (Y/N)
  set /p RUNAPP=^> 
  if /I "%RUNAPP%"=="Y" (
    call "%~dp0..\line_tracker_ui_click.vbs"
  )
  goto :end
)

echo One or more items are missing.
echo Open install pages? (Y/N)
set /p OPENPAGES=^> 
if /I "%OPENPAGES%"=="Y" (
  if "%PY_MISSING%"=="1" (
    start "" "https://www.python.org/downloads/"
  )
  if "%GIT_MISSING%"=="1" (
    start "" "https://git-scm.com/download/win"
  )
)

:end
echo.
pause
endlocal

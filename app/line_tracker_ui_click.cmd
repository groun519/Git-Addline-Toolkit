@echo off
setlocal
cd /d "%~dp0"

set "PY_EXE=pythonw"
where %PY_EXE% >nul 2>nul || set "PY_EXE=python"
start "" %PY_EXE% "%~dp0line_tracker_ui.pyw" %*

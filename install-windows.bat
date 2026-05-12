@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem =============================================================================
rem  SbVision IMS — one-folder Windows setup (venv + deps + database migrate)
rem  Prerequisites:
rem    - Python 3.12.x 64-bit from https://www.python.org/downloads/
rem      (installer: enable "Add python.exe to PATH")
rem    - This project folder copied intact (keep manage.py next to this file)
rem =============================================================================

cd /d "%~dp0"
set "ROOT=%CD%"
set "VENV=%ROOT%\.venv"
set "PIP=%VENV%\Scripts\pip.exe"
set "PY=%VENV%\Scripts\python.exe"

echo.
echo [%TIME%] SbVision IMS - Windows install
echo Project: %ROOT%
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python not found in PATH.
  echo Install Python 3.12 from https://www.python.org/downloads/windows/ ^(64-bit^)
  echo Re-run this script after install. Prefer "Add python.exe to PATH".
  exit /b 1
)

for /f "tokens=1,2 delims=." %%a in ('python -c "import sys;print(sys.version_info[0],sys.version_info[1])"') do set MAJ=%%a& set MIN=%%b
if not "!MAJ!"=="3" (
  echo ERROR: Need Python 3.12.x. Found Python !MAJ!.!MIN!.
  exit /b 1
)
if not "!MIN!"=="12" (
  echo WARNING: Project expects Python 3.12.x. Found 3.!MIN!. - continuing anyway...
)

if not exist "%ROOT%\manage.py" (
  echo ERROR: manage.py not found here. Put install-windows.bat in the project root ^(same folder as manage.py^).
  exit /b 1
)

if not exist "%ROOT%\requirements.txt" (
  echo ERROR: requirements.txt missing from project root.
  exit /b 1
)

echo Creating virtual environment: %VENV%
if exist "%VENV%" (
  echo ^(Reusing existing .venv - remove the folder for a clean reinstall^)
) else (
  python -m venv "%VENV%"
  if errorlevel 1 (
    echo ERROR: python -m venv failed.
    exit /b 1
  )
)

echo Upgrading pip...
"%PY%" -m pip install --upgrade pip wheel setuptools
if errorlevel 1 exit /b 1

echo Installing packages ^(this may take a few minutes^)...
"%PIP%" install -r "%ROOT%\requirements.txt"
if errorlevel 1 (
  echo ERROR: pip install failed.
  exit /b 1
)

echo.
echo Running database migrations...
"%PY%" "%ROOT%\manage.py" migrate --noinput
if errorlevel 1 (
  echo ERROR: migrate failed.
  exit /b 1
)

echo.
echo =============================================================================
echo  Install finished OK.
echo.
echo  Start the app on this PC:
echo    1. Open Command Prompt in this folder
echo    2. Run:  .venv\Scripts\activate.bat
echo    3. Run:  python manage.py runserver 0.0.0.0:8000
echo.
echo  Then open in browser:
echo    - On this PC:     http://127.0.0.1:8000
echo    - Other PCs/LAN:  http://THIS_PC_IP:8000   ^(allow port in Windows Firewall^)
echo.
echo  Production-like server on Windows ^(Waitress^):
echo    .venv\Scripts\activate.bat
echo    waitress-serve --listen=0.0.0.0:8000 InventoryMS.wsgi:application
echo.
echo  Create an admin user ^(first time only^):
echo    .venv\Scripts\activate.bat
echo    python manage.py createsuperuser
echo =============================================================================
echo.
endlocal
exit /b 0

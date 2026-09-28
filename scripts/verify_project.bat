@echo off
setlocal
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
  echo Sanal ortam bulunamadi. Once README'deki kurulum adimlarini tamamlayin.
  exit /b 1
)

if not exist "web\node_modules" (
  echo Web bagimliliklari bulunamadi. Once web klasorunde npm ci calistirin.
  exit /b 1
)

echo [1/3] Ruff lint calisiyor...
.venv\Scripts\python.exe -m ruff check .
if errorlevel 1 exit /b 1

echo [2/3] Python testleri calisiyor...
.venv\Scripts\python.exe -m unittest discover -s tests -v
if errorlevel 1 exit /b 1

echo [3/3] React production build calisiyor...
cd web
call npm.cmd run build

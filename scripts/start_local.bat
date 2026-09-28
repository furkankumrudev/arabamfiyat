@echo off
setlocal
rem Starts the API and the web app in their own windows and opens the site.
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo Sanal ortam bulunamadi. Once README'deki kurulum adimlarini tamamlayin.
  pause
  exit /b 1
)
if not exist "web\node_modules" (
  echo Web bagimliliklari kuruluyor...
  pushd web
  call npm.cmd ci || (popd & pause & exit /b 1)
  popd
)
start "ArabamFiyat API" cmd /k "%~dp0run_api.bat"
start "ArabamFiyat Web" cmd /k "cd /d "%~dp0..\web" && npm.cmd run dev -- --open"
echo API ve web ayri pencerelerde basladi. Site tarayicida acilacak: http://localhost:5173

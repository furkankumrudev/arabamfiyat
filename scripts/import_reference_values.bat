@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo Sanal ortam bulunamadi. Once README'deki kurulum adimlarini tamamlayin.
  exit /b 1
)
.venv\Scripts\python.exe -m src.ingestion.tsb_reference %*

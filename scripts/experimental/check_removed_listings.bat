@echo off
cd /d "%~dp0..\.."
".venv\Scripts\python.exe" -m src.experimental.sahibinden.check_removed_listings %*

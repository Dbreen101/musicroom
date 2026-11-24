@echo off
rem run_gr.bat — run the Music Room from its code on a Windows PC, as the Green Room's fellows use it.
rem
rem   First time only (Python 3.12 from python.org, "Add python.exe to PATH" ticked):
rem       py -3.12 -m venv venv
rem       venv\Scripts\pip install -r requirements.txt
rem   Then:  run_gr.bat
rem   Another server address:  set MR_GR_SERVER=http://192.168.1.20:5300  then  run_gr.bat
rem
rem Your own library and settings live in %APPDATA%\Music Room GR, never in this code folder.
cd /d "%~dp0"
if not exist venv\Scripts\python.exe (
  echo First:  py -3.12 -m venv venv  and then  venv\Scripts\pip install -r requirements.txt
  exit /b 1
)
set MUSICROOM_3D=1
set MR_GREEN_ROOM=1
set MR_GR_VERSION=GR1
if "%MR_GR_SERVER%"=="" set MR_GR_SERVER=https://musicroom.tail323912.ts.net
if "%MUSICROOM_DATA%"=="" set "MUSICROOM_DATA=%APPDATA%\Music Room GR"
if "%MUSICROOM_PORT%"=="" set MUSICROOM_PORT=5177
if not exist "%MUSICROOM_DATA%" mkdir "%MUSICROOM_DATA%"
venv\Scripts\python.exe native\launcher.py

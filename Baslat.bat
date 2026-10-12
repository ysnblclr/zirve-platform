@echo off
REM Zirve Platformu - cift tiklayinca baslar ve tarayicida acilir (sadece bu bilgisayar).
chcp 65001 >nul
cd /d "%~dp0"
set PYEXE=py -3
%PYEXE% -c "import sys" >nul 2>&1 || set PYEXE=python
%PYEXE% -c "import fastapi, uvicorn, requests, bs4, lxml" >nul 2>&1 || (
  echo Gerekli paketler kuruluyor...
  %PYEXE% -m pip install --user -r requirements.txt
)
%PYEXE% sunucu.py %*
pause

@echo off
chcp 65001 >nul
title Zirve Kontrol Merkezi
cd /d "%~dp0"

echo ====================================================
echo  ZIRVE KONTROL MERKEZI
echo ====================================================

REM Port 8999 zaten calisiyor mu kontrol et
netstat -ano | findstr 127.0.0.1:8999 >nul
if %errorlevel% equ 0 (
    echo [BILGI] Kontrol Merkezi zaten arka planda calisiyor.
    echo [BILGI] Tarayicinizda aciliyor: http://127.0.0.1:8999
    start http://127.0.0.1:8999
    timeout /t 2 >nul
    exit /b
)

REM Python tespiti
set PYEXE=py -3
%PYEXE% -c "import sys" >nul 2>&1 || set PYEXE="C:\Users\Msi\AppData\Local\Programs\Python\Python311\python.exe"
%PYEXE% -c "import sys" >nul 2>&1 || set PYEXE=python

echo [BILGI] Kontrol Merkezi baslatiliyor...
echo [BILGI] Arayuz: http://127.0.0.1:8999
echo.
%PYEXE% yonetici.py
pause

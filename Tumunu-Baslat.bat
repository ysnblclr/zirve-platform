@echo off
chcp 65001 >nul
title Zirve Platformu - Tumunu Baslat
cd /d "%~dp0"

echo ====================================================
echo  ZIRVE PLATFORMU - TUM SERVISLER BASLATILIYOR
echo ====================================================

REM Kontrol merkezini baslat (arka planda)
netstat -ano | findstr 127.0.0.1:8999 >nul
if %errorlevel% neq 0 (
    echo [BILGI] Kontrol merkezi baslatiliyor...
    start /min "" cmd /c "py -3 yonetici.py || python yonetici.py"
    timeout /t 2 >nul
)

REM Sunucu ve Tunel servislerini baslat
echo [BILGI] Web Sunucusu ve Internet Tuneli devreye aliniyor...
powershell -NoProfile -Command "try { Invoke-RestMethod -Uri 'http://127.0.0.1:8999/api/servis/sunucu/baslat' -Method POST -ErrorAction SilentlyContinue | Out-Null; Invoke-RestMethod -Uri 'http://127.0.0.1:8999/api/servis/tunel/baslat' -Method POST -ErrorAction SilentlyContinue | Out-Null } catch {}"

echo [BILGI] Tum servisler baslatildi.
echo [BILGI] Tarayicida Kontrol Merkezi aciliyor: http://127.0.0.1:8999
start http://127.0.0.1:8999
timeout /t 2 >nul
exit /b

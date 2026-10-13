@echo off
chcp 65001 >nul
title Zirve Platformu - Docker Durdurucu
cd /d "%~dp0"

echo ====================================================
echo  Zirve Platformu Docker Konteynerleri Durduruluyor...
echo ====================================================

docker compose down

echo.
echo [OK] Tum Docker servisleri basariyla durduruldu.
pause

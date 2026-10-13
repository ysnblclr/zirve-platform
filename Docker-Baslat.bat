@echo off
chcp 65001 >nul
title Zirve Platformu - Docker Baslatici
cd /d "%~dp0"

echo ====================================================
echo  ZIRVE PLATFORMU - DOCKER ILE BASLATILIYOR
echo ====================================================

REM Docker motoru calisiyor mu kontrol et
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo [BILGI] Docker Desktop henuz acik degil.
    echo [BILGI] Docker Desktop baslatiliyor, lutfen bekleyin...
    start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    
    echo [BEKLEME] Docker motorunun hazir olmasi bekleniyor...
    :wait_docker
    timeout /t 3 >nul
    docker info >nul 2>&1
    if %errorlevel% neq 0 (
        echo   Docker baslatiliyor...
        goto wait_docker
    )
    echo [OK] Docker basariyla acildi!
)

echo [BILGI] Konteynerlar insa ediliyor ve arka planda baslatiliyor...
docker compose up -d --build

if %errorlevel% equ 0 (
    echo.
    echo ====================================================
    echo  BASARIYLA BASLATILDI!
    echo ====================================================
    echo  - Web Platformu:   http://127.0.0.1:8795
    echo  - Kontrol Paneli:  http://127.0.0.1:8999
    echo [BILGI] Canli Internet Tunel baglantisi aliniyor...
    powershell -NoProfile -Command "$logs = docker logs zirve_tunel 2>&1; if ($logs -match 'https://[a-zA-Z0-9\-]+\.trycloudflare\.com') { $u = $matches[0]; Write-Host '  - Internet Adresi: ' $u; '[InternetShortcut]`nURL=' + $u | Out-File -FilePath 'C:\Users\Msi\Desktop\Zirve Internet Linki.url' -Encoding ascii; Write-Host '  - Masaustune ''Zirve Internet Linki'' kisayolu kaydedildi.' }"
    echo ====================================================
    start http://127.0.0.1:8795
) else (
    echo [HATA] Docker konteynerleri baslatilamadi!
)

pause

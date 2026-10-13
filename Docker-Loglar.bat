@echo off
chcp 65001 >nul
title Zirve Platformu - Docker Canli Loglar
cd /d "%~dp0"

echo ====================================================
echo  Zirve Platformu Docker Canli Log Akisi
echo  (Kapatmak icin pencereyi kapatin veya Ctrl+C)
echo ====================================================

docker compose logs -f

@echo off
chcp 65001 >nul
title Zirve Kontrol Merkezi
cd /d "%~dp0"
echo ====================================================
echo  Zirve Kontrol Merkezi Baslatiliyor...
echo  Tarayicinizda http://127.0.0.1:8999 acilacaktir.
echo ====================================================
python yonetici.py
pause

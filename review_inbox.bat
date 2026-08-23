@echo off
chcp 65001 >nul
title HomeServer - Согласование файлов
echo ====================================================
echo    HomeServer: Лист Согласования Входящих Файлов
echo ====================================================
"C:\HomeServer\venv\Scripts\python.exe" "C:\HomeServer\scripts\tasks\review_inbox.py"
pause

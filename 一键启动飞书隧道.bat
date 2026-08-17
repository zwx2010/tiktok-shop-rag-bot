@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
title RAG Feishu Tunnel Launcher
python scripts\tunnel_up.py
echo.
pause

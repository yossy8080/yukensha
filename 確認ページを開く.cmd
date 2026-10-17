@echo off
rem 有権者：下書きの確認ページを開く（ダブルクリックで起動。閉じるときはこの黒い画面を閉じる）
chcp 65001 >nul
cd /d "%~dp0"
set "PY=python"
for /d %%D in ("%LOCALAPPDATA%\hermes\tools\python-*") do if exist "%%D\python.exe" set "PY=%%D\python.exe"
start "" http://localhost:5600/review
"%PY%" tools\review_server.py
pause

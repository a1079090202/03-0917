# 系统自检（不改动正式库 data/pharma.db，全程使用临时库）
# 用法：先双击过一次 start.bat 完成环境安装，再双击本文件。
@echo off
chcp 65001 >nul
title 系统验收自检
cd /d "%~dp0"

if not exist "backend\.venv\Scripts\python.exe" (
  echo 运行环境不存在，请先双击 start.bat 完成首次启动。
  pause
  exit /b 1
)

pushd backend
".\.venv\Scripts\python.exe" acceptance_test.py
popd
echo.
pause

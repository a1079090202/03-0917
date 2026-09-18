@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title 批号效期台账（关闭本窗口即停服务）
cd /d "%~dp0"

echo ==========================================================
echo            批号效期台账  启动器（首次启动请联网）
echo ==========================================================
echo.

REM ---------- 1. 找 Python ----------
set "PYCMD="
python --version >nul 2>&1 && set "PYCMD=python"
if not defined PYCMD (
  py -3 --version >nul 2>&1 && set "PYCMD=py -3"
)
if not defined PYCMD (
  echo [缺少运行环境] 这台电脑没有安装 Python。
  echo 这不是开发环境，只是运行库，请安装一次 Python 3.10 或以上版本：
  echo     https://www.python.org/downloads/
  echo 安装时务必勾选 "Add Python to PATH"，装完重新双击本文件。
  echo.
  pause
  exit /b 1
)
echo [1/4] 运行环境检查通过：
%PYCMD% --version

REM ---------- 2. 建虚拟环境（只建一次）----------
if not exist "backend\.venv\Scripts\python.exe" (
  echo [2/4] 首次运行，正在创建独立运行环境（约需 1~2 分钟）...
  %PYCMD% -m venv "backend\.venv"
  if errorlevel 1 (
    echo 创建运行环境失败。可改用系统 Python：删掉本目录下 backend\.venv 后联系技术人员。
    pause
    exit /b 1
  )
) else (
  echo [2/4] 运行环境已存在，跳过创建。
)
set "VPY=backend\.venv\Scripts\python.exe"

REM ---------- 3. 装依赖（已装则秒过）----------
echo [3/4] 检查依赖包...
"%VPY%" -m pip install -q -r "backend\requirements.txt"
if errorlevel 1 (
  echo 依赖安装失败，请确认电脑能上网后重试。
  pause
  exit /b 1
)

REM ---------- 4. 启动（首次启动会自动建库并播种演示数据）----------
if not exist "frontend_dist\index.html" (
  echo [提示] 未找到前端页面文件 frontend_dist，请使用完整交付包。
)
echo [4/4] 起服务（首次启动自动建库播种）……

echo.
echo 正在启动服务，随后会自动打开浏览器……
echo 8 家门店请用黑窗口里提示的 http://本机IP:8000 地址访问。
echo.
pushd backend
"..\%VPY%" run_server.py --open
popd

echo.
echo 服务已停止。
pause

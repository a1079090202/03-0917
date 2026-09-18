@echo off
chcp 65001 >nul
title 连锁药房批号效期台账
cd /d "%~dp0"

echo ============================================================
echo            连锁药房批号效期台账  一键启动
echo ============================================================
echo.

REM ---------- 1. 检查 Python ----------
where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未检测到 Python。
    echo        请先安装 Python 3.10 或更高版本：
    echo        https://www.python.org/downloads/
    echo        安装时务必勾选 "Add python.exe to PATH"。
    echo.
    pause
    exit /b 1
)

REM ---------- 2. 首次运行：创建虚拟环境 ----------
if not exist ".venv\Scripts\python.exe" (
    echo [1/3] 首次运行，正在创建虚拟环境（约半分钟）...
    python -m venv .venv
    if errorlevel 1 (
        echo [错误] 虚拟环境创建失败。
        pause
        exit /b 1
    )
)

REM ---------- 3. 安装/校验依赖 ----------
echo [2/3] 正在校验依赖（已装则秒过）...
.venv\Scripts\python.exe -m pip install --quiet --disable-pip-version-check -r backend\requirements.txt
if errorlevel 1 (
    echo [错误] 依赖安装失败，请检查网络连接后重试。
    pause
    exit /b 1
)

REM ---------- 4. 建库 + 种子 + 起服务 + 自动开页面 ----------
echo [3/3] 正在启动服务（首次会自动建库并灌入演示数据）...
echo.
echo        启动后本窗口会显示门店访问地址，浏览器将自动打开。
echo        关闭本窗口即停止系统。
echo.
.venv\Scripts\python.exe backend\run.py

echo.
echo 服务已停止。
pause

@echo off
chcp 65001 >nul
title 重置演示数据
cd /d "%~dp0"

echo 这将【清空并重建】台账数据库 data\pharma.db，恢复为标准演示数据：
echo   15 个药品、30 个批次（1 过期 / 2 近效期 / 1 停售）、8 家门店、近三个月流水。
echo.
set /p ok=确认重置请输入 YES 后回车：
if /i not "%ok%"=="YES" (
  echo 已取消。
  pause
  exit /b 0
)

if not exist "backend\.venv\Scripts\python.exe" (
  echo 运行环境不存在，请先双击 start.bat 完成首次启动。
  pause
  exit /b 1
)

pushd backend
".\.venv\Scripts\python.exe" -m app.seed --force
popd
echo.
echo 重置完成，重新双击 start.bat 即可。
pause

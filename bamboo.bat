@echo off
REM 彭州竹子运输对账助手 - 运行脚本 (Windows)

setlocal

cd /d "%~dp0"

REM 检查 Python 是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.8+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

REM 检查依赖是否已安装
python -c "import click" >nul 2>&1
if errorlevel 1 (
    echo [信息] 首次运行，正在安装依赖...
    python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    if errorlevel 1 (
        echo [错误] 依赖安装失败，请手动执行: pip install -r requirements.txt
        pause
        exit /b 1
    )
)

REM 以模块方式运行
python -m bamboo_reconcile.cli %*

if errorlevel 1 (
    echo.
    echo [提示] 如果命令是 import, 请使用 bamboo-import.bat 或 python -m bamboo_reconcile.cli import
)

endlocal

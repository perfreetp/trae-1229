#!/bin/bash
# 彭州竹子运输对账助手 - 运行脚本 (Linux/Mac)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "[错误] 未检测到 Python3，请先安装 Python 3.8+"
    exit 1
fi

# 检查依赖
if ! python3 -c "import click" &> /dev/null; then
    echo "[信息] 首次运行，正在安装依赖..."
    python3 -m pip install -r requirements.txt
fi

python3 -m bamboo_reconcile.cli "$@"

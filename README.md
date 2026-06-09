# 彭州竹子运输对账助手

> 供合作社财务和车队调度在电脑上批量核对运单的命令行工具

## ✨ 功能特性

| 命令 | 功能说明 |
|------|----------|
| **import** | 导入运单 Excel/CSV 文件、导入磅单照片清单 |
| **check**  | 校验车牌号、校验司机信息、检查重复运单、识别缺少装车点、校验重量、检查磅单匹配 |
| **price**  | 按竹种设置计价规则、按里程和重量计算运费、计价规则增删改查 |
| **merge**  | 合并同车同天多趟运单 |
| **split**  | 拆分运单，支持按重量/金额/比例/手动拆分多人分账 |
| **settle** | 标记已付款、生成司机结算单（导出Excel）、生成竹农付款清单（导出Excel） |
| **report** | 综合对账报表、按收购点汇总吨数、按装车点/竹种/司机汇总、日报表、待补资料列表 |
| **search** | 多条件搜索运单、按日期查询异常并交互式修复、记录人工备注 |

## 📦 快速开始

### 1. 环境要求
- Python 3.8 及以上
- Windows / Mac / Linux 均可

### 2. 安装依赖
```bash
# 进入项目目录
cd 项目路径

# 安装依赖（推荐清华源加速）
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 3. 初始化（首次使用）
```bash
# Windows (推荐)
bamboo.bat init --sample-data

# 或直接使用 Python
python -m bamboo_reconcile.cli init --sample-data
```

`--sample-data` 会生成近30天的示例运单，方便测试。

### 4. 查看帮助
```bash
# 查看所有命令
python -m bamboo_reconcile.cli --help

# 查看具体命令帮助
python -m bamboo_reconcile.cli import --help
python -m bamboo_reconcile.cli check --help
python -m bamboo_reconcile.cli settle driver --help
```

## 🚀 典型工作流

### 日常对账流程
```bash
# 1. 初始化基础档案（只需第一次）
bamboo init

# 2. 导入每日运单（Excel）
bamboo import --file 20240115运单.xlsx

# 3. 导入磅单照片清单（如有）
bamboo import --type weight --file 磅单目录清单.csv

# 4. 数据校验，自动修复可修复问题
bamboo check --all --fix

# 5. 计算运费
bamboo price calc

# 6. 有同车多趟的可以合并
bamboo merge --date 2024-01-15 --yes

# 7. 有多人分账的拆分
bamboo split --id WB202401150012 --by ratio --ratios 60,40 --farmer-names 张三,李四

# 8. 查询异常
bamboo search exception --start-date 2024-01-01 --end-date 2024-01-31

# 9. 月末生成司机结算单
bamboo settle driver --start-date 2024-01-01 --end-date 2024-01-31 --export 1月司机结算.xlsx

# 10. 月末生成竹农付款清单
bamboo settle farmer --start-date 2024-01-01 --end-date 2024-01-31

# 11. 标记付款完成
bamboo settle pay --driver 张三 --start-date 2024-01-01 --end-date 2024-01-31 --remark 银行转账

# 12. 生成月度报表
bamboo report summary --start-date 2024-01-01 --end-date 2024-01-31 --by month

# 13. 按收购点汇总吨数
bamboo report purchase --start-date 2024-01-01 --end-date 2024-01-31

# 14. 打印待补资料清单
bamboo report pending
```

## 📋 运单导入 Excel 模板字段

Excel 首行应为以下列名（部分可选，顺序无关）：

| 列名 | 说明 | 必填 |
|------|------|:----:|
| 运单号 | 运单编号，如不填自动生成 | 否 |
| 运输日期 | YYYY-MM-DD 格式 | 是 |
| 车牌号 | 川A12345 格式 | 是 |
| 司机姓名 | 司机名字 | 是 |
| 司机电话 | 11位手机号 | 否 |
| 竹种 | 毛竹/楠竹/慈竹等 | 是 |
| 装车点 | 装车点名称 | 是 |
| 收购点 | 收购点名称 | 否 |
| 里程 | 运输里程(km) | 否 |
| 毛重 | 毛重(吨) | 是 |
| 皮重 | 皮重(吨) | 是 |
| 净重 | 净重(吨)，如不填自动=毛重-皮重 | 否 |
| 磅单号 | 过磅单编号 | 否 |
| 单价 | 竹子单价(元/吨) | 否 |
| 竹农姓名 | 竹农/货主姓名 | 否 |
| 竹农电话 | 竹农联系电话 | 否 |
| 备注 | 其他备注 | 否 |

## 💾 数据存储位置

默认数据目录：
- **Windows**: `C:\Users\用户名\.bamboo_reconcile\`
- **Linux/Mac**: `~/.bamboo_reconcile/`

目录结构：
```
.bamboo_reconcile/
├── waybills.json          # 运单数据
├── weight_notes.json      # 磅单照片清单
├── pricing_rules.json     # 计价规则
├── drivers.json           # 司机档案
├── vehicles.json          # 车辆档案
├── bamboo_types.json      # 竹种档案
├── loading_points.json    # 装车点档案
├── purchase_points.json   # 收购点档案
├── settlements.json       # 结算记录
├── settings.json          # 系统设置
└── exports/
    ├── reports/           # 报表导出
    └── settlements/       # 结算单导出
```

可通过环境变量 `BAMBOO_DATA_DIR` 或 `--data-dir` 参数自定义目录。

## 📖 命令详解

### import - 导入
```bash
# 自动识别类型导入
bamboo import --file 运单.xlsx

# 指定类型导入
bamboo import --type weight --file 磅单清单.csv

# 试运行（不保存）
bamboo import --file 运单.xlsx --dry-run
```

### check - 校验
```bash
# 全部检查
bamboo check --all

# 单项检查
bamboo check --plate          # 车牌
bamboo check --driver         # 司机
bamboo check --duplicate      # 重复运单
bamboo check --loading        # 装车点
bamboo check --weight         # 重量
bamboo check --unmatched-weight  # 磅单匹配

# 指定日期范围 + 自动修复
bamboo check --all --start-date 2024-01-01 --end-date 2024-01-31 --fix
```

### price - 计价
```bash
# 查看计价规则
bamboo price list

# 新增竹种计价规则（基础价20元/吨 + 里程0.5元/吨·km）
bamboo price add --bamboo 毛竹 --base-price 20 --km-price 0.5

# 设置最低收费
bamboo price add --bamboo 楠竹 --base-price 25 --km-price 0.6 --min-charge 100

# 批量计算运费
bamboo price calc --start-date 2024-01-01 --end-date 2024-01-31

# 强制重新计算
bamboo price calc --recalc-all
```

### settle - 结算
```bash
# 生成司机结算单（自动导出Excel）
bamboo settle driver --start-date 2024-01-01 --end-date 2024-01-31

# 生成竹农付款清单
bamboo settle farmer --start-date 2024-01-01 --end-date 2024-01-31

# 标记付款
bamboo settle pay --id WB00123 --remark 现金支付
bamboo settle pay --driver 张三 --start-date 2024-01-01 --end-date 2024-01-31

# 查看未付款统计
bamboo settle unpaid --by driver
```

### report - 报表
```bash
# 综合日报
bamboo report daily

# 综合对账报表（按日/月/收购点等维度）
bamboo report summary --start-date 2024-01-01 --end-date 2024-01-31 --by day
bamboo report summary --start-date 2024-01-01 --end-date 2024-03-31 --by month

# 按收购点汇总
bamboo report purchase --start-date 2024-01-01 --end-date 2024-01-31

# 按装车点/竹种/司机汇总
bamboo report loading  --start-date 2024-01-01 --end-date 2024-01-31
bamboo report bamboo   --start-date 2024-01-01 --end-date 2024-01-31
bamboo report driver   --start-date 2024-01-01 --end-date 2024-01-31 --top 20

# 待补资料列表
bamboo report pending
```

### search - 搜索
```bash
# 关键词搜索
bamboo search waybill --keyword 川A12345
bamboo search waybill --keyword 张三

# 多条件组合搜索
bamboo search waybill --start-date 2024-01-01 --end-date 2024-01-15 --status exception

# 查看详情
bamboo search waybill --id WB00123 --detail

# 查询异常并交互式修复
bamboo search exception --start-date 2024-01-01 --end-date 2024-01-31 --fix

# 人工备注
bamboo search note --id WB00123 --list
bamboo search note --id WB00123 --add "司机确认无异常" --operator 李会计
```

## 🔧 常见问题

**Q: 导入Excel时提示字段不识别？**
A: 请确保Excel首行包含上表中的标准列名。列名不区分大小写，允许部分别名（如"司机"等同于"司机姓名"）。

**Q: 运费计算为0？**
A: 需要先为对应竹种设置计价规则。使用 `bamboo price add --bamboo 竹种名 --base-price xx --km-price xx`。

**Q: 数据文件在哪里？想备份怎么办？**
A: 默认在 `~/.bamboo_reconcile/` 目录，直接复制该目录即可完整备份。可设置环境变量 `BAMBOO_DATA_DIR` 更换位置。

**Q: 磅单照片如何管理？**
A: 准备一份CSV/Excel，包含"磅单号"和"照片文件路径"两列（或更多列），使用 `bamboo import --type weight` 导入即可自动与运单关联。

## 📝 License

MIT License

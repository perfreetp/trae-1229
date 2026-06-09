"""price 命令 - 按竹种设置计价规则、按里程和重量计算运费"""
import os
from typing import List, Optional, Dict, Any

import click

from ..models import Waybill, PricingRule, BambooType
from ..storage import DataStore
from ..utils import (
    print_table, format_money, format_weight, calculate_freight,
    calculate_bamboo_value, is_within_date_range, normalize_date,
    export_to_excel
)
from datetime import datetime


@click.group()
def price():
    """竹种计价规则管理与运费计算

    \b
    子命令:
      list    - 查看计价规则列表
      add     - 新增计价规则
      update  - 更新计价规则
      delete  - 删除计价规则
      calc    - 批量计算运费
    """
    pass


@price.command("list")
@click.option("--bamboo", "bamboo_name", default=None, help="按竹种名称筛选")
@click.pass_context
def price_list(ctx, bamboo_name: Optional[str]):
    """查看计价规则列表

    \b
    示例:
      bamboo price list
      bamboo price list --bamboo 毛竹
    """
    store: DataStore = ctx.obj["store"]
    rules = store.load_pricing_rules()
    bamboo_types = {b.id: b.name for b in store.load_bamboo_types()}

    if bamboo_name:
        rules = [r for r in rules if bamboo_name in r.bamboo_type_name]

    if not rules:
        click.echo("\n暂无计价规则数据")
        return

    data = []
    for r in rules:
        data.append([
            r.bamboo_type_name,
            format_money(r.base_price_per_ton),
            format_money(r.price_per_km_per_ton),
            f"{r.mileage_threshold}km" if r.mileage_threshold > 0 else "-",
            format_money(r.additional_price) if r.additional_price > 0 else "-",
            format_money(r.min_charge) if r.min_charge > 0 else "-",
            r.effective_date or "-",
            r.remark or ""
        ])

    print_table(
        data,
        ["竹种", "基础单价(元/吨)", "里程单价(元/吨·km)", "里程阈值", "额外加价", "最低收费", "生效日期", "备注"],
        f"计价规则列表 (共 {len(rules)} 条)"
    )


@price.command("add")
@click.option("--bamboo", "bamboo_name", required=True, help="竹种名称")
@click.option("--base-price", type=float, required=True, help="基础单价 (元/吨)")
@click.option("--km-price", type=float, default=0.0, help="里程单价 (元/吨·km)")
@click.option("--min-charge", type=float, default=0.0, help="最低运费 (元/车)")
@click.option("--threshold-km", type=float, default=0.0, help="里程阈值 (km)")
@click.option("--extra-price", type=float, default=0.0, help="超阈值额外加价 (元/吨·km)")
@click.option("--effective-date", default=None, help="生效日期 (YYYY-MM-DD)")
@click.option("--remark", default="", help="备注")
@click.pass_context
def price_add(
    ctx, bamboo_name: str, base_price: float, km_price: float, min_charge: float,
    threshold_km: float, extra_price: float, effective_date: Optional[str], remark: str
):
    """新增计价规则

    \b
    示例:
      bamboo price add --bamboo 毛竹 --base-price 20 --km-price 0.5
      bamboo price add --bamboo 楠竹 --base-price 25 --km-price 0.6 --min-charge 100
    """
    store: DataStore = ctx.obj["store"]

    bamboo = store.find_bamboo_by_name(bamboo_name)
    if not bamboo:
        bamboo = BambooType(name=bamboo_name, code=bamboo_name[:2].upper(), unit_price=base_price)
        store.add_bamboo_type(bamboo)
        click.echo(f"  自动创建竹种: {bamboo_name}")

    existing = store.get_pricing_rule_by_bamboo(bamboo.id)
    if existing:
        if not click.confirm(f"\n竹种 [{bamboo_name}] 已有计价规则，是否覆盖？"):
            click.echo("已取消")
            return

    rule = PricingRule(
        bamboo_type_id=bamboo.id,
        bamboo_type_name=bamboo_name,
        base_price_per_ton=base_price,
        price_per_km_per_ton=km_price,
        min_charge=min_charge,
        mileage_threshold=threshold_km,
        additional_price=extra_price,
        effective_date=effective_date or datetime.now().strftime("%Y-%m-%d"),
        remark=remark
    )

    if existing:
        rule.id = existing.id
        store.update_pricing_rule(rule)
        click.echo(f"\n✅ 已更新竹种 [{bamboo_name}] 的计价规则")
    else:
        store.add_pricing_rule(rule)
        click.echo(f"\n✅ 已新增竹种 [{bamboo_name}] 的计价规则")

    _print_rule_preview(rule)


@price.command("update")
@click.option("--bamboo", "bamboo_name", required=True, help="竹种名称")
@click.option("--base-price", type=float, default=None, help="基础单价 (元/吨)")
@click.option("--km-price", type=float, default=None, help="里程单价 (元/吨·km)")
@click.option("--min-charge", type=float, default=None, help="最低运费 (元/车)")
@click.option("--threshold-km", type=float, default=None, help="里程阈值 (km)")
@click.option("--extra-price", type=float, default=None, help="超阈值额外加价 (元/吨·km)")
@click.option("--remark", default=None, help="备注")
@click.pass_context
def price_update(
    ctx, bamboo_name: str, base_price: Optional[float], km_price: Optional[float],
    min_charge: Optional[float], threshold_km: Optional[float], extra_price: Optional[float],
    remark: Optional[str]
):
    """更新计价规则

    \b
    示例:
      bamboo price update --bamboo 毛竹 --base-price 22
      bamboo price update --bamboo 楠竹 --km-price 0.7 --remark 春节后调价
    """
    store: DataStore = ctx.obj["store"]

    bamboo = store.find_bamboo_by_name(bamboo_name)
    if not bamboo:
        click.echo(f"\n❌ 未找到竹种: {bamboo_name}", err=True)
        return

    rule = store.get_pricing_rule_by_bamboo(bamboo.id)
    if not rule:
        click.echo(f"\n❌ 竹种 [{bamboo_name}] 暂无计价规则，请先使用 add 命令创建", err=True)
        return

    if base_price is not None:
        rule.base_price_per_ton = base_price
    if km_price is not None:
        rule.price_per_km_per_ton = km_price
    if min_charge is not None:
        rule.min_charge = min_charge
    if threshold_km is not None:
        rule.mileage_threshold = threshold_km
    if extra_price is not None:
        rule.additional_price = extra_price
    if remark is not None:
        rule.remark = remark

    store.update_pricing_rule(rule)
    click.echo(f"\n✅ 已更新竹种 [{bamboo_name}] 的计价规则")
    _print_rule_preview(rule)


@price.command("delete")
@click.option("--bamboo", "bamboo_name", required=True, help="竹种名称")
@click.option("--yes", is_flag=True, help="跳过确认")
@click.pass_context
def price_delete(ctx, bamboo_name: str, yes: bool):
    """删除计价规则

    \b
    示例:
      bamboo price delete --bamboo 杂竹
    """
    store: DataStore = ctx.obj["store"]

    bamboo = store.find_bamboo_by_name(bamboo_name)
    if not bamboo:
        click.echo(f"\n❌ 未找到竹种: {bamboo_name}", err=True)
        return

    rule = store.get_pricing_rule_by_bamboo(bamboo.id)
    if not rule:
        click.echo(f"\n❌ 竹种 [{bamboo_name}] 暂无计价规则", err=True)
        return

    if not yes:
        if not click.confirm(f"\n确定要删除竹种 [{bamboo_name}] 的计价规则吗？"):
            click.echo("已取消")
            return

    rules = store.load_pricing_rules()
    rules = [r for r in rules if r.id != rule.id]
    store.save_pricing_rules(rules)
    click.echo(f"\n✅ 已删除竹种 [{bamboo_name}] 的计价规则")


@price.command("calc")
@click.option("--start-date", default=None, help="开始日期 (YYYY-MM-DD)")
@click.option("--end-date", default=None, help="结束日期 (YYYY-MM-DD)")
@click.option("--bamboo", "bamboo_name", default=None, help="按竹种筛选")
@click.option("--plate", default=None, help="按车牌号筛选")
@click.option("--recalc-all", is_flag=True, help="重新计算所有运单，忽略已有运费")
@click.option("--export", "export_path", default=None, help="导出结果到 Excel 文件")
@click.pass_context
def price_calc(
    ctx, start_date: Optional[str], end_date: Optional[str],
    bamboo_name: Optional[str], plate: Optional[str],
    recalc_all: bool, export_path: Optional[str]
):
    """批量计算运费

    \b
    示例:
      bamboo price calc
      bamboo price calc --start-date 2024-01-01 --end-date 2024-01-31
      bamboo price calc --bamboo 毛竹 --recalc-all
      bamboo price calc --export 运费计算.xlsx
    """
    store: DataStore = ctx.obj["store"]
    waybills = store.load_waybills()
    rules = store.load_pricing_rules()
    rule_map = {r.bamboo_type_id: r for r in rules}

    original_count = len(waybills)

    if start_date and end_date:
        waybills = [w for w in waybills if is_within_date_range(w.transport_date, start_date, end_date)]
    if bamboo_name:
        waybills = [w for w in waybills if bamboo_name in w.bamboo_type_name]
    if plate:
        waybills = [w for w in waybills if plate in w.license_plate]

    if not waybills:
        click.echo("\n没有需要计算运费的运单")
        return

    click.echo(f"\n准备计算 {len(waybills)} 条运单的运费...")

    if not rules:
        click.echo("\n⚠️  暂无计价规则，运费计算将为0。请先用 price add 添加规则")

    results = []
    updated_count = 0
    skipped = 0
    no_rule_count = 0

    for w in waybills:
        if not recalc_all and w.freight > 0:
            skipped += 1
            continue

        rule = None
        if w.bamboo_type_id:
            rule = rule_map.get(w.bamboo_type_id)
        if not rule and w.bamboo_type_name:
            for r in rules:
                if r.bamboo_type_name == w.bamboo_type_name:
                    rule = r
                    break

        if not rule:
            no_rule_count += 1

        w.freight = calculate_freight(w.net_weight, w.mileage, rule)
        w.bamboo_value = calculate_bamboo_value(w.net_weight, w.unit_price)
        w.farmer_amount = w.bamboo_value
        updated_count += 1

        results.append({
            "运单号": w.waybill_no,
            "日期": w.transport_date,
            "车牌": w.license_plate,
            "司机": w.driver_name,
            "竹种": w.bamboo_type_name,
            "里程(km)": w.mileage,
            "净重(吨)": round(w.net_weight, 3),
            "运费(元)": round(w.freight, 2),
            "竹款(元)": round(w.bamboo_value, 2),
            "状态": "已计算" if rule else "无计价规则"
        })

    if updated_count > 0:
        store.update_waybills_batch(waybills)

    click.echo(f"\n计算完成:")
    click.echo(f"  总运单数: {original_count}")
    click.echo(f"  已计算: {updated_count}")
    click.echo(f"  跳过(已有运费): {skipped}")
    if no_rule_count > 0:
        click.echo(f"  无计价规则: {no_rule_count}")

    total_freight = sum(w.freight for w in waybills)
    total_bamboo = sum(w.bamboo_value for w in waybills)
    total_weight = sum(w.net_weight for w in waybills)

    summary = [
        ["总净重", format_weight(total_weight)],
        ["总运费", format_money(total_freight)],
        ["总竹款", format_money(total_bamboo)],
        ["合计应付", format_money(total_freight + total_bamboo)],
    ]
    print_table(summary, ["统计项", "数值"], "费用汇总")

    if results:
        print_table(
            [[list(r.values()) for r in results[:20]]][0],
            list(results[0].keys()),
            f"计算明细 (前20条，共{len(results)}条)"
        )

    if export_path:
        filepath = export_path
        if not os.path.isabs(filepath):
            filepath = os.path.join(store.get_export_dir(), filepath)
        export_to_excel(results, filepath, sheet_name="运费计算")
        click.echo(f"\n✅ 已导出到: {filepath}")


def _print_rule_preview(rule: PricingRule):
    """预览计价规则"""
    sample_weights = [5, 10, 15, 20]
    sample_mileages = [10, 30, 50, 100]

    click.echo(f"\n计价示例 - 竹种: {rule.bamboo_type_name}")
    click.echo(f"  基础价: {format_money(rule.base_price_per_ton)}/吨 + "
               f"{format_money(rule.price_per_km_per_ton)}/吨·km")
    if rule.min_charge > 0:
        click.echo(f"  最低收费: {format_money(rule.min_charge)}/车")
    if rule.mileage_threshold > 0:
        click.echo(f"  超{rule.mileage_threshold}km额外: +{format_money(rule.additional_price)}/吨·km")

    data = []
    for wt in sample_weights:
        row = [f"{wt}吨"]
        for ml in sample_mileages:
            freight = calculate_freight(wt, ml, rule)
            row.append(format_money(freight))
        data.append(row)

    print_table(data, ["重量 / 里程"] + [f"{m}km" for m in sample_mileages], "运费预览表")

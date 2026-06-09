"""merge 命令 - 合并同车多趟"""
from typing import List, Dict, Any
from collections import defaultdict
from datetime import datetime

import click

from ..models import Waybill
from ..storage import DataStore
from ..utils import (
    print_table, format_money, format_weight, normalize_date,
    normalize_license_plate, is_within_date_range
)


@click.command("merge")
@click.option("--start-date", default=None, help="开始日期 (YYYY-MM-DD)")
@click.option("--end-date", default=None, help="结束日期 (YYYY-MM-DD)")
@click.option("--plate", default=None, help="指定车牌号合并")
@click.option("--date", "merge_date", default=None, help="指定日期合并 (YYYY-MM-DD)")
@click.option("--threshold", type=float, default=0.5,
              help="同批次净重差异阈值(吨)，小于此值视为可合并，默认0.5吨")
@click.option("--list", "list_only", is_flag=True, help="只列出可合并的运单，不实际合并")
@click.option("--yes", is_flag=True, help="跳过确认直接合并")
@click.pass_context
def cmd_merge(
    ctx, start_date, end_date, plate, merge_date,
    threshold: float, list_only: bool, yes: bool
):
    """合并同车多趟运单（同一车同一天多趟可合并为一条记录）

    \b
    合并规则:
      1. 相同车牌号
      2. 相同运输日期
      3. 相同装车点、收购点、竹种
      4. 合并后重量累加，运费累加

    \b
    示例:
      bamboo merge --list
      bamboo merge --plate 川A12345 --date 2024-01-15
      bamboo merge --start-date 2024-01-01 --end-date 2024-01-31 --yes
    """
    store: DataStore = ctx.obj["store"]
    waybills = store.load_waybills()

    waybills = [w for w in waybills if not w.is_merged and not w.is_split and not w.is_duplicate]

    if merge_date:
        start_date = merge_date
        end_date = merge_date

    if start_date and end_date:
        waybills = [w for w in waybills if is_within_date_range(w.transport_date, start_date, end_date)]
    elif start_date:
        waybills = [w for w in waybills if normalize_date(w.transport_date) >= normalize_date(start_date)]
    elif end_date:
        waybills = [w for w in waybills if normalize_date(w.transport_date) <= normalize_date(end_date)]

    if plate:
        waybills = [w for w in waybills if plate in normalize_license_plate(w.license_plate)]

    if not waybills:
        click.echo("\n没有可合并的运单")
        return

    click.echo(f"\n分析 {len(waybills)} 条运单的可合并情况...")

    groups: Dict[str, List[Waybill]] = defaultdict(list)
    for w in waybills:
        plate_n = normalize_license_plate(w.license_plate)
        dt = normalize_date(w.transport_date)
        lp = w.loading_point_id or w.loading_point_name or "unknown"
        pp = w.purchase_point_id or w.purchase_point_name or "unknown"
        bt = w.bamboo_type_id or w.bamboo_type_name or "unknown"
        key = f"{plate_n}|{dt}|{lp}|{pp}|{bt}"
        groups[key].append(w)

    merge_candidates = []
    for key, wbs in groups.items():
        if len(wbs) >= 2:
            wbs_sorted = sorted(wbs, key=lambda x: x.waybill_no)
            merge_candidates.append(wbs_sorted)

    if not merge_candidates:
        click.echo("\n✅ 没有找到可合并的运单组")
        return

    click.echo(f"\n找到 {len(merge_candidates)} 组可合并的运单:")

    preview_data = []
    for idx, wbs in enumerate(merge_candidates, 1):
        total_net = sum(w.net_weight for w in wbs)
        total_freight = sum(w.freight for w in wbs)
        first = wbs[0]
        preview_data.append([
            idx,
            first.license_plate,
            first.driver_name,
            first.transport_date,
            first.bamboo_type_name,
            len(wbs),
            format_weight(total_net),
            format_money(total_freight),
            ", ".join(w.waybill_no for w in wbs)
        ])

    print_table(
        preview_data,
        ["序号", "车牌", "司机", "日期", "竹种", "合并数", "总净重", "总运费", "运单号"],
        "可合并运单预览"
    )

    if list_only:
        click.echo("\n⚠️  list 模式，未执行合并操作")
        return

    if not yes:
        if not click.confirm(f"\n确认合并以上 {len(merge_candidates)} 组运单吗？"):
            click.echo("已取消")
            return

    merged_new: List[Waybill] = []
    merged_ids = set()

    for wbs in merge_candidates:
        first = wbs[0]
        merged = Waybill()

        merged.waybill_no = f"M{first.waybill_no}"
        merged.transport_date = first.transport_date
        merged.license_plate = first.license_plate
        merged.driver_id = first.driver_id
        merged.driver_name = first.driver_name
        merged.driver_phone = first.driver_phone
        merged.bamboo_type_id = first.bamboo_type_id
        merged.bamboo_type_name = first.bamboo_type_name
        merged.loading_point_id = first.loading_point_id
        merged.loading_point_name = first.loading_point_name
        merged.purchase_point_id = first.purchase_point_id
        merged.purchase_point_name = first.purchase_point_name
        merged.farmer_id = first.farmer_id
        merged.farmer_name = first.farmer_name
        merged.farmer_phone = first.farmer_phone
        merged.farmer_bank_account = first.farmer_bank_account
        merged.farmer_bank_name = first.farmer_bank_name

        for w in wbs:
            merged.gross_weight += w.gross_weight
            merged.tare_weight += w.tare_weight
            merged.net_weight += w.net_weight
            merged.freight += w.freight
            merged.bamboo_value += w.bamboo_value
            merged.farmer_amount += w.farmer_amount
            merged_ids.add(w.id)
            merged.merged_ids.append(w.id)

        if wbs:
            merged.mileage = sum(w.mileage for w in wbs) / len(wbs)
            merged.unit_price = first.unit_price

        merged.is_merged = True
        merged.weight_note_no = "+".join(w.weight_note_no for w in wbs if w.weight_note_no)
        merged.remark = f"合并 {len(wbs)} 条运单: " + ", ".join(w.waybill_no for w in wbs)
        merged.add_note(f"系统合并运单 {datetime.now().strftime('%Y-%m-%d %H:%M')}")

        merged_new.append(merged)

    all_waybills = store.load_waybills()
    remaining = []
    for w in all_waybills:
        if w.id in merged_ids:
            w.is_merged = True
            w.add_note(f"已被合并到运单组，合并时间 {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        remaining.append(w)

    remaining.extend(merged_new)
    store.save_waybills(remaining)

    click.echo(f"\n✅ 合并完成!")
    click.echo(f"  合并组: {len(merge_candidates)} 组")
    click.echo(f"  原始运单: {sum(len(g) for g in merge_candidates)} 条 (已标记为已合并)")
    click.echo(f"  新增合并运单: {len(merged_new)} 条")

    final_summary = []
    total_net = sum(w.net_weight for w in merged_new)
    total_freight = sum(w.freight for w in merged_new)
    total_bamboo = sum(w.bamboo_value for w in merged_new)
    final_summary.append(["合并总净重", format_weight(total_net)])
    final_summary.append(["合并总运费", format_money(total_freight)])
    final_summary.append(["合并总竹款", format_money(total_bamboo)])
    print_table(final_summary, ["统计项", "数值"], "合并结果汇总")

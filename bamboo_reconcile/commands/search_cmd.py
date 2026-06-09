"""search 命令 - 按日期查询异常、按条件搜索运单、记录人工备注"""
from typing import List, Dict, Any
from datetime import datetime
from collections import defaultdict

import click

from ..models import Waybill
from ..storage import DataStore
from ..utils import (
    print_table, format_money, format_weight, is_within_date_range,
    normalize_date
)


@click.group()
def search():
    """搜索运单与记录备注

    \b
    子命令:
      waybill   - 搜索运单
      exception - 按日期查询异常
      note      - 管理人工备注
      pending   - 搜索待处理事项
    """
    pass


@search.command("waybill")
@click.option("--keyword", default=None, help="关键词搜索（运单号/车牌/司机/竹农/磅单号）")
@click.option("--start-date", default=None, help="开始日期")
@click.option("--end-date", default=None, help="结束日期")
@click.option("--plate", default=None, help="车牌号")
@click.option("--driver", default=None, help="司机姓名")
@click.option("--farmer", default=None, help="竹农姓名")
@click.option("--bamboo", default=None, help="竹种")
@click.option("--loading", default=None, help="装车点")
@click.option("--purchase", default=None, help="收购点")
@click.option("--status", type=click.Choice(["all", "paid", "unpaid", "exception", "duplicate"]),
              default="all", help="状态筛选")
@click.option("--min-weight", type=float, default=None, help="最小净重(吨)")
@click.option("--max-weight", type=float, default=None, help="最大净重(吨)")
@click.option("--limit", type=int, default=50, help="显示结果数量，默认50")
@click.option("--detail", is_flag=True, help="显示运单详情")
@click.pass_context
def search_waybill(
    ctx, keyword, start_date, end_date, plate, driver, farmer,
    bamboo, loading, purchase, status, min_weight, max_weight, limit, detail
):
    """搜索运单

    \b
    示例:
      bamboo search waybill --keyword 川A12345
      bamboo search waybill --start-date 2024-01-01 --end-date 2024-01-15 --status exception
      bamboo search waybill --driver 张三 --bamboo 毛竹
      bamboo search waybill --keyword 张三 --detail
    """
    store: DataStore = ctx.obj["store"]
    waybills = store.load_waybills()

    if keyword:
        kw = keyword.lower()
        waybills = [w for w in waybills if
                    kw in (w.waybill_no or "").lower() or
                    kw in (w.license_plate or "").lower() or
                    kw in (w.driver_name or "").lower() or
                    kw in (w.farmer_name or "").lower() or
                    kw in (w.weight_note_no or "").lower()]

    if start_date and end_date:
        waybills = [w for w in waybills if is_within_date_range(w.transport_date, start_date, end_date)]
    elif start_date:
        waybills = [w for w in waybills if normalize_date(w.transport_date) >= normalize_date(start_date)]
    elif end_date:
        waybills = [w for w in waybills if normalize_date(w.transport_date) <= normalize_date(end_date)]

    if plate:
        waybills = [w for w in waybills if plate in (w.license_plate or "")]
    if driver:
        waybills = [w for w in waybills if driver in (w.driver_name or "")]
    if farmer:
        waybills = [w for w in waybills if farmer in (w.farmer_name or "")]
    if bamboo:
        waybills = [w for w in waybills if bamboo in (w.bamboo_type_name or "")]
    if loading:
        waybills = [w for w in waybills if loading in (w.loading_point_name or "")]
    if purchase:
        waybills = [w for w in waybills if purchase in (w.purchase_point_name or "")]

    if status == "paid":
        waybills = [w for w in waybills if w.is_paid]
    elif status == "unpaid":
        waybills = [w for w in waybills if not w.is_paid]
    elif status == "exception":
        waybills = [w for w in waybills if w.exceptions]
    elif status == "duplicate":
        waybills = [w for w in waybills if w.is_duplicate]

    if min_weight is not None:
        waybills = [w for w in waybills if w.net_weight >= min_weight]
    if max_weight is not None:
        waybills = [w for w in waybills if w.net_weight <= max_weight]

    if not waybills:
        click.echo("\n没有找到匹配的运单")
        return

    click.echo(f"\n找到 {len(waybills)} 条匹配运单 (显示前 {min(limit, len(waybills))} 条):")

    if detail:
        for i, w in enumerate(waybills[:limit]):
            click.echo(f"\n--- 运单 {i+1} / {min(limit, len(waybills))} ---")
            info = [
                ["运单号", w.waybill_no],
                ["ID", w.id],
                ["运输日期", w.transport_date],
                ["车牌号", w.license_plate],
                ["司机", f"{w.driver_name} ({w.driver_phone})" if w.driver_phone else w.driver_name],
                ["竹种", w.bamboo_type_name],
                ["装车点", w.loading_point_name],
                ["收购点", w.purchase_point_name],
                ["里程", f"{w.mileage} km"],
                ["毛重", format_weight(w.gross_weight)],
                ["皮重", format_weight(w.tare_weight)],
                ["净重", format_weight(w.net_weight)],
                ["磅单号", w.weight_note_no or "-"],
                ["单价", format_money(w.unit_price)],
                ["运费", format_money(w.freight)],
                ["竹款", format_money(w.bamboo_value)],
                ["合计", format_money(w.freight + w.bamboo_value)],
                ["竹农", f"{w.farmer_name} ({w.farmer_phone})" if w.farmer_name else "-"],
                ["付款状态", "已付款" if w.is_paid else "未付款"],
                ["已付金额", format_money(w.paid_amount)],
                ["付款日期", w.paid_date or "-"],
                ["异常", "; ".join(w.exceptions) if w.exceptions else "无"],
                ["是否合并", "是" if w.is_merged else "否"],
                ["是否拆分", "是" if w.is_split else "否"],
                ["是否重复", "是" if w.is_duplicate else "否"],
                ["系统备注", w.remark or "-"],
            ]
            print_table(info, ["项目", "内容"], title=f"运单详情 - {w.waybill_no}")

            if w.manual_notes:
                click.echo(f"  人工备注 ({len(w.manual_notes)} 条):")
                for idx, note in enumerate(w.manual_notes, 1):
                    click.echo(f"    {idx}. [{note.get('time', '')[:16]}] "
                               f"{note.get('operator', '')}: {note.get('content', '')}")
    else:
        data = []
        for i, w in enumerate(waybills[:limit]):
            status_str = []
            if w.is_paid:
                status_str.append("已付")
            if w.exceptions:
                status_str.append(f"异常{len(w.exceptions)}")
            if w.is_duplicate:
                status_str.append("重复")
            if w.is_merged:
                status_str.append("合并")
            if w.is_split:
                status_str.append("拆分")

            data.append([
                i + 1,
                w.waybill_no,
                w.transport_date,
                w.license_plate,
                w.driver_name,
                w.bamboo_type_name,
                format_weight(w.net_weight),
                f"{w.mileage:.0f}km" if w.mileage > 0 else "-",
                format_money(w.freight + w.bamboo_value),
                ", ".join(status_str) if status_str else "正常"
            ])

        print_table(
            data,
            ["序", "运单号", "日期", "车牌", "司机", "竹种", "净重", "里程", "金额", "状态"],
            f"搜索结果 (共{len(waybills)}条)"
        )

    if len(waybills) > limit:
        click.echo(f"  ... 还有 {len(waybills) - limit} 条未显示，使用 --limit {len(waybills)} 查看全部")


@search.command("exception")
@click.option("--start-date", required=True, help="开始日期")
@click.option("--end-date", required=True, help="结束日期")
@click.option("--type", "exc_type", default=None,
              help="异常类型筛选（如：车牌号/净重/装车点/重复/磅单 等关键词）")
@click.option("--fix", is_flag=True, help="进入交互式修复模式")
@click.pass_context
def search_exception(ctx, start_date: str, end_date: str, exc_type: str, fix: bool):
    """按日期范围查询异常运单

    \b
    示例:
      bamboo search exception --start-date 2024-01-01 --end-date 2024-01-31
      bamboo search exception --start-date 2024-01-01 --end-date 2024-01-31 --type 车牌号
      bamboo search exception --start-date 2024-01-01 --end-date 2024-01-31 --fix
    """
    store: DataStore = ctx.obj["store"]
    waybills = store.load_waybills()
    waybills = [w for w in waybills if is_within_date_range(w.transport_date, start_date, end_date)]

    exc_wbs = [w for w in waybills if w.exceptions]
    if exc_type:
        kw = exc_type.lower()
        exc_wbs = [w for w in exc_wbs if any(kw in e.lower() for e in w.exceptions)]

    if not exc_wbs:
        click.echo(f"\n✅ 在 {start_date} ~ {end_date} 期间没有异常运单！")
        return

    click.echo(f"\n异常运单统计: {start_date} ~ {end_date}")
    click.echo(f"  运单总数: {len(waybills)}")
    click.echo(f"  异常运单: {len(exc_wbs)} ({len(exc_wbs)/len(waybills)*100:.1f}%)")

    exc_counter = defaultdict(int)
    for w in exc_wbs:
        for exc in w.exceptions:
            simple = exc.split(":")[0] if ":" in exc else exc
            exc_counter[simple] += 1

    click.echo(f"\n异常类型分布:")
    for etype, count in sorted(exc_counter.items(), key=lambda x: -x[1]):
        pct = count / len(exc_wbs) * 100
        bar = "█" * int(pct / 5)
        click.echo(f"  {etype:20s}: {count:4d} 条 ({pct:5.1f}%) {bar}")

    data = []
    for idx, w in enumerate(sorted(exc_wbs, key=lambda x: (x.transport_date, x.waybill_no)), 1):
        data.append([
            idx,
            w.waybill_no,
            w.transport_date,
            w.license_plate,
            w.driver_name,
            format_weight(w.net_weight),
            len(w.exceptions),
            "; ".join(w.exceptions)[:60]
        ])

    print_table(
        data,
        ["序", "运单号", "日期", "车牌", "司机", "净重", "异常数", "异常描述"],
        f"异常运单清单 (共 {len(exc_wbs)} 条)"
    )

    if fix:
        _interactive_fix(store, exc_wbs)


def _interactive_fix(store: DataStore, exc_wbs: List[Waybill]):
    """交互式修复异常"""
    click.echo(f"\n进入交互式修复模式，共 {len(exc_wbs)} 条待处理")
    click.echo("操作: [n]下一条 [p]上一条 [f]修复当前 [s]跳过 [q]退出")

    idx = 0
    updated_count = 0
    while 0 <= idx < len(exc_wbs):
        w = exc_wbs[idx]
        click.echo(f"\n[{idx + 1}/{len(exc_wbs)}] 运单: {w.waybill_no}")
        click.echo(f"  日期: {w.transport_date}, 车牌: {w.license_plate}, 司机: {w.driver_name}")
        click.echo(f"  异常: {', '.join(w.exceptions)}")

        choice = click.prompt("操作", default="n", show_default=False).strip().lower()

        if choice == "q":
            break
        elif choice == "p":
            idx = max(0, idx - 1)
        elif choice == "s":
            idx += 1
        elif choice == "f":
            click.echo("  修复选项:")
            click.echo("    1) 清除所有异常标记")
            click.echo("    2) 添加备注后清除异常")
            click.echo("    3) 修改车牌号")
            click.echo("    4) 修改净重")
            click.echo("    5) 补充装车点")
            sub = click.prompt("选择", type=int, default=1)

            if sub == 1 or sub == 2:
                if sub == 2:
                    note = click.prompt("请输入备注", default="人工核查无异常")
                    w.add_note(note, "人工修复")
                w.exceptions = []
                w.add_note("人工清除异常标记", "人工修复")
                updated_count += 1
                idx += 1
            elif sub == 3:
                new_plate = click.prompt("新车牌号", default=w.license_plate)
                w.license_plate = new_plate
                w.exceptions = [e for e in w.exceptions if "车牌" not in e]
                w.add_note(f"修改车牌号为 {new_plate}", "人工修复")
                updated_count += 1
                idx += 1
            elif sub == 4:
                new_net = click.prompt("新净重(吨)", type=float, default=w.net_weight)
                w.net_weight = new_net
                w.exceptions = [e for e in w.exceptions if "净重" not in e and "重量" not in e]
                w.add_note(f"修改净重为 {new_net}吨", "人工修复")
                updated_count += 1
                idx += 1
            elif sub == 5:
                new_lp = click.prompt("装车点名称", default=w.loading_point_name)
                w.loading_point_name = new_lp
                lp = store.find_loading_point_by_name(new_lp)
                if lp:
                    w.loading_point_id = lp.id
                w.exceptions = [e for e in w.exceptions if "装车点" not in e]
                w.add_note(f"补充装车点: {new_lp}", "人工修复")
                updated_count += 1
                idx += 1
        else:
            idx += 1

    if updated_count > 0:
        store.update_waybills_batch(exc_wbs)
        click.echo(f"\n✅ 已修复 {updated_count} 条运单")
    else:
        click.echo("\n未修改任何运单")


@search.command("note")
@click.option("--id", "waybill_id", required=True, help="运单ID或运单号")
@click.option("--add", "add_note", default=None, help="添加备注内容")
@click.option("--list", "list_notes", is_flag=True, help="列出所有备注")
@click.option("--clear", is_flag=True, help="清除所有人工备注")
@click.option("--operator", default="财务", help="操作人姓名，默认'财务'")
@click.pass_context
def search_note(ctx, waybill_id: str, add_note: str, list_notes: bool, clear: bool, operator: str):
    """管理运单的人工备注

    \b
    示例:
      bamboo search note --id WB00123 --list
      bamboo search note --id WB00123 --add "司机确认无异常" --operator 李会计
      bamboo search note --id WB00123 --clear
    """
    store: DataStore = ctx.obj["store"]
    waybills = store.load_waybills()

    target = None
    for w in waybills:
        if w.id == waybill_id or w.waybill_no == waybill_id:
            target = w
            break

    if not target:
        click.echo(f"\n❌ 未找到运单: {waybill_id}", err=True)
        return

    if add_note:
        target.add_note(add_note, operator)
        store.update_waybill(target)
        click.echo(f"\n✅ 已添加备注到运单 {target.waybill_no}")
        click.echo(f"  [{datetime.now().strftime('%Y-%m-%d %H:%M')}] {operator}: {add_note}")
        return

    if clear:
        if click.confirm(f"\n确定要清除运单 {target.waybill_no} 的所有人工备注吗？"):
            target.manual_notes = []
            target.add_note("清除历史备注", operator)
            store.update_waybill(target)
            click.echo(f"\n✅ 已清除备注")
        return

    click.echo(f"\n运单 {target.waybill_no} 的人工备注:")
    if not target.manual_notes:
        click.echo("  (暂无备注)")
        return

    for idx, note in enumerate(target.manual_notes, 1):
        click.echo(f"  {idx}. [{note.get('time', '')[:19]}] "
                   f"{note.get('operator', '未知')}: {note.get('content', '')}")


@search.command("pending")
@click.option("--type", "pending_type",
              type=click.Choice(["all", "unpaid", "exception", "duplicate", "no_photo", "no_price"]),
              default="all", help="待处理类型")
@click.option("--start-date", default=None, help="开始日期")
@click.option("--end-date", default=None, help="结束日期")
@click.pass_context
def search_pending(ctx, pending_type: str, start_date: str, end_date: str):
    """搜索待处理事项

    \b
    待处理类型:
      all       - 全部待处理
      unpaid    - 未付款运单
      exception - 有异常的运单
      duplicate - 重复运单
      no_photo  - 缺少磅单照片
      no_price  - 未计算运费

    \b
    示例:
      bamboo search pending --type unpaid
      bamboo search pending --type exception --start-date 2024-01-01
    """
    store: DataStore = ctx.obj["store"]
    waybills = store.load_waybills()

    if start_date and end_date:
        waybills = [w for w in waybills if is_within_date_range(w.transport_date, start_date, end_date)]

    pending = []
    for w in waybills:
        match = False
        if pending_type == "all" and (not w.is_paid or w.exceptions or w.is_duplicate or not w.weight_note_photo or w.freight <= 0):
            match = True
        elif pending_type == "unpaid" and not w.is_paid:
            match = True
        elif pending_type == "exception" and w.exceptions:
            match = True
        elif pending_type == "duplicate" and w.is_duplicate:
            match = True
        elif pending_type == "no_photo" and w.weight_note_no and not w.weight_note_photo:
            match = True
        elif pending_type == "no_price" and w.net_weight > 0 and w.freight <= 0:
            match = True

        if match:
            pending.append(w)

    if not pending:
        click.echo(f"\n✅ 没有找到待处理事项")
        return

    click.echo(f"\n找到 {len(pending)} 条待处理事项:")

    type_map = {
        "unpaid": "未付款",
        "exception": "有异常",
        "duplicate": "重复运单",
        "no_photo": "缺照片",
        "no_price": "未计价"
    }

    data = []
    for idx, w in enumerate(pending[:30], 1):
        tags = []
        if not w.is_paid:
            tags.append("未付款")
        if w.exceptions:
            tags.append(f"异常{len(w.exceptions)}")
        if w.is_duplicate:
            tags.append("重复")
        if w.weight_note_no and not w.weight_note_photo:
            tags.append("缺照片")
        if w.net_weight > 0 and w.freight <= 0:
            tags.append("未计价")

        data.append([
            idx,
            w.waybill_no,
            w.transport_date,
            w.license_plate,
            w.driver_name,
            format_weight(w.net_weight),
            format_money(w.freight + w.bamboo_value),
            ", ".join(tags)
        ])

    print_table(
        data,
        ["序", "运单号", "日期", "车牌", "司机", "净重", "金额", "待处理"],
        f"待处理事项 (共{len(pending)}条)"
    )

    if len(pending) > 30:
        click.echo(f"  ... 还有 {len(pending) - 30} 条未显示")

    counter = defaultdict(int)
    for w in pending:
        if not w.is_paid:
            counter["未付款"] += 1
        if w.exceptions:
            counter["有异常"] += 1
        if w.is_duplicate:
            counter["重复运单"] += 1
        if w.weight_note_no and not w.weight_note_photo:
            counter["缺磅单照片"] += 1
        if w.net_weight > 0 and w.freight <= 0:
            counter["未计算运费"] += 1

    click.echo(f"\n分类统计:")
    for k, v in sorted(counter.items(), key=lambda x: -x[1]):
        click.echo(f"  {k}: {v} 条")

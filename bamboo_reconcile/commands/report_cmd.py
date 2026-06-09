"""report 命令 - 生成对账报表、按收购点汇总吨数、打印待补资料列表"""
import os
from typing import List, Dict, Any
from collections import defaultdict
from datetime import datetime

import click

from ..models import Waybill
from ..storage import DataStore
from ..utils import (
    print_table, format_money, format_weight, is_within_date_range,
    normalize_date, export_to_excel, filter_effective_waybills
)


@click.group()
def report():
    """对账报表生成

    \b
    子命令:
      summary     - 综合对账报表
      purchase    - 按收购点汇总吨数
      loading     - 按装车点汇总
      bamboo      - 按竹种汇总
      driver      - 按司机运输汇总
      pending     - 待补资料列表
      daily       - 日报表
    """
    pass


@report.command("summary")
@click.option("--start-date", required=True, help="开始日期 (YYYY-MM-DD)")
@click.option("--end-date", required=True, help="结束日期 (YYYY-MM-DD)")
@click.option("--by", "group_by",
              type=click.Choice(["day", "week", "month", "purchase", "loading", "bamboo", "driver"]),
              default="day", help="汇总维度")
@click.option("--diff", is_flag=True, help="显示对账差异视图（已付/未付/异常/缺照片 分开统计）")
@click.option("--export", "export_path", default=None, help="导出 Excel 文件路径")
@click.pass_context
def report_summary(ctx, start_date: str, end_date: str, group_by: str, diff: bool, export_path: str):
    """生成综合对账报表

    \b
    示例:
      bamboo report summary --start-date 2024-01-01 --end-date 2024-01-31 --by day
      bamboo report summary --start-date 2024-01-01 --end-date 2024-01-31 --by purchase --diff
      bamboo report summary --start-date 2024-01-01 --end-date 2024-03-31 --by month --export Q1报表.xlsx
    """
    store: DataStore = ctx.obj["store"]
    waybills = store.load_waybills()
    waybills = [w for w in waybills if is_within_date_range(w.transport_date, start_date, end_date)]
    waybills = filter_effective_waybills(waybills)

    if not waybills:
        click.echo("\n该日期范围内没有运单数据")
        return

    click.echo(f"\n综合对账报表: {start_date} ~ {end_date}")
    click.echo(f"运单总数: {len(waybills)} 条")

    groups: Dict[str, List[Waybill]] = defaultdict(list)

    for w in waybills:
        dt = normalize_date(w.transport_date)
        if group_by == "day":
            key = dt
        elif group_by == "week":
            try:
                d = datetime.strptime(dt, "%Y-%m-%d")
                key = f"{d.isocalendar()[0]}年第{d.isocalendar()[1]}周"
            except Exception:
                key = dt[:7]
        elif group_by == "month":
            key = dt[:7]
        elif group_by == "purchase":
            key = w.purchase_point_name or "未知收购点"
        elif group_by == "loading":
            key = w.loading_point_name or "未知装车点"
        elif group_by == "bamboo":
            key = w.bamboo_type_name or "未知竹种"
        elif group_by == "driver":
            key = w.driver_name or "未知司机"
        else:
            key = dt
        groups[key].append(w)

    def _calc_diff(wbs: List[Waybill]) -> Dict[str, Any]:
        """计算差异视图统计数据"""
        paid_wbs = [w for w in wbs if w.is_paid]
        unpaid_wbs = [w for w in wbs if not w.is_paid]
        exc_wbs = [w for w in wbs if w.exceptions]
        no_photo_wbs = [w for w in wbs if w.weight_note_no and not w.weight_note_photo]
        no_price_wbs = [w for w in wbs if w.net_weight > 0 and w.freight <= 0]
        return {
            "paid": {
                "count": len(paid_wbs),
                "weight": round(sum(w.net_weight for w in paid_wbs), 3),
                "amount": round(sum(w.freight + w.bamboo_value for w in paid_wbs), 2),
            },
            "unpaid": {
                "count": len(unpaid_wbs),
                "weight": round(sum(w.net_weight for w in unpaid_wbs), 3),
                "amount": round(sum(w.freight + w.bamboo_value for w in unpaid_wbs), 2),
            },
            "exception": {
                "count": len(exc_wbs),
                "weight": round(sum(w.net_weight for w in exc_wbs), 3),
                "amount": round(sum(w.freight + w.bamboo_value for w in exc_wbs), 2),
            },
            "no_photo": {
                "count": len(no_photo_wbs),
                "weight": round(sum(w.net_weight for w in no_photo_wbs), 3),
                "amount": round(sum(w.freight + w.bamboo_value for w in no_photo_wbs), 2),
            },
            "no_price": {
                "count": len(no_price_wbs),
                "weight": round(sum(w.net_weight for w in no_price_wbs), 3),
                "amount": round(sum(w.freight + w.bamboo_value for w in no_price_wbs), 2),
            },
        }

    data = []
    export_data = []
    diff_export_rows = []
    diff_data = []

    for idx, (key, wbs) in enumerate(sorted(groups.items()), 1):
        count = len(wbs)
        vehicles = len(set(w.license_plate for w in wbs if w.license_plate))
        drivers = len(set(w.driver_name for w in wbs if w.driver_name))
        total_net = sum(w.net_weight for w in wbs)
        total_gross = sum(w.gross_weight for w in wbs)
        total_freight = sum(w.freight for w in wbs)
        total_bamboo = sum(w.bamboo_value for w in wbs)
        total_amount = total_freight + total_bamboo
        avg_mileage = sum(w.mileage for w in wbs) / count if count > 0 else 0

        paid = [w for w in wbs if w.is_paid]
        paid_count = len(paid)
        paid_amount = sum(w.paid_amount for w in paid)
        unpaid_count = count - paid_count
        unpaid_amount = total_amount - paid_amount

        exc_count = sum(1 for w in wbs if w.exceptions)

        data.append([
            idx, key, count, vehicles, drivers,
            format_weight(total_net),
            format_money(total_freight),
            format_money(total_bamboo),
            format_money(total_amount),
            f"{paid_count}/{unpaid_count}",
            exc_count if exc_count > 0 else "-"
        ])

        export_data.append({
            "分组": key,
            "运单数": count,
            "车辆数": vehicles,
            "司机数": drivers,
            "总毛重(吨)": round(total_gross, 3),
            "总净重(吨)": round(total_net, 3),
            "平均里程(km)": round(avg_mileage, 1),
            "运费合计(元)": round(total_freight, 2),
            "竹款合计(元)": round(total_bamboo, 2),
            "总计(元)": round(total_amount, 2),
            "已付款单数": paid_count,
            "未付款单数": unpaid_count,
            "已付款金额": round(paid_amount, 2),
            "未付款金额": round(unpaid_amount, 2),
            "异常单数": exc_count,
        })

        d = _calc_diff(wbs)
        diff_export_rows.append({
            "分组": key,
            "类别": "已付款", "单数": d["paid"]["count"],
            "净重(吨)": d["paid"]["weight"], "金额(元)": d["paid"]["amount"],
        })
        diff_export_rows.append({
            "分组": key,
            "类别": "未付款", "单数": d["unpaid"]["count"],
            "净重(吨)": d["unpaid"]["weight"], "金额(元)": d["unpaid"]["amount"],
        })
        diff_export_rows.append({
            "分组": key,
            "类别": "异常单", "单数": d["exception"]["count"],
            "净重(吨)": d["exception"]["weight"], "金额(元)": d["exception"]["amount"],
        })
        diff_export_rows.append({
            "分组": key,
            "类别": "缺磅单照片", "单数": d["no_photo"]["count"],
            "净重(吨)": d["no_photo"]["weight"], "金额(元)": d["no_photo"]["amount"],
        })
        diff_export_rows.append({
            "分组": key,
            "类别": "未计价", "单数": d["no_price"]["count"],
            "净重(吨)": d["no_price"]["weight"], "金额(元)": d["no_price"]["amount"],
        })
        diff_data.append((key, d))

    headers_map = {
        "day": "日期", "week": "周", "month": "月份",
        "purchase": "收购点", "loading": "装车点",
        "bamboo": "竹种", "driver": "司机"
    }
    header_name = headers_map.get(group_by, "分组")

    print_table(
        data,
        ["序", header_name, "单数", "车辆", "司机", "总净重", "运费", "竹款", "合计", "付款状态", "异常"],
        f"对账报表 - 按{header_name}汇总 (共 {len(groups)} 组)"
    )

    total_count = len(waybills)
    total_weight = sum(w.net_weight for w in waybills)
    total_freight = sum(w.freight for w in waybills)
    total_bamboo = sum(w.bamboo_value for w in waybills)
    total_amount = total_freight + total_bamboo
    paid_count = sum(1 for w in waybills if w.is_paid)
    exc_total = sum(1 for w in waybills if w.exceptions)

    grand = [
        ["运单总数", f"{total_count} 条"],
        ["车辆数", f"{len(set(w.license_plate for w in waybills if w.license_plate))} 辆"],
        ["司机数", f"{len(set(w.driver_name for w in waybills if w.driver_name))} 人"],
        ["总毛重", format_weight(sum(w.gross_weight for w in waybills))],
        ["总净重", format_weight(total_weight)],
        ["运费合计", format_money(total_freight)],
        ["竹款合计", format_money(total_bamboo)],
        ["总计金额", format_money(total_amount)],
        ["已付款", f"{paid_count} 条 / {format_money(sum(w.paid_amount for w in waybills if w.is_paid))}"],
        ["未付款", f"{total_count - paid_count} 条 / {format_money(total_amount - sum(w.paid_amount for w in waybills if w.is_paid))}"],
        ["有异常", f"{exc_total} 条"],
    ]
    print_table(grand, ["项目", "数值"], "总计")

    overall_diff = _calc_diff(waybills)
    if diff:
        diff_rows = []
        categories = [
            ("已付款", "paid", "✅"),
            ("未付款", "unpaid", "⏳"),
            ("异常单", "exception", "⚠️"),
            ("缺磅单照片", "no_photo", "📷"),
            ("未计价", "no_price", "💲"),
        ]
        for cat_name, cat_key, icon in categories:
            cd = overall_diff[cat_key]
            diff_rows.append([
                f"{icon} {cat_name}",
                f"{cd['count']} 条",
                format_weight(cd['weight']),
                format_money(cd['amount']),
                f"{cd['count'] / total_count * 100:.1f}%" if total_count > 0 else "0%"
            ])
        print_table(
            diff_rows,
            ["分类", "单数", "总净重", "总金额", "占比"],
            f"对账差异视图 - 整体({header_name}维度分组)"
        )

        if len(diff_data) > 1:
            per_group_rows = []
            for key, d in diff_data:
                row = [key[:14]]
                for _, ck, _ in categories:
                    cnt = d[ck]["count"]
                    if cnt > 0:
                        row.append(f"{cnt}条/{format_money(d[ck]['amount'])}")
                    else:
                        row.append("-")
                per_group_rows.append(row)
            print_table(
                per_group_rows,
                [header_name[:6], "已付款", "未付款", "异常", "缺照片", "未计价"],
                f"各{header_name}差异概览 (单数/金额)"
            )

    if export_path or True:
        if not export_path:
            suffix = ""
            if diff:
                suffix = "_含差异视图"
            export_path = f"对账报表_{start_date}_{end_date}_按{header_name}{suffix}.xlsx"
        if not os.path.isabs(export_path):
            export_path = os.path.join(store.get_report_dir(), export_path)

        import pandas as pd
        os.makedirs(os.path.dirname(export_path), exist_ok=True)

        extra_dims = {}
        if group_by != "driver":
            dim_wbs: Dict[str, List[Waybill]] = defaultdict(list)
            for w in waybills:
                dim_wbs[w.driver_name or "未知司机"].append(w)
            extra_dims["差异_按司机"] = dim_wbs
        if group_by != "purchase":
            dim_wbs = defaultdict(list)
            for w in waybills:
                dim_wbs[w.purchase_point_name or "未知收购点"].append(w)
            extra_dims["差异_按收购点"] = dim_wbs
        if group_by != "bamboo":
            dim_wbs = defaultdict(list)
            for w in waybills:
                dim_wbs[w.bamboo_type_name or "未知竹种"].append(w)
            extra_dims["差异_按竹种"] = dim_wbs

        total_sheets = 2 + (1 if diff_export_rows else 0) + len(extra_dims)
        with click.progressbar(length=total_sheets, label="导出对账报表") as bar:
            with pd.ExcelWriter(export_path, engine="openpyxl") as writer:
                pd.DataFrame(export_data).to_excel(writer, sheet_name="汇总数据", index=False)
                bar.update(1)

                detail = []
                for w in waybills:
                    detail.append({
                        "运单号": w.waybill_no,
                        "运输日期": w.transport_date,
                        "车牌号": w.license_plate,
                        "司机": w.driver_name,
                        "竹种": w.bamboo_type_name,
                        "装车点": w.loading_point_name,
                        "收购点": w.purchase_point_name,
                        "里程(km)": w.mileage,
                        "毛重(吨)": round(w.gross_weight, 3),
                        "皮重(吨)": round(w.tare_weight, 3),
                        "净重(吨)": round(w.net_weight, 3),
                        "运费(元)": round(w.freight, 2),
                        "竹款(元)": round(w.bamboo_value, 2),
                        "合计(元)": round(w.freight + w.bamboo_value, 2),
                        "竹农": w.farmer_name,
                        "磅单号": w.weight_note_no,
                        "付款状态": "已付款" if w.is_paid else "未付款",
                        "已付金额": round(w.paid_amount, 2),
                        "异常数": len(w.exceptions),
                        "异常描述": "; ".join(w.exceptions) if w.exceptions else "",
                        "有磅单照片": "是" if w.weight_note_photo else "否",
                        "备注": w.remark,
                    })
                pd.DataFrame(detail).to_excel(writer, sheet_name="运单明细", index=False)
                bar.update(1)

                if diff_export_rows:
                    diff_df = pd.DataFrame(diff_export_rows)
                    diff_df.to_excel(writer, sheet_name=f"差异_按{header_name}", index=False)
                    bar.update(1)

                    overall_rows = []
                    categories = ["已付款", "未付款", "异常单", "缺磅单照片", "未计价"]
                    keys = ["paid", "unpaid", "exception", "no_photo", "no_price"]
                    for cat, k in zip(categories, keys):
                        overall_rows.append({
                            "分组": "【整体合计】",
                            "类别": cat,
                            "单数": overall_diff[k]["count"],
                            "净重(吨)": overall_diff[k]["weight"],
                            "金额(元)": overall_diff[k]["amount"],
                        })
                    pd.DataFrame(overall_rows).to_excel(
                        writer, sheet_name=f"差异_按{header_name}",
                        index=False, startrow=len(diff_df) + 3
                    )

                for sheet_name, dim_map in extra_dims.items():
                    dim_rows = []
                    for key, wbs in sorted(dim_map.items()):
                        d = _calc_diff(wbs)
                        for cat, k in zip(categories, keys):
                            dim_rows.append({
                                "分组": key,
                                "类别": cat,
                                "单数": d[k]["count"],
                                "净重(吨)": d[k]["weight"],
                                "金额(元)": d[k]["amount"],
                            })
                    pd.DataFrame(dim_rows).to_excel(writer, sheet_name=sheet_name, index=False)
                    bar.update(1)

        click.echo(f"\n✅ 对账报表已导出: {export_path}")
        click.echo(f"   Sheet: 汇总数据 + 运单明细 + 差异视图({1 + len(extra_dims)}个维度)")


@report.command("purchase")
@click.option("--start-date", required=True, help="开始日期")
@click.option("--end-date", required=True, help="结束日期")
@click.option("--bamboo", default=None, help="按竹种筛选")
@click.option("--export", "export_path", default=None, help="导出 Excel")
@click.pass_context
def report_purchase(ctx, start_date: str, end_date: str, bamboo: str, export_path: str):
    """按收购点汇总吨数

    \b
    示例:
      bamboo report purchase --start-date 2024-01-01 --end-date 2024-01-31
      bamboo report purchase --start-date 2024-01-01 --end-date 2024-01-31 --bamboo 毛竹
    """
    store: DataStore = ctx.obj["store"]
    waybills = store.load_waybills()
    waybills = [w for w in waybills if is_within_date_range(w.transport_date, start_date, end_date)]
    waybills = filter_effective_waybills(waybills)
    if bamboo:
        waybills = [w for w in waybills if bamboo in (w.bamboo_type_name or "")]

    if not waybills:
        click.echo("\n没有数据")
        return

    groups: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "count": 0, "net": 0.0, "gross": 0.0,
        "bamboos": defaultdict(float), "freight": 0.0, "bamboo_value": 0.0
    })

    for w in waybills:
        key = w.purchase_point_name or "未知收购点"
        g = groups[key]
        g["count"] += 1
        g["net"] += w.net_weight
        g["gross"] += w.gross_weight
        g["freight"] += w.freight
        g["bamboo_value"] += w.bamboo_value
        bamboo_name = w.bamboo_type_name or "未知"
        g["bamboos"][bamboo_name] += w.net_weight

    data = []
    export_data = []
    bamboo_types = sorted(set(bt for g in groups.values() for bt in g["bamboos"].keys()))

    for idx, (name, g) in enumerate(sorted(groups.items(), key=lambda x: -x[1]["net"]), 1):
        bamboo_str = ", ".join(f"{bt}:{format_weight(g['bamboos'][bt])}" for bt in bamboo_types if g["bamboos"][bt] > 0)
        data.append([
            idx, name, g["count"],
            format_weight(g["gross"]), format_weight(g["net"]),
            bamboo_str,
            format_money(g["freight"]), format_money(g["bamboo_value"]),
            format_money(g["freight"] + g["bamboo_value"])
        ])
        row = {"收购点": name, "运单数": g["count"],
               "总毛重(吨)": round(g["gross"], 3), "总净重(吨)": round(g["net"], 3),
               "运费(元)": round(g["freight"], 2), "竹款(元)": round(g["bamboo_value"], 2),
               "合计(元)": round(g["freight"] + g["bamboo_value"], 2)}
        for bt in bamboo_types:
            row[f"{bt}(吨)"] = round(g["bamboos"][bt], 3)
        export_data.append(row)

    headers = ["序", "收购点", "单数", "总毛重", "总净重"] + bamboo_types + ["运费", "竹款", "合计"]
    table_data = []
    for idx, (name, g) in enumerate(sorted(groups.items(), key=lambda x: -x[1]["net"]), 1):
        row = [idx, name, g["count"], format_weight(g["gross"]), format_weight(g["net"])]
        for bt in bamboo_types:
            row.append(format_weight(g["bamboos"][bt]) if g["bamboos"][bt] > 0 else "-")
        row.extend([format_money(g["freight"]), format_money(g["bamboo_value"]),
                    format_money(g["freight"] + g["bamboo_value"])])
        table_data.append(row)

    print_table(table_data, headers, f"按收购点汇总 (共 {len(groups)} 个)")

    total_w = sum(w.net_weight for w in waybills)
    total_g = sum(w.gross_weight for w in waybills)
    grand = [
        ["收购点数", f"{len(groups)} 个"],
        ["运单总数", f"{len(waybills)} 条"],
        ["总毛重", format_weight(total_g)],
        ["总净重", format_weight(total_w)],
        ["运费合计", format_money(sum(w.freight for w in waybills))],
        ["竹款合计", format_money(sum(w.bamboo_value for w in waybills))],
    ]
    print_table(grand, ["项目", "数值"], "总计")

    if export_path:
        if not os.path.isabs(export_path):
            export_path = os.path.join(store.get_report_dir(), export_path)
        export_to_excel(export_data, export_path, sheet_name="收购点汇总")
        click.echo(f"\n✅ 已导出: {export_path}")


@report.command("loading")
@click.option("--start-date", required=True, help="开始日期")
@click.option("--end-date", required=True, help="结束日期")
@click.pass_context
def report_loading(ctx, start_date: str, end_date: str):
    """按装车点汇总运输量

    \b
    示例:
      bamboo report loading --start-date 2024-01-01 --end-date 2024-01-31
    """
    store: DataStore = ctx.obj["store"]
    waybills = store.load_waybills()
    waybills = [w for w in waybills if is_within_date_range(w.transport_date, start_date, end_date)]
    waybills = filter_effective_waybills(waybills)

    if not waybills:
        click.echo("\n没有数据")
        return

    groups = defaultdict(lambda: {"count": 0, "net": 0.0, "drivers": set(), "vehicles": set()})

    for w in waybills:
        key = w.loading_point_name or "未知装车点"
        g = groups[key]
        g["count"] += 1
        g["net"] += w.net_weight
        if w.driver_name:
            g["drivers"].add(w.driver_name)
        if w.license_plate:
            g["vehicles"].add(w.license_plate)

    data = []
    for idx, (name, g) in enumerate(sorted(groups.items(), key=lambda x: -x[1]["net"]), 1):
        data.append([
            idx, name, g["count"],
            len(g["vehicles"]), len(g["drivers"]),
            format_weight(g["net"]),
            format_weight(g["net"] / g["count"]) if g["count"] > 0 else "-"
        ])

    print_table(
        data,
        ["序", "装车点", "单数", "车辆数", "司机数", "总净重", "平均单重"],
        f"按装车点汇总 (共 {len(groups)} 个)"
    )


@report.command("bamboo")
@click.option("--start-date", required=True, help="开始日期")
@click.option("--end-date", required=True, help="结束日期")
@click.pass_context
def report_bamboo(ctx, start_date: str, end_date: str):
    """按竹种汇总运输量和金额

    \b
    示例:
      bamboo report bamboo --start-date 2024-01-01 --end-date 2024-01-31
    """
    store: DataStore = ctx.obj["store"]
    waybills = store.load_waybills()
    waybills = [w for w in waybills if is_within_date_range(w.transport_date, start_date, end_date)]
    waybills = filter_effective_waybills(waybills)

    if not waybills:
        click.echo("\n没有数据")
        return

    groups = defaultdict(lambda: {
        "count": 0, "net": 0.0, "gross": 0.0,
        "freight": 0.0, "bamboo_value": 0.0,
        "farmer_count": set()
    })

    for w in waybills:
        key = w.bamboo_type_name or "未知竹种"
        g = groups[key]
        g["count"] += 1
        g["net"] += w.net_weight
        g["gross"] += w.gross_weight
        g["freight"] += w.freight
        g["bamboo_value"] += w.bamboo_value
        if w.farmer_name:
            g["farmer_count"].add(w.farmer_name)

    data = []
    total_amount = 0
    for idx, (name, g) in enumerate(sorted(groups.items(), key=lambda x: -x[1]["net"]), 1):
        total = g["freight"] + g["bamboo_value"]
        total_amount += total
        unit_price = (g["bamboo_value"] / g["net"]) if g["net"] > 0 else 0
        data.append([
            idx, name, g["count"],
            format_weight(g["net"]),
            format_money(unit_price),
            format_money(g["freight"]),
            format_money(g["bamboo_value"]),
            format_money(total),
            len(g["farmer_count"])
        ])

    print_table(
        data,
        ["序", "竹种", "单数", "总净重", "平均单价", "运费", "竹款", "合计", "竹农户数"],
        f"按竹种汇总 (共 {len(groups)} 种)"
    )

    click.echo(f"\n总金额: {format_money(total_amount)}")


@report.command("driver")
@click.option("--start-date", required=True, help="开始日期")
@click.option("--end-date", required=True, help="结束日期")
@click.option("--top", type=int, default=10, help="显示前N名，默认10")
@click.pass_context
def report_driver(ctx, start_date: str, end_date: str, top: int):
    """按司机运输量排行

    \b
    示例:
      bamboo report driver --start-date 2024-01-01 --end-date 2024-01-31 --top 20
    """
    store: DataStore = ctx.obj["store"]
    waybills = store.load_waybills()
    waybills = [w for w in waybills if is_within_date_range(w.transport_date, start_date, end_date)]
    waybills = filter_effective_waybills(waybills)

    if not waybills:
        click.echo("\n没有数据")
        return

    groups = defaultdict(lambda: {
        "count": 0, "net": 0.0, "trips": 0,
        "plates": set(), "freight": 0.0, "mileage_sum": 0.0
    })

    for w in waybills:
        key = w.driver_name or "未知司机"
        g = groups[key]
        g["count"] += 1
        g["net"] += w.net_weight
        g["freight"] += w.freight
        g["mileage_sum"] += w.mileage * w.net_weight
        if w.license_plate:
            g["plates"].add(w.license_plate)

    sorted_groups = sorted(groups.items(), key=lambda x: -x[1]["net"])[:top]

    data = []
    for idx, (name, g) in enumerate(sorted_groups, 1):
        avg_mileage = (g["mileage_sum"] / g["net"]) if g["net"] > 0 else 0
        data.append([
            idx, name, len(g["plates"]), g["count"],
            format_weight(g["net"]),
            format_weight(g["net"] / g["count"]) if g["count"] > 0 else "-",
            f"{avg_mileage:.1f}km",
            format_money(g["freight"])
        ])

    print_table(
        data,
        ["排名", "司机", "车辆数", "趟数", "总净重", "均重/趟", "平均里程", "运费合计"],
        f"司机运输排行 (前{len(sorted_groups)}名)"
    )


@report.command("pending")
@click.option("--start-date", default=None, help="开始日期 (可选)")
@click.option("--end-date", default=None, help="结束日期 (可选)")
@click.option("--export", "export_path", default=None, help="导出 Excel 文件路径")
@click.pass_context
def report_pending(ctx, start_date: str, end_date: str, export_path: str):
    """打印待补资料列表

    \b
    待补资料包括：
      - 缺少装车点记录
      - 缺少磅单号/磅单照片
      - 缺少司机信息
      - 重量异常
      - 未匹配磅单照片
      - 重复运单待确认

    \b
    示例:
      bamboo report pending
      bamboo report pending --start-date 2024-01-01 --end-date 2024-01-31 --export 待补资料.xlsx
    """
    store: DataStore = ctx.obj["store"]
    waybills = store.load_waybills()
    waybills = filter_effective_waybills(waybills)

    if start_date and end_date:
        waybills = [w for w in waybills if is_within_date_range(w.transport_date, start_date, end_date)]

    pending_items = []

    for w in waybills:
        items = []

        if not w.loading_point_id and not w.loading_point_name:
            items.append("缺少装车点")
        elif w.loading_point_name and not w.loading_point_id:
            items.append("装车点未建档")

        if not w.weight_note_no:
            items.append("缺少磅单号")

        if w.weight_note_no and not w.weight_note_photo:
            items.append("缺少磅单照片")

        if not w.driver_name:
            items.append("缺少司机姓名")
        if not w.license_plate:
            items.append("缺少车牌号")

        if w.gross_weight > 0 and w.tare_weight > 0 and w.net_weight > 0:
            calc = round(w.gross_weight - w.tare_weight, 3)
            if abs(calc - w.net_weight) > 0.01:
                items.append(f"重量不符(记{w.net_weight}/算{calc})")

        if w.is_duplicate:
            items.append("重复运单待确认")

        if not w.farmer_name and w.bamboo_value > 0:
            items.append("缺少竹农信息")

        if w.freight <= 0 and w.net_weight > 0:
            items.append("未计算运费")

        for exc in w.exceptions:
            if exc not in items and "缺少" in exc or "异常" in exc or "不符" in exc:
                if exc not in items:
                    items.append(exc)

        if items:
            pending_items.append({
                "运单号": w.waybill_no,
                "日期": w.transport_date,
                "车牌": w.license_plate,
                "司机": w.driver_name,
                "竹种": w.bamboo_type_name,
                "净重": f"{w.net_weight:.3f}" if w.net_weight > 0 else "-",
                "待补项目": "; ".join(items),
            })

    if not pending_items:
        click.echo("\n✅ 太棒了！没有待补资料")
        return

    click.echo(f"\n待补资料列表 (共 {len(pending_items)} 条运单需要补充):")

    sorted_items = sorted(pending_items, key=lambda x: (x["日期"] or "", x["运单号"]))
    data = [[i + 1] + [list(item.values())[j] for j in range(len(item))]
            for i, item in enumerate(sorted_items[:50])]
    headers = ["序"] + list(pending_items[0].keys())
    print_table(data, headers, f"待补资料清单 (前50条)")

    if len(pending_items) > 50:
        click.echo(f"  ... 还有 {len(pending_items) - 50} 条，请导出查看完整列表")

    counter = defaultdict(int)
    for item in pending_items:
        for p in item["待补项目"].split("; "):
            counter[p] += 1

    click.echo(f"\n待补项目统计:")
    for item, count in sorted(counter.items(), key=lambda x: -x[1]):
        click.echo(f"  {item}: {count} 条")

    if export_path or True:
        if not export_path:
            suffix = f"_{start_date}_{end_date}" if start_date else ""
            export_path = f"待补资料清单{suffix}.xlsx"
        if not os.path.isabs(export_path):
            export_path = os.path.join(store.get_report_dir(), export_path)
        export_to_excel(pending_items, export_path, sheet_name="待补资料")
        click.echo(f"\n✅ 待补资料清单已导出: {export_path}")


@report.command("daily")
@click.option("--date", "report_date", default=None, help="报表日期 (YYYY-MM-DD)，默认今天")
@click.pass_context
def report_daily(ctx, report_date: str):
    """生成日报表

    \b
    示例:
      bamboo report daily
      bamboo report daily --date 2024-01-15
    """
    store: DataStore = ctx.obj["store"]
    if not report_date:
        report_date = datetime.now().strftime("%Y-%m-%d")

    waybills = store.load_waybills()
    waybills = [w for w in waybills if normalize_date(w.transport_date) == report_date]
    waybills = filter_effective_waybills(waybills)

    click.echo(f"\n{'=' * 60}")
    click.echo(f"  竹子运输日报表 - {report_date}")
    click.echo(f"{'=' * 60}")

    if not waybills:
        click.echo("\n  当日无运单记录")
        return

    total_count = len(waybills)
    total_net = sum(w.net_weight for w in waybills)
    total_gross = sum(w.gross_weight for w in waybills)
    total_freight = sum(w.freight for w in waybills)
    total_bamboo = sum(w.bamboo_value for w in waybills)
    vehicles = len(set(w.license_plate for w in waybills if w.license_plate))
    drivers = len(set(w.driver_name for w in waybills if w.driver_name))
    points = len(set(w.purchase_point_name for w in waybills if w.purchase_point_name))

    summary = [
        ["运单总数", f"{total_count} 条"],
        ["运输车辆", f"{vehicles} 辆"],
        ["司机人数", f"{drivers} 人"],
        ["收购点数", f"{points} 个"],
        ["总毛重", format_weight(total_gross)],
        ["总净重", format_weight(total_net)],
        ["运费合计", format_money(total_freight)],
        ["竹款合计", format_money(total_bamboo)],
        ["当日总额", format_money(total_freight + total_bamboo)],
    ]
    print_table(summary, ["项目", "数值"], "当日概览")

    bamboo_groups = defaultdict(float)
    for w in waybills:
        bamboo_groups[w.bamboo_type_name or "未知"] += w.net_weight

    bamboo_data = [[i + 1, bt, format_weight(wt)]
                   for i, (bt, wt) in enumerate(sorted(bamboo_groups.items(), key=lambda x: -x[1]))]
    print_table(bamboo_data, ["序", "竹种", "净重"], "竹种分布")

    driver_groups = defaultdict(lambda: [0, 0.0])
    for w in waybills:
        key = f"{w.driver_name or '未知'}({w.license_plate or '无牌'})"
        driver_groups[key][0] += 1
        driver_groups[key][1] += w.net_weight

    driver_data = [[i + 1, name, d[0], format_weight(d[1])]
                   for i, (name, d) in enumerate(sorted(driver_groups.items(), key=lambda x: -x[1][1]))]
    print_table(driver_data, ["序", "司机(车牌)", "趟数", "运输总量"], "当日司机运输")

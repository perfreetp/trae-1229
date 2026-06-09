"""settle 命令 - 标记已付款、生成司机结算单、生成竹农付款清单"""
import os
from typing import List, Dict, Any
from collections import defaultdict
from datetime import datetime

import click

from ..models import Waybill, Settlement, Driver
from ..storage import DataStore
from ..utils import (
    print_table, format_money, format_weight, is_within_date_range,
    normalize_date, export_to_excel, generate_serial_no, filter_effective_waybills
)


@click.group()
def settle():
    """结算管理 - 标记付款、生成司机结算单和竹农付款清单

    \b
    子命令:
      driver    - 生成司机结算单
      farmer    - 生成竹农付款清单
      pay       - 标记运单已付款
      unpaid    - 查看未付款统计
      list      - 查看结算记录列表
    """
    pass


@settle.command("driver")
@click.option("--start-date", required=True, help="结算开始日期 (YYYY-MM-DD)")
@click.option("--end-date", required=True, help="结算结束日期 (YYYY-MM-DD)")
@click.option("--driver", "driver_name", default=None, help="指定司机姓名")
@click.option("--plate", default=None, help="指定车牌号")
@click.option("--status", type=click.Choice(["all", "unpaid", "paid"]), default="all",
              help="运单状态筛选: all(全部), unpaid(未付款), paid(已付款)")
@click.option("--mark-paid", is_flag=True, help="生成结算单时同时标记为已付款")
@click.option("--export", "export_path", default=None, help="导出到 Excel 文件路径")
@click.pass_context
def settle_driver(
    ctx, start_date: str, end_date: str, driver_name: str, plate: str,
    status: str, mark_paid: bool, export_path: str
):
    """生成司机运费结算单

    \b
    示例:
      bamboo settle driver --start-date 2024-01-01 --end-date 2024-01-31
      bamboo settle driver --start-date 2024-01-01 --end-date 2024-01-31 --driver 张三
      bamboo settle driver --start-date 2024-01-01 --end-date 2024-01-31 --status unpaid --export 1月司机结算.xlsx
    """
    store: DataStore = ctx.obj["store"]
    waybills = store.load_waybills()
    drivers = store.load_drivers()
    driver_map = {d.id: d for d in drivers}

    waybills = [w for w in waybills if is_within_date_range(w.transport_date, start_date, end_date)]
    waybills = filter_effective_waybills(waybills)

    if driver_name:
        waybills = [w for w in waybills if driver_name in (w.driver_name or "")]
    if plate:
        waybills = [w for w in waybills if plate in (w.license_plate or "")]
    if status == "unpaid":
        waybills = [w for w in waybills if not w.is_paid]
    elif status == "paid":
        waybills = [w for w in waybills if w.is_paid]

    if not waybills:
        click.echo("\n没有符合条件的运单")
        return

    driver_groups: Dict[str, List[Waybill]] = defaultdict(list)
    for w in waybills:
        key = w.driver_id or w.driver_name or "未命名司机"
        driver_groups[key].append(w)

    click.echo(f"\n司机结算期间: {start_date} ~ {end_date}")
    click.echo(f"运单数量: {len(waybills)} 条, 涉及司机: {len(driver_groups)} 人")

    settlements = []
    summary_data = []
    all_details = []

    for idx, (driver_key, wbs) in enumerate(sorted(driver_groups.items()), 1):
        driver = None
        if driver_key in driver_map:
            driver = driver_map[driver_key]
        else:
            for d in drivers:
                if d.name == driver_key or d.id == driver_key:
                    driver = d
                    break

        first_wb = wbs[0]
        d_name = driver.name if driver else first_wb.driver_name or driver_key
        d_plate = driver.license_plate if driver else first_wb.license_plate
        d_phone = driver.phone if driver else first_wb.driver_phone
        d_bank = driver.bank_account if driver else ""
        d_bank_name = driver.bank_name if driver else ""

        total_weight = sum(w.net_weight for w in wbs)
        total_freight = sum(w.freight for w in wbs)
        paid_amount = sum(min(w.paid_amount, w.freight) for w in wbs if w.is_paid)
        unpaid_count = sum(1 for w in wbs if (not w.is_paid) or (w.paid_amount < w.freight))
        paid_count = sum(1 for w in wbs if w.is_paid and w.paid_amount >= w.freight)
        unpaid_amount = total_freight - paid_amount

        settlement_no = generate_serial_no("DS", idx)
        settlements.append({
            "no": settlement_no,
            "driver": d_name,
            "plate": d_plate,
            "phone": d_phone,
            "bank_account": d_bank,
            "bank_name": d_bank_name,
            "waybills": wbs,
            "total_weight": total_weight,
            "total_freight": total_freight,
            "paid_amount": paid_amount,
            "unpaid_amount": unpaid_amount,
            "unpaid_count": unpaid_count,
            "paid_count": paid_count,
        })

        summary_data.append([
            idx,
            settlement_no,
            d_name,
            d_plate,
            len(wbs),
            format_weight(total_weight),
            format_money(total_freight),
            format_money(paid_amount),
            format_money(unpaid_amount),
            f"{paid_count}/{unpaid_count}"
        ])

        for w in wbs:
            all_details.append({
                "结算单号": settlement_no,
                "司机": d_name,
                "车牌号": d_plate,
                "运单号": w.waybill_no,
                "运输日期": w.transport_date,
                "竹种": w.bamboo_type_name,
                "装车点": w.loading_point_name,
                "收购点": w.purchase_point_name,
                "里程(km)": w.mileage,
                "净重(吨)": round(w.net_weight, 3),
                "运费(元)": round(w.freight, 2),
                "状态": "已付款" if w.is_paid else "未付款",
                "已付金额": round(w.paid_amount, 2),
                "付款日期": w.paid_date,
                "付款备注": w.paid_remark,
            })

    print_table(
        summary_data,
        ["序", "结算单号", "司机", "车牌", "运单数", "总净重", "总运费", "已付", "未付", "状态"],
        f"司机结算汇总 (共 {len(settlements)} 人)"
    )

    grand_total_weight = sum(s["total_weight"] for s in settlements)
    grand_total_freight = sum(s["total_freight"] for s in settlements)
    grand_paid = sum(s["paid_amount"] for s in settlements)
    grand_unpaid = sum(s["unpaid_amount"] for s in settlements)

    grand = [
        ["总运单数", f"{len(waybills)} 条"],
        ["总净重", format_weight(grand_total_weight)],
        ["总运费", format_money(grand_total_freight)],
        ["已付合计", format_money(grand_paid)],
        ["未付合计", format_money(grand_unpaid)],
    ]
    print_table(grand, ["项目", "金额/数量"], "总计")

    if mark_paid:
        updated_count = 0
        for s in settlements:
            for w in s["waybills"]:
                if not w.is_paid:
                    w.is_paid = True
                    w.paid_amount = w.freight
                    w.paid_date = datetime.now().strftime("%Y-%m-%d")
                    w.paid_remark = f"结算单{s['no']}自动标记"
                    updated_count += 1
        if updated_count > 0:
            store.update_waybills_batch(waybills)
            click.echo(f"\n✅ 已标记 {updated_count} 条运单为已付款")

    settlement_records = []
    seq = len(store.load_settlements()) + 1
    for s in settlements:
        sett = Settlement(
            settlement_no=s["no"],
            settlement_date=datetime.now().strftime("%Y-%m-%d"),
            settlement_type="司机结算",
            target_id=next((d.id for d in drivers if d.name == s["driver"]), ""),
            target_name=s["driver"],
            waybill_ids=[w.id for w in s["waybills"]],
            total_weight=s["total_weight"],
            total_freight=s["total_freight"],
            total_bamboo_value=0,
            total_amount=s["total_freight"],
            paid_amount=s["paid_amount"],
            unpaid_amount=s["unpaid_amount"],
            status="已完成" if s["unpaid_count"] == 0 else "部分付款"
        )
        settlement_records.append(sett)
    for sr in settlement_records:
        store.add_settlement(sr)

    if export_path or True:
        if not export_path:
            target_suffix = ""
            if driver_name and len(settlements) == 1:
                target_suffix = f"_{driver_name}"
            elif plate and len(settlements) == 1:
                target_suffix = f"_{plate.replace('/', '-')}"
            export_path = f"司机结算包_{start_date}_{end_date}{target_suffix}.xlsx"
        if not os.path.isabs(export_path):
            export_path = os.path.join(store.get_settlement_dir(), export_path)

        with click.progressbar(length=2 + len(settlements), label="导出结算包") as bar:
            import pandas as pd
            os.makedirs(os.path.dirname(export_path), exist_ok=True)
            with pd.ExcelWriter(export_path, engine="openpyxl") as writer:
                df_summary = pd.DataFrame([[
                    s["no"], s["driver"], s["plate"], s["phone"],
                    s["bank_name"], s["bank_account"],
                    len(s["waybills"]), round(s["total_weight"], 3),
                    round(s["total_freight"], 2), round(s["paid_amount"], 2),
                    round(s["unpaid_amount"], 2)
                ] for s in settlements], columns=[
                    "结算单号", "司机", "车牌", "电话", "开户行", "银行账号",
                    "运单数", "总净重(吨)", "总运费(元)", "已付(元)", "未付(元)"
                ])
                df_summary.to_excel(writer, sheet_name="结算汇总", index=False)
                bar.update(1)

                if all_details:
                    df_detail = pd.DataFrame(all_details)
                    df_detail.to_excel(writer, sheet_name="全部运单明细", index=False)
                bar.update(1)

                for s in settlements:
                    driver_sheet_rows = []
                    for w in s["waybills"]:
                        driver_sheet_rows.append({
                            "结算单号": s["no"],
                            "运单号": w.waybill_no,
                            "运输日期": w.transport_date,
                            "竹种": w.bamboo_type_name,
                            "装车点": w.loading_point_name,
                            "收购点": w.purchase_point_name,
                            "里程(km)": w.mileage,
                            "净重(吨)": round(w.net_weight, 3),
                            "运费(元)": round(w.freight, 2),
                            "竹款(元)": round(w.bamboo_value, 2),
                            "合计(元)": round(w.freight + w.bamboo_value, 2),
                            "状态": "已付款" if w.is_paid else "未付款",
                            "已付金额": round(w.paid_amount, 2),
                            "付款日期": w.paid_date,
                            "付款备注": w.paid_remark,
                            "竹农": w.farmer_name or "-",
                            "磅单号": w.weight_note_no or "-",
                            "备注": w.remark or "",
                        })
                    df_per = pd.DataFrame(driver_sheet_rows)
                    sheet_name = f"{s['driver'][:10]}_{s['plate']}"
                    invalid = '<>:"/\\|?*'
                    for ch in invalid:
                        sheet_name = sheet_name.replace(ch, "_")
                    sheet_name = sheet_name[:31]
                    df_per.to_excel(writer, sheet_name=sheet_name, index=False)
                    bar.update(1)

        click.echo(f"\n✅ 司机结算包已导出: {export_path}")
        click.echo(f"   包含: 结算汇总 + 全部明细 + {len(settlements)} 个司机分Sheet")

    return settlements


@settle.command("farmer")
@click.option("--start-date", required=True, help="结算开始日期 (YYYY-MM-DD)")
@click.option("--end-date", required=True, help="结算结束日期 (YYYY-MM-DD)")
@click.option("--farmer", "farmer_name", default=None, help="指定竹农姓名")
@click.option("--bamboo", default=None, help="按竹种筛选")
@click.option("--status", type=click.Choice(["all", "unpaid", "paid"]), default="all",
              help="运单状态筛选")
@click.option("--mark-paid", is_flag=True, help="生成清单时同时标记为已付款")
@click.option("--export", "export_path", default=None, help="导出到 Excel 文件路径")
@click.pass_context
def settle_farmer(
    ctx, start_date: str, end_date: str, farmer_name: str, bamboo: str,
    status: str, mark_paid: bool, export_path: str
):
    """生成竹农付款清单

    \b
    示例:
      bamboo settle farmer --start-date 2024-01-01 --end-date 2024-01-31
      bamboo settle farmer --start-date 2024-01-01 --end-date 2024-01-31 --farmer 李四
      bamboo settle farmer --start-date 2024-01-01 --end-date 2024-01-31 --bamboo 毛竹
    """
    store: DataStore = ctx.obj["store"]
    waybills = store.load_waybills()

    waybills = [w for w in waybills if is_within_date_range(w.transport_date, start_date, end_date)]
    waybills = filter_effective_waybills(waybills)
    waybills = [w for w in waybills if w.farmer_name or w.bamboo_value > 0]

    if farmer_name:
        waybills = [w for w in waybills if farmer_name in (w.farmer_name or "")]
    if bamboo:
        waybills = [w for w in waybills if bamboo in (w.bamboo_type_name or "")]
    if status == "unpaid":
        waybills = [w for w in waybills if w.farmer_amount > 0 and not (w.is_paid and w.paid_amount >= w.farmer_amount)]
    elif status == "paid":
        waybills = [w for w in waybills if w.is_paid and w.paid_amount >= w.farmer_amount]

    if not waybills:
        click.echo("\n没有符合条件的运单")
        return

    farmer_groups: Dict[str, List[Waybill]] = defaultdict(list)
    for w in waybills:
        key = w.farmer_name or "未登记竹农"
        farmer_groups[key].append(w)

    click.echo(f"\n竹农结算期间: {start_date} ~ {end_date}")
    click.echo(f"运单数量: {len(waybills)} 条, 涉及竹农: {len(farmer_groups)} 户")

    payment_list = []
    all_details = []

    for idx, (f_name, wbs) in enumerate(sorted(farmer_groups.items()), 1):
        first_wb = wbs[0]
        f_phone = first_wb.farmer_phone
        f_bank = first_wb.farmer_bank_account
        f_bank_name = first_wb.farmer_bank_name

        for w in wbs:
            if not f_phone and w.farmer_phone:
                f_phone = w.farmer_phone
            if not f_bank and w.farmer_bank_account:
                f_bank = w.farmer_bank_account
            if not f_bank_name and w.farmer_bank_name:
                f_bank_name = w.farmer_bank_name

        total_weight = sum(w.net_weight for w in wbs)
        total_value = sum(w.farmer_amount for w in wbs if w.farmer_amount > 0)
        paid_amount = sum(min(w.paid_amount, w.farmer_amount) for w in wbs if w.is_paid)
        unpaid_amount = total_value - paid_amount

        bamboo_detail = defaultdict(float)
        for w in wbs:
            bamboo_detail[w.bamboo_type_name or "未知竹种"] += w.net_weight

        bamboo_str = ", ".join(f"{k}:{format_weight(v)}" for k, v in bamboo_detail.items())

        payment_list.append([
            idx,
            f_name,
            f_phone or "-",
            f_bank_name or "-",
            f_bank or "-",
            len(wbs),
            bamboo_str,
            format_weight(total_weight),
            format_money(total_value),
            format_money(paid_amount),
            format_money(unpaid_amount),
        ])

        for w in wbs:
            all_details.append({
                "竹农": f_name,
                "联系电话": f_phone,
                "开户行": f_bank_name,
                "银行账号": f_bank,
                "运单号": w.waybill_no,
                "运输日期": w.transport_date,
                "竹种": w.bamboo_type_name,
                "装车点": w.loading_point_name,
                "净重(吨)": round(w.net_weight, 3),
                "单价(元/吨)": round(w.unit_price, 2),
                "竹款(元)": round(w.farmer_amount, 2),
                "已付金额": round(min(w.paid_amount, w.farmer_amount), 2),
                "付款日期": w.paid_date,
                "备注": w.paid_remark,
            })

    print_table(
        payment_list,
        ["序", "竹农", "电话", "开户行", "账号", "单数", "竹种明细", "总净重", "总竹款", "已付", "未付"],
        f"竹农付款清单 (共 {len(payment_list)} 户)"
    )

    grand_total_weight = sum(sum(w.net_weight for w in wbs) for wbs in farmer_groups.values())
    grand_total_value = sum(sum(w.farmer_amount for w in wbs if w.farmer_amount > 0) for wbs in farmer_groups.values())
    grand_paid = sum(sum(min(w.paid_amount, w.farmer_amount) for w in wbs if w.is_paid) for wbs in farmer_groups.values())
    grand_unpaid = grand_total_value - grand_paid

    grand = [
        ["总户数", f"{len(farmer_groups)} 户"],
        ["总运单数", f"{len(waybills)} 条"],
        ["总净重", format_weight(grand_total_weight)],
        ["总竹款", format_money(grand_total_value)],
        ["已付合计", format_money(grand_paid)],
        ["未付合计", format_money(grand_unpaid)],
    ]
    print_table(grand, ["项目", "金额/数量"], "总计")

    if mark_paid:
        updated_count = 0
        for wbs in farmer_groups.values():
            for w in wbs:
                if not w.is_paid or w.paid_amount < w.farmer_amount:
                    w.is_paid = True
                    w.paid_amount = w.freight + w.farmer_amount if w.freight > 0 else w.farmer_amount
                    w.paid_date = datetime.now().strftime("%Y-%m-%d")
                    w.paid_remark = (w.paid_remark + "; " if w.paid_remark else "") + "竹农付款清单自动标记"
                    updated_count += 1
        if updated_count > 0:
            store.update_waybills_batch(waybills)
            click.echo(f"\n✅ 已标记 {updated_count} 条运单竹款为已付款")

    if export_path or True:
        if not export_path:
            target_suffix = ""
            if farmer_name and len(payment_list) == 1:
                target_suffix = f"_{farmer_name}"
            export_path = f"竹农付款清单_{start_date}_{end_date}{target_suffix}.xlsx"
        if not os.path.isabs(export_path):
            export_path = os.path.join(store.get_settlement_dir(), export_path)

        import pandas as pd
        os.makedirs(os.path.dirname(export_path), exist_ok=True)
        total_sheets = 3 + len(farmer_groups)
        with click.progressbar(length=total_sheets, label="导出付款清单") as bar:
            with pd.ExcelWriter(export_path, engine="openpyxl") as writer:
                df_pay = pd.DataFrame([
                    [p[1], p[2], p[3], p[4], p[5], p[6], p[7].replace("吨", ""),
                     float(p[8].replace("¥", "").replace(",", "")),
                     float(p[9].replace("¥", "").replace(",", "")),
                     float(p[10].replace("¥", "").replace(",", ""))]
                    for p in payment_list
                ], columns=[
                    "竹农", "联系电话", "开户行", "银行账号", "运单数",
                    "竹种明细", "总净重(吨)", "总竹款(元)", "已付(元)", "未付(元)"
                ])
                df_pay.to_excel(writer, sheet_name="付款清单汇总", index=False)
                bar.update(1)

                coop_rows: List[Dict[str, Any]] = []
                for f_name, wbs in sorted(farmer_groups.items()):
                    sub_total_w = sum(w.net_weight for w in wbs)
                    sub_total_v = sum(w.farmer_amount for w in wbs if w.farmer_amount > 0)
                    sub_paid = sum(min(w.paid_amount, w.farmer_amount) for w in wbs if w.is_paid)
                    coop_rows.append({
                        "层级": "【竹农合计】",
                        "竹农": f_name,
                        "收购点": "合计",
                        "竹种": "合计",
                        "单数": len(wbs),
                        "总净重(吨)": round(sub_total_w, 3),
                        "竹款(元)": round(sub_total_v, 2),
                        "已付(元)": round(sub_paid, 2),
                        "未付(元)": round(sub_total_v - sub_paid, 2),
                    })
                    pp_groups: Dict[str, List[Waybill]] = defaultdict(list)
                    for w in wbs:
                        pp_groups[w.purchase_point_name or "未知收购点"].append(w)
                    for pp_name, pp_wbs in sorted(pp_groups.items()):
                        pp_w = sum(w.net_weight for w in pp_wbs)
                        pp_v = sum(w.farmer_amount for w in pp_wbs if w.farmer_amount > 0)
                        pp_pd = sum(min(w.paid_amount, w.farmer_amount) for w in pp_wbs if w.is_paid)
                        coop_rows.append({
                            "层级": "  ↳收购点小计",
                            "竹农": f_name,
                            "收购点": pp_name,
                            "竹种": "小计",
                            "单数": len(pp_wbs),
                            "总净重(吨)": round(pp_w, 3),
                            "竹款(元)": round(pp_v, 2),
                            "已付(元)": round(pp_pd, 2),
                            "未付(元)": round(pp_v - pp_pd, 2),
                        })
                        bb_groups: Dict[str, List[Waybill]] = defaultdict(list)
                        for w in pp_wbs:
                            bb_groups[w.bamboo_type_name or "未知竹种"].append(w)
                        for bb_name, bb_wbs in sorted(bb_groups.items()):
                            bb_w = sum(w.net_weight for w in bb_wbs)
                            bb_v = sum(w.farmer_amount for w in bb_wbs if w.farmer_amount > 0)
                            bb_pd = sum(min(w.paid_amount, w.farmer_amount) for w in bb_wbs if w.is_paid)
                            coop_rows.append({
                                "层级": "    ↳竹种明细",
                                "竹农": f_name,
                                "收购点": pp_name,
                                "竹种": bb_name,
                                "单数": len(bb_wbs),
                                "总净重(吨)": round(bb_w, 3),
                                "竹款(元)": round(bb_v, 2),
                                "已付(元)": round(bb_pd, 2),
                                "未付(元)": round(bb_v - bb_pd, 2),
                            })
                pd.DataFrame(coop_rows).to_excel(writer, sheet_name="合作社汇总(展开)", index=False)
                bar.update(1)

                if all_details:
                    df_detail = pd.DataFrame(all_details)
                    df_detail.to_excel(writer, sheet_name="全部运单明细", index=False)
                bar.update(1)

                for f_name, wbs in farmer_groups.items():
                    farmer_sheet_rows: List[Dict[str, Any]] = []
                    sub_total_w = sum(w.net_weight for w in wbs)
                    sub_total_v = sum(w.farmer_amount for w in wbs if w.farmer_amount > 0)
                    sub_paid = sum(min(w.paid_amount, w.farmer_amount) for w in wbs if w.is_paid)
                    pp_count = len(set(w.purchase_point_name for w in wbs if w.purchase_point_name))
                    bb_count = len(set(w.bamboo_type_name for w in wbs if w.bamboo_type_name))
                    farmer_sheet_rows.append({
                        "【竹农合计摘要】": f_name,
                        "跨收购点": f"{pp_count} 个",
                        "跨竹种": f"{bb_count} 个",
                        "总单数": len(wbs),
                        "总净重(吨)": round(sub_total_w, 3),
                        "竹款合计(元)": round(sub_total_v, 2),
                        "已付竹款(元)": round(sub_paid, 2),
                        "未付竹款(元)": round(sub_total_v - sub_paid, 2),
                        "收购点明细": "/".join(sorted(set(w.purchase_point_name or "未知" for w in wbs if w.purchase_point_name))),
                        "竹种明细": "/".join(sorted(set(w.bamboo_type_name or "未知" for w in wbs if w.bamboo_type_name))),
                    })
                    farmer_sheet_rows.append({})
                    for w in wbs:
                        farmer_sheet_rows.append({
                            "【竹农合计摘要】": "↓运单明细",
                            "跨收购点": w.waybill_no,
                            "竹种明细": w.transport_date,
                            "总单数": w.driver_name or "-",
                            "总净重(吨)": w.license_plate or "-",
                            "竹款合计(元)": w.bamboo_type_name or "-",
                            "已付竹款(元)": w.loading_point_name or "-",
                            "未付竹款(元)": w.purchase_point_name or "-",
                            "收购点明细": round(w.net_weight, 3),
                        })
                    farmer_sheet_rows.append({})
                    farmer_sheet_rows.append({
                        "【竹农合计摘要】": "运单号",
                        "跨收购点": "运输日期",
                        "竹种明细": "司机",
                        "总单数": "车牌",
                        "总净重(吨)": "竹种",
                        "竹款合计(元)": "装车点",
                        "已付竹款(元)": "收购点",
                        "未付竹款(元)": "净重(吨)",
                        "收购点明细": "单价(元/吨)",
                        "竹种明细(列10)": "竹款(元)",
                    })
                    for w in wbs:
                        farmer_sheet_rows.append({
                            "【竹农合计摘要】": w.waybill_no,
                            "跨收购点": w.transport_date,
                            "竹种明细": w.driver_name or "-",
                            "总单数": w.license_plate or "-",
                            "总净重(吨)": w.bamboo_type_name or "-",
                            "竹款合计(元)": w.loading_point_name or "-",
                            "已付竹款(元)": w.purchase_point_name or "-",
                            "未付竹款(元)": round(w.net_weight, 3),
                            "收购点明细": round(w.unit_price, 2),
                            "竹种明细(列10)": round(w.farmer_amount, 2),
                        })
                    df_per = pd.DataFrame(farmer_sheet_rows)
                    sheet_name = f"{f_name[:10]}"
                    invalid = '<>:"/\\|?*'
                    for ch in invalid:
                        sheet_name = sheet_name.replace(ch, "_")
                    sheet_name = sheet_name[:31] or "未命名竹农"
                    df_per.to_excel(writer, sheet_name=sheet_name, index=False)
                    bar.update(1)

        click.echo(f"\n✅ 竹农付款清单已导出: {export_path}")
        click.echo(f"   包含: 付款汇总 + 合作社汇总(展开) + 全部明细 + {len(farmer_groups)} 个竹农分Sheet")

    return payment_list


@settle.command("pay")
@click.option("--id", "waybill_id", default=None, help="运单ID或运单号")
@click.option("--ids", default=None, help="多个运单号，逗号分隔")
@click.option("--driver", "driver_name", default=None, help="按司机批量标记")
@click.option("--start-date", default=None, help="开始日期，配合 --driver 使用")
@click.option("--end-date", default=None, help="结束日期，配合 --driver 使用")
@click.option("--amount", type=float, default=None, help="付款金额，默认全额")
@click.option("--date", "paid_date", default=None, help="付款日期 (YYYY-MM-DD)，默认今天")
@click.option("--remark", default="", help="付款备注")
@click.option("--farmer", is_flag=True, help="同时标记竹农款项已付")
@click.pass_context
def settle_pay(
    ctx, waybill_id: str, ids: str, driver_name: str,
    start_date: str, end_date: str, amount: float, paid_date: str,
    remark: str, farmer: bool
):
    """标记运单已付款

    \b
    示例:
      bamboo settle pay --id WB00123
      bamboo settle pay --ids WB00123,WB00124,WB00125 --amount 500 --remark 现金支付
      bamboo settle pay --driver 张三 --start-date 2024-01-01 --end-date 2024-01-31
    """
    store: DataStore = ctx.obj["store"]
    waybills = store.load_waybills()

    target_ids = set()
    if waybill_id:
        for w in waybills:
            if w.id == waybill_id or w.waybill_no == waybill_id:
                target_ids.add(w.id)
                break
    if ids:
        id_list = [x.strip() for x in ids.split(",") if x.strip()]
        for w in waybills:
            if w.id in id_list or w.waybill_no in id_list:
                target_ids.add(w.id)
    if driver_name:
        effective_wbs = filter_effective_waybills(waybills)
        for w in effective_wbs:
            if driver_name in (w.driver_name or ""):
                if start_date and end_date and not is_within_date_range(w.transport_date, start_date, end_date):
                    continue
                if start_date and not end_date and normalize_date(w.transport_date) < normalize_date(start_date):
                    continue
                if end_date and not start_date and normalize_date(w.transport_date) > normalize_date(end_date):
                    continue
                target_ids.add(w.id)

    if not target_ids:
        click.echo("\n❌ 未找到匹配的运单", err=True)
        return

    pd = paid_date or datetime.now().strftime("%Y-%m-%d")
    count = 0
    total_paid = 0.0

    for w in waybills:
        if w.id not in target_ids:
            continue

        w.is_paid = True
        if amount:
            w.paid_amount += amount
        else:
            if farmer:
                w.paid_amount = w.freight + w.farmer_amount
            else:
                w.paid_amount = w.freight if w.freight > 0 else w.farmer_amount
        w.paid_date = pd
        if remark:
            w.paid_remark = (w.paid_remark + "; " if w.paid_remark else "") + remark
        else:
            w.paid_remark = w.paid_remark or "已付款"
        total_paid += w.paid_amount
        count += 1

    store.save_waybills(waybills)

    click.echo(f"\n✅ 已标记付款:")
    click.echo(f"  运单数量: {count} 条")
    click.echo(f"  付款金额: {format_money(total_paid)}")
    click.echo(f"  付款日期: {pd}")
    if remark:
        click.echo(f"  付款备注: {remark}")


@settle.command("unpaid")
@click.option("--by", "group_by", type=click.Choice(["driver", "farmer", "month"]), default="driver",
              help="未付款统计分组方式")
@click.option("--start-date", default=None, help="开始日期")
@click.option("--end-date", default=None, help="结束日期")
@click.pass_context
def settle_unpaid(ctx, group_by: str, start_date: str, end_date: str):
    """查看未付款统计

    \b
    示例:
      bamboo settle unpaid --by driver
      bamboo settle unpaid --by farmer
      bamboo settle unpaid --by month --start-date 2024-01-01
    """
    store: DataStore = ctx.obj["store"]
    waybills = store.load_waybills()

    waybills = filter_effective_waybills(waybills)
    if start_date and end_date:
        waybills = [w for w in waybills if is_within_date_range(w.transport_date, start_date, end_date)]

    unpaid_wbs = [w for w in waybills if not w.is_paid or w.paid_amount < max(w.freight, w.farmer_amount)]

    if not unpaid_wbs:
        click.echo("\n✅ 没有未付款的运单！")
        return

    click.echo(f"\n未付款运单总数: {len(unpaid_wbs)} 条")

    if group_by == "driver":
        groups: Dict[str, List[Waybill]] = defaultdict(list)
        for w in unpaid_wbs:
            key = w.driver_name or "未命名司机"
            groups[key].append(w)
        data = []
        for idx, (name, wbs) in enumerate(sorted(groups.items()), 1):
            w = sum(w.net_weight for w in wbs)
            f = sum(w.freight for w in wbs)
            data.append([idx, name, len(wbs), format_weight(w), format_money(f)])
        print_table(data, ["序", "司机", "单数", "总净重", "未付运费"], "按司机统计未付款")

    elif group_by == "farmer":
        groups = defaultdict(list)
        for w in unpaid_wbs:
            key = w.farmer_name or "未登记竹农"
            groups[key].append(w)
        data = []
        for idx, (name, wbs) in enumerate(sorted(groups.items()), 1):
            w = sum(w.net_weight for w in wbs)
            b = sum(w.farmer_amount for w in wbs)
            data.append([idx, name, len(wbs), format_weight(w), format_money(b)])
        print_table(data, ["序", "竹农", "单数", "总净重", "未付竹款"], "按竹农统计未付款")

    else:
        groups = defaultdict(list)
        for w in unpaid_wbs:
            dt = normalize_date(w.transport_date)
            key = dt[:7] if dt else "未知月份"
            groups[key].append(w)
        data = []
        for month, wbs in sorted(groups.items()):
            w = sum(w.net_weight for w in wbs)
            f = sum(w.freight for w in wbs)
            b = sum(w.farmer_amount for w in wbs)
            data.append([month, len(wbs), format_weight(w), format_money(f), format_money(b), format_money(f + b)])
        print_table(data, ["月份", "单数", "总净重", "未付运费", "未付竹款", "合计"], "按月份统计未付款")


@settle.command("list")
@click.option("--type", "settlement_type", type=click.Choice(["all", "司机结算", "竹农结算"]), default="all",
              help="结算类型筛选")
@click.option("--limit", type=int, default=20, help="显示最近多少条，默认20")
@click.pass_context
def settle_list(ctx, settlement_type: str, limit: int):
    """查看结算记录列表

    \b
    示例:
      bamboo settle list
      bamboo settle list --type 司机结算 --limit 50
    """
    store: DataStore = ctx.obj["store"]
    settlements = store.load_settlements()

    if settlement_type != "all":
        settlements = [s for s in settlements if s.settlement_type == settlement_type]

    settlements = sorted(settlements, key=lambda x: x.created_at, reverse=True)[:limit]

    if not settlements:
        click.echo("\n暂无结算记录")
        return

    data = []
    for idx, s in enumerate(settlements, 1):
        data.append([
            idx,
            s.settlement_no,
            s.settlement_date,
            s.settlement_type,
            s.target_name,
            len(s.waybill_ids),
            format_weight(s.total_weight),
            format_money(s.total_amount),
            format_money(s.paid_amount),
            s.status,
        ])

    print_table(
        data,
        ["序", "结算单号", "日期", "类型", "对象", "单数", "总重", "总额", "已付", "状态"],
        f"结算记录 (共 {len(settlements)} 条)"
    )

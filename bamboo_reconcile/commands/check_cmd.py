"""check 命令 - 校验车牌和司机、检查重复运单、识别缺少装车点记录"""
from typing import List, Dict, Any, Set
from collections import defaultdict

import click

from ..models import Waybill
from ..storage import DataStore
from ..utils import (
    validate_license_plate, validate_driver_name, validate_phone,
    validate_weight, normalize_license_plate, normalize_date,
    find_duplicate_waybills, find_missing_loading_points, find_weight_mismatch,
    print_table, is_within_date_range
)


@click.command("check")
@click.option("--all", "check_all", is_flag=True, help="执行全部检查")
@click.option("--plate", is_flag=True, help="校验车牌号")
@click.option("--driver", is_flag=True, help="校验司机信息")
@click.option("--duplicate", is_flag=True, help="检查重复运单")
@click.option("--loading", is_flag=True, help="识别缺少装车点记录")
@click.option("--weight", is_flag=True, help="校验重量数据")
@click.option("--unmatched-weight", is_flag=True, help="检查未匹配磅单的运单")
@click.option("--start-date", default=None, help="开始日期 (YYYY-MM-DD)")
@click.option("--end-date", default=None, help="结束日期 (YYYY-MM-DD)")
@click.option("--fix", is_flag=True, help="自动修复可修复的问题")
@click.pass_context
def cmd_check(
    ctx, check_all: bool, plate: bool, driver: bool, duplicate: bool,
    loading: bool, weight: bool, unmatched_weight: bool,
    start_date: str, end_date: str, fix: bool
):
    """校验运单数据，检查各种异常

    \b
    示例:
      bamboo check --all
      bamboo check --plate --driver
      bamboo check --duplicate --fix
      bamboo check --loading --start-date 2024-01-01 --end-date 2024-01-31
      bamboo check --unmatched-weight
    """
    store: DataStore = ctx.obj["store"]

    if not any([check_all, plate, driver, duplicate, loading, weight, unmatched_weight]):
        check_all = True

    waybills = store.load_waybills()
    original_count = len(waybills)

    if start_date and end_date:
        waybills = [w for w in waybills if is_within_date_range(w.transport_date, start_date, end_date)]
        click.echo(f"\n日期范围筛选: {start_date} ~ {end_date}, 共 {len(waybills)} 条运单")
    elif start_date:
        waybills = [w for w in waybills if normalize_date(w.transport_date) >= normalize_date(start_date)]
        click.echo(f"\n从 {start_date} 起, 共 {len(waybills)} 条运单")
    elif end_date:
        waybills = [w for w in waybills if normalize_date(w.transport_date) <= normalize_date(end_date)]
        click.echo(f"\n截至 {end_date}, 共 {len(waybills)} 条运单")

    if not waybills:
        click.echo("\n没有可检查的运单数据")
        return

    total_issues = 0

    if check_all or plate:
        total_issues += _check_license_plates(store, waybills, fix)

    if check_all or driver:
        total_issues += _check_drivers(store, waybills, fix)

    if check_all or duplicate:
        total_issues += _check_duplicates(store, waybills, fix)

    if check_all or loading:
        total_issues += _check_loading_points(store, waybills, fix)

    if check_all or weight:
        total_issues += _check_weights(store, waybills, fix)

    if check_all or unmatched_weight:
        total_issues += _check_unmatched_weight_notes(store, waybills, fix)

    click.echo(f"\n{'=' * 60}")
    click.echo(f"  检查完成: 共发现 {total_issues} 个问题")
    if fix:
        click.echo(f"  已自动修复可修复的问题")
    click.echo(f"{'=' * 60}")

    if total_issues > 0:
        exception_summary = _collect_exceptions(store, start_date, end_date)
        if exception_summary:
            print_table(
                [[etype, count] for etype, count in exception_summary.items()],
                ["异常类型", "数量"],
                "异常汇总"
            )


def _check_license_plates(store: DataStore, waybills: List[Waybill], fix: bool) -> int:
    """校验车牌号"""
    click.echo(f"\n--- 检查车牌号 ---")
    issues = []
    valid_vehicles = {v.license_plate for v in store.load_vehicles()}
    valid_drivers_plates = {d.license_plate for d in store.load_drivers()}

    for w in waybills:
        plate = normalize_license_plate(w.license_plate)
        if not plate:
            issues.append({"运单": w.waybill_no, "车牌": "(空)", "问题": "车牌号为空", "司机": w.driver_name})
            w.add_exception("车牌号为空")
            continue

        ok, msg = validate_license_plate(plate)
        if not ok:
            issues.append({"运单": w.waybill_no, "车牌": plate, "问题": msg, "司机": w.driver_name})
            w.add_exception(msg)
        elif fix and plate != w.license_plate:
            w.license_plate = plate

        if plate and plate not in valid_vehicles and plate not in valid_drivers_plates:
            msg = f"车牌未在车辆/司机档案中注册: {plate}"
            issues.append({"运单": w.waybill_no, "车牌": plate, "问题": "未注册", "司机": w.driver_name})
            w.add_exception(msg)

    if issues:
        print_table(
            [[i["运单"], i["车牌"], i["司机"], i["问题"]] for i in issues[:30]],
            ["运单号", "车牌号", "司机", "问题"],
            f"车牌问题 ({len(issues)} 条)"
        )
        if len(issues) > 30:
            click.echo(f"  ... 还有 {len(issues) - 30} 条未显示")
    else:
        click.echo("  ✅ 所有车牌号校验通过")

    if fix and issues:
        store.update_waybills_batch(waybills)

    return len(issues)


def _check_drivers(store: DataStore, waybills: List[Waybill], fix: bool) -> int:
    """校验司机信息"""
    click.echo(f"\n--- 检查司机信息 ---")
    issues = []
    driver_map = {}
    for d in store.load_drivers():
        driver_map[(d.name, d.license_plate)] = d
        driver_map[(d.name, "")] = d

    for w in waybills:
        problems = []
        if not w.driver_name:
            problems.append("司机姓名为空")
        else:
            ok, msg = validate_driver_name(w.driver_name)
            if not ok:
                problems.append(msg)

            key = (w.driver_name, normalize_license_plate(w.license_plate))
            key2 = (w.driver_name, "")
            matched = driver_map.get(key) or driver_map.get(key2)
            if not matched:
                problems.append(f"司机未在档案中注册: {w.driver_name}")
            elif fix:
                if not w.driver_id:
                    w.driver_id = matched.id
                if not w.driver_phone and matched.phone:
                    w.driver_phone = matched.phone

        if w.driver_phone:
            ok, msg = validate_phone(w.driver_phone)
            if not ok:
                problems.append(msg)

        for p in problems:
            w.add_exception(p)
            issues.append({
                "运单": w.waybill_no,
                "司机": w.driver_name,
                "车牌": w.license_plate,
                "问题": p
            })

    if issues:
        print_table(
            [[i["运单"], i["司机"], i["车牌"], i["问题"]] for i in issues[:30]],
            ["运单号", "司机", "车牌号", "问题"],
            f"司机信息问题 ({len(issues)} 条)"
        )
        if len(issues) > 30:
            click.echo(f"  ... 还有 {len(issues) - 30} 条未显示")
    else:
        click.echo("  ✅ 所有司机信息校验通过")

    if fix and issues:
        store.update_waybills_batch(waybills)

    return len(issues)


def _check_duplicates(store: DataStore, waybills: List[Waybill], fix: bool) -> int:
    """检查重复运单"""
    click.echo(f"\n--- 检查重复运单 ---")
    dup_map = find_duplicate_waybills(waybills)

    if not dup_map:
        click.echo("  ✅ 未发现重复运单")
        return 0

    wb_map = {w.id: w for w in waybills}
    issues = []
    processed: Set[str] = set()

    for wid, dup_ids in dup_map.items():
        if wid in processed:
            continue
        group = [wid] + dup_ids
        for gid in group:
            processed.add(gid)

        wbs = [wb_map[g] for g in group if g in wb_map]
        if not wbs:
            continue

        first = wbs[0]
        for w in wbs[1:]:
            w.is_duplicate = True
            w.duplicate_of = first.id
            w.add_exception("重复运单")
            issues.append({
                "运单": w.waybill_no,
                "重复于": first.waybill_no,
                "车牌": w.license_plate,
                "日期": w.transport_date,
                "净重": f"{w.net_weight:.3f}"
            })

    if issues:
        print_table(
            [[i["运单"], i["重复于"], i["车牌"], i["日期"], i["净重"]] for i in issues[:30]],
            ["重复运单号", "原始运单号", "车牌号", "运输日期", "净重(吨)"],
            f"重复运单 ({len(issues)} 条)"
        )
        if len(issues) > 30:
            click.echo(f"  ... 还有 {len(issues) - 30} 条未显示")

    if fix:
        store.update_waybills_batch(waybills)

    return len(issues)


def _check_loading_points(store: DataStore, waybills: List[Waybill], fix: bool) -> int:
    """识别缺少装车点记录"""
    click.echo(f"\n--- 检查装车点记录 ---")
    missing_ids = find_missing_loading_points(waybills)

    if not missing_ids:
        click.echo("  ✅ 所有运单都有装车点记录")
        return 0

    wb_map = {w.id: w for w in waybills}
    issues = []
    for mid in missing_ids:
        w = wb_map.get(mid)
        if w:
            w.add_exception("缺少装车点记录")
            issues.append({
                "运单": w.waybill_no,
                "车牌": w.license_plate,
                "司机": w.driver_name,
                "日期": w.transport_date,
                "装车点": w.loading_point_name or "(空)"
            })

    if issues:
        print_table(
            [[i["运单"], i["车牌"], i["司机"], i["日期"], i["装车点"]] for i in issues[:30]],
            ["运单号", "车牌号", "司机", "运输日期", "装车点"],
            f"缺少装车点记录 ({len(issues)} 条)"
        )
        if len(issues) > 30:
            click.echo(f"  ... 还有 {len(issues) - 30} 条未显示")

    if fix:
        store.update_waybills_batch(waybills)

    return len(issues)


def _check_weights(store: DataStore, waybills: List[Waybill], fix: bool) -> int:
    """校验重量数据"""
    click.echo(f"\n--- 检查重量数据 ---")
    mismatch_ids = find_weight_mismatch(waybills)
    wb_map = {w.id: w for w in waybills}

    issues = []
    for w in waybills:
        if w.id in mismatch_ids:
            calc = round(w.gross_weight - w.tare_weight, 3)
            msg = f"净重不符: 记录{w.net_weight}吨, 计算{calc}吨"
            w.add_exception(msg)
            issues.append({
                "运单": w.waybill_no,
                "车牌": w.license_plate,
                "毛重": f"{w.gross_weight:.3f}",
                "皮重": f"{w.tare_weight:.3f}",
                "记录净重": f"{w.net_weight:.3f}",
                "计算净重": f"{calc:.3f}"
            })
        if w.net_weight <= 0:
            msg = f"净重异常: {w.net_weight}吨"
            w.add_exception(msg)
            issues.append({
                "运单": w.waybill_no,
                "车牌": w.license_plate,
                "毛重": f"{w.gross_weight:.3f}",
                "皮重": f"{w.tare_weight:.3f}",
                "记录净重": f"{w.net_weight:.3f}",
                "计算净重": "N/A"
            })
        elif fix and w.id in mismatch_ids:
            calc = round(w.gross_weight - w.tare_weight, 3)
            w.net_weight = calc
            w.exceptions = [e for e in w.exceptions if "净重不符" not in e]

    if issues:
        print_table(
            [[i["运单"], i["车牌"], i["毛重"], i["皮重"], i["记录净重"], i["计算净重"]] for i in issues[:30]],
            ["运单号", "车牌号", "毛重(吨)", "皮重(吨)", "记录净重(吨)", "计算净重(吨)"],
            f"重量异常 ({len(issues)} 条)"
        )
        if len(issues) > 30:
            click.echo(f"  ... 还有 {len(issues) - 30} 条未显示")
    else:
        click.echo("  ✅ 所有重量数据校验通过")

    if fix and issues:
        store.update_waybills_batch(waybills)

    return len(issues)


def _check_unmatched_weight_notes(store: DataStore, waybills: List[Waybill], fix: bool) -> int:
    """检查未匹配磅单的运单"""
    click.echo(f"\n--- 检查磅单匹配情况 ---")
    weight_notes = store.load_weight_notes()
    wn_waybill_map = {n.weight_note_no: n for n in weight_notes if n.weight_note_no}

    issues = []
    for w in waybills:
        if not w.weight_note_no:
            msg = "缺少磅单号"
            w.add_exception(msg)
            issues.append({
                "运单": w.waybill_no,
                "车牌": w.license_plate,
                "司机": w.driver_name,
                "磅单号": "(空)",
                "问题": msg
            })
        elif w.weight_note_no not in wn_waybill_map:
            msg = f"磅单号未找到照片: {w.weight_note_no}"
            w.add_exception(msg)
            issues.append({
                "运单": w.waybill_no,
                "车牌": w.license_plate,
                "司机": w.driver_name,
                "磅单号": w.weight_note_no,
                "问题": msg
            })

    unmatched_notes = [n for n in weight_notes if not n.matched and n.weight_note_no]
    if unmatched_notes:
        click.echo(f"\n  有 {len(unmatched_notes)} 张磅单照片未匹配到运单")
        if fix:
            wb_wn_map = defaultdict(list)
            for w in waybills:
                if w.weight_note_no:
                    wb_wn_map[w.weight_note_no].append(w)
            for n in unmatched_notes:
                if n.weight_note_no in wb_wn_map:
                    wbs = wb_wn_map[n.weight_note_no]
                    if wbs:
                        w = wbs[0]
                        n.matched = True
                        n.matched_waybill_id = w.id
                        w.weight_note_photo = n.photo_path or n.photo_name
                        w.exceptions = [e for e in w.exceptions if "磅单号未找到" not in e]

    if issues:
        print_table(
            [[i["运单"], i["车牌"], i["司机"], i["磅单号"], i["问题"]] for i in issues[:30]],
            ["运单号", "车牌号", "司机", "磅单号", "问题"],
            f"磅单匹配问题 ({len(issues)} 条)"
        )
        if len(issues) > 30:
            click.echo(f"  ... 还有 {len(issues) - 30} 条未显示")
    else:
        click.echo("  ✅ 所有运单磅单匹配正常")

    if fix:
        store.update_waybills_batch(waybills)
        if unmatched_notes:
            store.save_weight_notes(weight_notes)

    return len(issues) + len(unmatched_notes)


def _collect_exceptions(store: DataStore, start_date: str, end_date: str) -> Dict[str, int]:
    """收集所有异常统计"""
    waybills = store.load_waybills()
    if start_date and end_date:
        waybills = [w for w in waybills if is_within_date_range(w.transport_date, start_date, end_date)]

    summary: Dict[str, int] = defaultdict(int)
    for w in waybills:
        for exc in w.exceptions:
            simple = exc.split(":")[0] if ":" in exc else exc
            summary[simple] += 1
    return dict(sorted(summary.items(), key=lambda x: -x[1]))

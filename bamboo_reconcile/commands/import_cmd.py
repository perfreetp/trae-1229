"""import 命令 - 导入运单文件和磅单照片清单"""
import os
from typing import List, Optional, Dict, Any

import click
import pandas as pd

from ..models import Waybill, WeightNote, Driver, BambooType, LoadingPoint, PurchasePoint, Vehicle, ImportBatch
from ..storage import DataStore
from ..utils import (
    read_excel_file, safe_float, safe_str, normalize_date, normalize_license_plate,
    print_table, validate_license_plate, validate_date, generate_serial_no
)


WAYBILL_COLUMN_MAPPING = {
    "运单号": "waybill_no",
    "运输日期": "transport_date",
    "日期": "transport_date",
    "车牌号": "license_plate",
    "车牌": "license_plate",
    "司机姓名": "driver_name",
    "司机": "driver_name",
    "司机电话": "driver_phone",
    "电话": "driver_phone",
    "竹种": "bamboo_type_name",
    "品种": "bamboo_type_name",
    "竹子种类": "bamboo_type_name",
    "装车点": "loading_point_name",
    "装货点": "loading_point_name",
    "装车地点": "loading_point_name",
    "收购点": "purchase_point_name",
    "卸货点": "purchase_point_name",
    "收购地点": "purchase_point_name",
    "里程": "mileage",
    "公里数": "mileage",
    "距离": "mileage",
    "毛重": "gross_weight",
    "皮重": "tare_weight",
    "净重": "net_weight",
    "实重": "net_weight",
    "过磅单": "weight_note_no",
    "磅单号": "weight_note_no",
    "磅单编号": "weight_note_no",
    "单价": "unit_price",
    "竹农": "farmer_name",
    "竹农姓名": "farmer_name",
    "货主": "farmer_name",
    "竹农电话": "farmer_phone",
    "竹农账号": "farmer_bank_account",
    "竹农开户行": "farmer_bank_name",
    "备注": "remark",
}

WEIGHT_NOTE_COLUMN_MAPPING = {
    "磅单号": "weight_note_no",
    "过磅单号": "weight_note_no",
    "编号": "weight_note_no",
    "照片文件": "photo_path",
    "照片": "photo_path",
    "文件路径": "photo_path",
    "文件名": "photo_name",
    "照片名称": "photo_name",
    "运输日期": "transport_date",
    "日期": "transport_date",
    "车牌号": "license_plate",
    "车牌": "license_plate",
    "毛重": "gross_weight",
    "皮重": "tare_weight",
    "净重": "net_weight",
    "备注": "remark",
}


def _map_columns(df: pd.DataFrame, mapping: Dict[str, str]) -> pd.DataFrame:
    """映射列名"""
    rename_map = {}
    for col in df.columns:
        if col in mapping:
            rename_map[col] = mapping[col]
    if rename_map:
        df = df.rename(columns=rename_map)
    return df


def _ensure_bamboo_types(store: DataStore, df: pd.DataFrame):
    """确保竹种存在"""
    if "bamboo_type_name" not in df.columns:
        return
    existing = {b.name for b in store.load_bamboo_types()}
    names = df["bamboo_type_name"].dropna().unique().tolist()
    for name in names:
        name = safe_str(name)
        if name and name not in existing:
            bamboo = BambooType(name=name, code=name[:2].upper())
            store.add_bamboo_type(bamboo)
            existing.add(name)
            click.echo(f"  新增竹种: {name}")


def _ensure_loading_points(store: DataStore, df: pd.DataFrame):
    """确保装车点存在"""
    if "loading_point_name" not in df.columns:
        return
    existing = {p.name for p in store.load_loading_points()}
    names = df["loading_point_name"].dropna().unique().tolist()
    for name in names:
        name = safe_str(name)
        if name and name not in existing:
            point = LoadingPoint(name=name)
            store.add_loading_point(point)
            existing.add(name)
            click.echo(f"  新增装车点: {name}")


def _ensure_purchase_points(store: DataStore, df: pd.DataFrame):
    """确保收购点存在"""
    if "purchase_point_name" not in df.columns:
        return
    existing = {p.name for p in store.load_purchase_points()}
    names = df["purchase_point_name"].dropna().unique().tolist()
    for name in names:
        name = safe_str(name)
        if name and name not in existing:
            point = PurchasePoint(name=name)
            store.add_purchase_point(point)
            existing.add(name)
            click.echo(f"  新增收购点: {name}")


def _ensure_drivers(store: DataStore, df: pd.DataFrame):
    """确保司机存在"""
    if "driver_name" not in df.columns:
        return
    existing_drivers = {(d.name, d.license_plate): d for d in store.load_drivers()}
    existing_vehicles = {v.license_plate: v for v in store.load_vehicles()}

    for _, row in df.iterrows():
        name = safe_str(row.get("driver_name", ""))
        plate = normalize_license_plate(safe_str(row.get("license_plate", "")))
        phone = safe_str(row.get("driver_phone", ""))
        if not name or not plate:
            continue
        key = (name, plate)
        if key not in existing_drivers:
            driver = Driver(name=name, license_plate=plate, phone=phone)
            store.add_driver(driver)
            existing_drivers[key] = driver
            click.echo(f"  新增司机: {name} ({plate})")
        if plate not in existing_vehicles:
            vehicle = Vehicle(
                license_plate=plate,
                driver_id=existing_drivers[key].id,
                driver_name=name
            )
            store.add_vehicle(vehicle)
            existing_vehicles[plate] = vehicle


def _row_to_waybill(store: DataStore, row: pd.Series, index: int) -> Waybill:
    """将行转换为运单对象"""
    w = Waybill()

    w.waybill_no = safe_str(row.get("waybill_no", "")) or f"AUTO{index+1:06d}"
    w.transport_date = normalize_date(safe_str(row.get("transport_date", "")))
    w.license_plate = normalize_license_plate(safe_str(row.get("license_plate", "")))
    w.driver_name = safe_str(row.get("driver_name", ""))
    w.driver_phone = safe_str(row.get("driver_phone", ""))
    w.bamboo_type_name = safe_str(row.get("bamboo_type_name", ""))
    w.loading_point_name = safe_str(row.get("loading_point_name", ""))
    w.purchase_point_name = safe_str(row.get("purchase_point_name", ""))
    w.mileage = safe_float(row.get("mileage", 0))
    w.gross_weight = safe_float(row.get("gross_weight", 0))
    w.tare_weight = safe_float(row.get("tare_weight", 0))
    w.net_weight = safe_float(row.get("net_weight", 0))
    w.weight_note_no = safe_str(row.get("weight_note_no", ""))
    w.unit_price = safe_float(row.get("unit_price", 0))
    w.farmer_name = safe_str(row.get("farmer_name", ""))
    w.farmer_phone = safe_str(row.get("farmer_phone", ""))
    w.farmer_bank_account = safe_str(row.get("farmer_bank_account", ""))
    w.farmer_bank_name = safe_str(row.get("farmer_bank_name", ""))
    w.remark = safe_str(row.get("remark", ""))

    if w.net_weight <= 0 and w.gross_weight > 0 and w.tare_weight > 0:
        w.net_weight = round(w.gross_weight - w.tare_weight, 3)

    bamboo = store.find_bamboo_by_name(w.bamboo_type_name)
    if bamboo:
        w.bamboo_type_id = bamboo.id
        if w.unit_price <= 0:
            w.unit_price = bamboo.unit_price

    lp = store.find_loading_point_by_name(w.loading_point_name)
    if lp:
        w.loading_point_id = lp.id
        if w.mileage <= 0:
            w.mileage = lp.mileage

    pp = store.find_purchase_point_by_name(w.purchase_point_name)
    if pp:
        w.purchase_point_id = pp.id

    driver = None
    if w.license_plate:
        driver = store.find_driver_by_plate(w.license_plate)
    if not driver and w.driver_name:
        driver = store.find_driver_by_name(w.driver_name)
    if driver:
        w.driver_id = driver.id
        if not w.driver_name:
            w.driver_name = driver.name
        if not w.driver_phone:
            w.driver_phone = driver.phone
        if not w.license_plate:
            w.license_plate = driver.license_plate

    return w


def _row_to_weight_note(row: pd.Series, index: int) -> WeightNote:
    """将行转换为磅单对象"""
    n = WeightNote()
    n.weight_note_no = safe_str(row.get("weight_note_no", "")) or f"PN{index+1:06d}"
    n.photo_path = safe_str(row.get("photo_path", ""))
    n.photo_name = safe_str(row.get("photo_name", ""))
    n.transport_date = normalize_date(safe_str(row.get("transport_date", "")))
    n.license_plate = normalize_license_plate(safe_str(row.get("license_plate", "")))
    n.gross_weight = safe_float(row.get("gross_weight", 0))
    n.tare_weight = safe_float(row.get("tare_weight", 0))
    n.net_weight = safe_float(row.get("net_weight", 0))
    n.remark = safe_str(row.get("remark", ""))

    if n.net_weight <= 0 and n.gross_weight > 0 and n.tare_weight > 0:
        n.net_weight = round(n.gross_weight - n.tare_weight, 3)

    return n


@click.command("import")
@click.option("--type", "import_type", type=click.Choice(["waybill", "weight", "auto"]),
              default="auto", help="导入类型: waybill(运单), weight(磅单), auto(自动识别)")
@click.option("--file", "filepath", required=True, type=click.Path(exists=True), help="要导入的 Excel/CSV 文件路径")
@click.option("--sheet", "sheet_name", default=None, help="Excel 工作表名称 (可选)")
@click.option("--dry-run", is_flag=True, help="试运行，不实际保存数据")
@click.pass_context
def cmd_import(ctx, import_type: str, filepath: str, sheet_name: Optional[str], dry_run: bool):
    """导入运单文件或磅单照片清单

    \b
    示例:
      bamboo import --file 运单202401.xlsx
      bamboo import --type waybill --file 运单.csv
      bamboo import --type weight --file 磅单清单.xlsx --dry-run
    """
    store: DataStore = ctx.obj["store"]
    filename = os.path.basename(filepath)

    click.echo(f"\n开始导入文件: {filename}")
    click.echo(f"导入类型: {import_type}")

    try:
        df = read_excel_file(filepath, sheet_name)
    except Exception as e:
        click.echo(f"❌ 读取文件失败: {e}", err=True)
        return

    click.echo(f"读取到 {len(df)} 行数据")

    if import_type == "auto":
        has_waybill_cols = any(c in WAYBILL_COLUMN_MAPPING for c in df.columns)
        has_weight_cols = any(c in WEIGHT_NOTE_COLUMN_MAPPING for c in df.columns)
        if has_waybill_cols and not has_weight_cols:
            import_type = "waybill"
        elif has_weight_cols and not has_waybill_cols:
            import_type = "weight"
        elif "运单号" in df.columns or "司机姓名" in df.columns or "竹种" in df.columns:
            import_type = "waybill"
        else:
            import_type = "waybill"
        click.echo(f"自动识别导入类型: {import_type}")

    if import_type == "waybill":
        _import_waybills(store, df, filepath, dry_run)
    else:
        _import_weight_notes(store, df, filepath, dry_run)


def _import_waybills(store: DataStore, df: pd.DataFrame, filepath: str, dry_run: bool):
    """导入运单"""
    df = _map_columns(df, WAYBILL_COLUMN_MAPPING)
    click.echo(f"\n识别字段: {', '.join(c for c in df.columns if c in WAYBILL_COLUMN_MAPPING.values())}")

    _ensure_bamboo_types(store, df)
    _ensure_loading_points(store, df)
    _ensure_purchase_points(store, df)
    _ensure_drivers(store, df)

    waybills: List[Waybill] = []
    errors: List[Dict[str, Any]] = []
    warning_count = 0

    for idx, row in df.iterrows():
        try:
            w = _row_to_waybill(store, row, idx)
            row_errors = []

            if w.license_plate:
                ok, msg = validate_license_plate(w.license_plate)
                if not ok:
                    row_errors.append(msg)
                    w.add_exception(msg)

            if w.transport_date:
                ok, msg = validate_date(w.transport_date)
                if not ok:
                    row_errors.append(msg)
                    w.add_exception(msg)

            if w.net_weight <= 0:
                msg = f"净重异常: {w.net_weight}"
                row_errors.append(msg)
                w.add_exception(msg)

            if not w.loading_point_name and not w.loading_point_id:
                msg = "缺少装车点记录"
                w.add_exception(msg)

            if row_errors:
                warning_count += len(row_errors)
                errors.append({
                    "行号": idx + 2,
                    "运单号": w.waybill_no,
                    "车牌": w.license_plate,
                    "错误": "; ".join(row_errors)
                })

            waybills.append(w)
        except Exception as e:
            errors.append({
                "行号": idx + 2,
                "运单号": "",
                "车牌": "",
                "错误": f"解析失败: {str(e)}"
            })

    click.echo(f"\n解析完成: 成功 {len(waybills)} 条, 问题 {len(errors)} 条, 警告 {warning_count} 条")

    if errors:
        print_table(
            [[e["行号"], e["运单号"], e["车牌"], e["错误"]] for e in errors[:20]],
            ["行号", "运单号", "车牌", "问题描述"],
            "导入问题清单 (最多显示20条)"
        )
        if len(errors) > 20:
            click.echo(f"  ... 还有 {len(errors) - 20} 条问题未显示")

    if dry_run:
        click.echo("\n⚠️  试运行模式，未保存任何数据")
        return

    seq = len(store.load_import_batches()) + 1
    batch_no = generate_serial_no("IMP", seq)
    batch = ImportBatch(
        batch_no=batch_no,
        import_type="运单",
        source_file=filepath,
        total_count=len(waybills),
        success_count=len(waybills) - len(errors),
        error_count=len(errors),
        warning_count=warning_count,
        duplicate_count=sum(1 for w in waybills if w.is_duplicate),
        exception_count=sum(1 for w in waybills if w.exceptions),
        operator="导入系统",
        error_details=errors[:200],
        remark=f"从 {os.path.basename(filepath)} 导入运单"
    )

    for w in waybills:
        w.import_batch_id = batch.id
        batch.waybill_ids.append(w.id)

    count = store.add_waybills_batch(waybills)
    store.add_import_batch(batch)

    click.echo(f"\n✅ 成功导入运单: {count} 条 (批次号: {batch_no})")

    summary = []
    total_net = sum(w.net_weight for w in waybills)
    total_gross = sum(w.gross_weight for w in waybills)
    summary.append(["批次号", batch_no])
    summary.append(["总条数", f"{len(waybills)} 条"])
    summary.append(["总毛重", f"{total_gross:.3f} 吨"])
    summary.append(["总净重", f"{total_net:.3f} 吨"])
    summary.append(["异常单数", f"{batch.exception_count} 条"])
    print_table(summary, ["统计项", "数值"], "导入汇总")


def _import_weight_notes(store: DataStore, df: pd.DataFrame, filepath: str, dry_run: bool):
    """导入磅单照片清单"""
    df = _map_columns(df, WEIGHT_NOTE_COLUMN_MAPPING)
    click.echo(f"\n识别字段: {', '.join(c for c in df.columns if c in WEIGHT_NOTE_COLUMN_MAPPING.values())}")

    notes: List[WeightNote] = []
    errors: List[Dict[str, Any]] = []

    for idx, row in df.iterrows():
        try:
            n = _row_to_weight_note(row, idx)
            row_errors = []

            if not n.weight_note_no:
                row_errors.append("缺少磅单号")

            if n.net_weight <= 0 and n.gross_weight <= 0:
                row_errors.append("缺少重量数据")

            if row_errors:
                errors.append({
                    "行号": idx + 2,
                    "磅单号": n.weight_note_no,
                    "错误": "; ".join(row_errors)
                })

            notes.append(n)
        except Exception as e:
            errors.append({
                "行号": idx + 2,
                "磅单号": "",
                "错误": f"解析失败: {str(e)}"
            })

    click.echo(f"\n解析完成: 成功 {len(notes)} 条, 问题 {len(errors)} 条")

    if errors:
        print_table(
            [[e["行号"], e["磅单号"], e["错误"]] for e in errors[:20]],
            ["行号", "磅单号", "问题描述"],
            "导入问题清单 (最多显示20条)"
        )

    if dry_run:
        click.echo("\n⚠️  试运行模式，未保存任何数据")
        return

    seq = len(store.load_import_batches()) + 1
    batch_no = generate_serial_no("IMP", seq)
    batch = ImportBatch(
        batch_no=batch_no,
        import_type="磅单照片",
        source_file=filepath,
        total_count=len(notes),
        success_count=len(notes) - len(errors),
        error_count=len(errors),
        warning_count=0,
        duplicate_count=0,
        exception_count=len(errors),
        operator="导入系统",
        error_details=errors[:200],
        remark=f"从 {os.path.basename(filepath)} 导入磅单照片清单"
    )

    for n in notes:
        batch.weight_note_ids.append(n.id)

    count = store.add_weight_notes_batch(notes)
    matched = 0
    waybills = store.load_waybills()
    wn_map = {}
    for w in waybills:
        if w.weight_note_no:
            wn_map.setdefault(w.weight_note_no, []).append(w)

    for n in notes:
        if n.weight_note_no in wn_map:
            matched_wbs = wn_map[n.weight_note_no]
            if matched_wbs:
                w = matched_wbs[0]
                n.matched = True
                n.matched_waybill_id = w.id
                w.weight_note_photo = n.photo_path or n.photo_name
                w.exceptions = [e for e in w.exceptions if "磅单" not in e]
                matched += 1

    if matched > 0:
        store.save_weight_notes(notes)
        store.save_waybills(waybills)

    batch.remark += f"，匹配运单{matched}条"
    store.add_import_batch(batch)

    click.echo(f"\n✅ 成功导入磅单照片清单: {count} 条 (批次号: {batch_no})")

    summary = []
    summary.append(["批次号", batch_no])
    summary.append(["总条数", f"{len(notes)} 条"])
    summary.append(["匹配运单", f"{matched} 条"])
    summary.append(["未匹配", f"{len(notes) - matched} 条"])
    print_table(summary, ["统计项", "数值"], "导入汇总")

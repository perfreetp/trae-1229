"""通用工具函数"""
import re
import os
from typing import List, Dict, Any, Optional, Tuple, Callable
from datetime import datetime, date
from collections import defaultdict

import pandas as pd
from tabulate import tabulate

from .models import Waybill, PricingRule, Driver, Vehicle, LoadingPoint


LICENSE_PLATE_PATTERN = re.compile(
    r'^[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼使领][A-Z][A-Z0-9]{4,5}[A-Z0-9挂学警港澳]$'
)

CHINESE_NAME_PATTERN = re.compile(r'^[\u4e00-\u9fa5·]{2,10}$')
PHONE_PATTERN = re.compile(r'^1[3-9]\d{9}$')
ID_CARD_PATTERN = re.compile(r'^\d{17}[\dXx]$')


def validate_license_plate(plate: str) -> Tuple[bool, str]:
    """校验车牌号"""
    if not plate or not plate.strip():
        return False, "车牌号不能为空"
    plate = plate.strip().upper().replace(" ", "")
    if LICENSE_PLATE_PATTERN.match(plate):
        return True, ""
    return False, f"车牌号格式不正确: {plate}"


def validate_driver_name(name: str) -> Tuple[bool, str]:
    """校验司机姓名"""
    if not name or not name.strip():
        return False, "司机姓名不能为空"
    name = name.strip()
    if CHINESE_NAME_PATTERN.match(name):
        return True, ""
    return False, f"姓名格式不正确: {name}"


def validate_phone(phone: str) -> Tuple[bool, str]:
    """校验手机号"""
    if not phone:
        return True, ""
    phone = phone.strip()
    if PHONE_PATTERN.match(phone):
        return True, ""
    return False, f"手机号格式不正确: {phone}"


def validate_id_card(id_card: str) -> Tuple[bool, str]:
    """校验身份证号"""
    if not id_card:
        return True, ""
    id_card = id_card.strip().upper()
    if ID_CARD_PATTERN.match(id_card):
        return True, ""
    return False, f"身份证号格式不正确: {id_card}"


def validate_weight(gross: float, tare: float, net: float) -> Tuple[bool, str]:
    """校验重量数据"""
    if gross <= 0:
        return False, f"毛重必须大于0: {gross}"
    if tare <= 0:
        return False, f"皮重必须大于0: {tare}"
    if net <= 0:
        return False, f"净重必须大于0: {net}"
    if tare >= gross:
        return False, f"皮重({tare})不能大于等于毛重({gross})"
    calculated_net = round(gross - tare, 3)
    if abs(calculated_net - net) > 0.01:
        return False, f"净重({net})与毛重减皮重({calculated_net})不符"
    return True, ""


def validate_date(date_str: str) -> Tuple[bool, str]:
    """校验日期格式"""
    if not date_str:
        return False, "日期不能为空"
    for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%Y-%m-%d %H:%M:%S"]:
        try:
            datetime.strptime(date_str.strip(), fmt)
            return True, ""
        except ValueError:
            continue
    return False, f"日期格式不正确: {date_str}"


def normalize_date(date_str: str) -> str:
    """标准化日期为 YYYY-MM-DD 格式"""
    if not date_str:
        return ""
    date_str = date_str.strip()
    for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"]:
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    try:
        if isinstance(date_str, date) or (hasattr(date_str, 'year') and hasattr(date_str, 'month')):
            return date_str.strftime("%Y-%m-%d")
    except Exception:
        pass
    return date_str


def normalize_license_plate(plate: str) -> str:
    """标准化车牌号"""
    if not plate:
        return ""
    return plate.strip().upper().replace(" ", "")


def calculate_freight(
    net_weight: float,
    mileage: float,
    rule: Optional[PricingRule] = None,
    base_price: float = 0.0,
    price_per_km: float = 0.0
) -> float:
    """计算运费"""
    if net_weight <= 0:
        return 0.0

    if rule:
        bp = rule.base_price_per_ton
        ppk = rule.price_per_km_per_ton
        min_c = rule.min_charge
    else:
        bp = base_price
        ppk = price_per_km
        min_c = 0.0

    freight = net_weight * (bp + ppk * mileage)

    if rule and rule.mileage_threshold > 0 and mileage > rule.mileage_threshold:
        extra_mileage = mileage - rule.mileage_threshold
        freight += net_weight * rule.additional_price * extra_mileage

    freight = round(freight, 2)

    if min_c > 0 and freight < min_c:
        freight = min_c

    return freight


def calculate_bamboo_value(net_weight: float, unit_price: float) -> float:
    """计算竹子价值（竹农款项）"""
    if net_weight <= 0 or unit_price <= 0:
        return 0.0
    return round(net_weight * unit_price, 2)


def find_duplicate_waybills(waybills: List[Waybill]) -> Dict[str, List[str]]:
    """查找重复运单
    重复判定规则：相同车牌号 + 相同日期 + (相同净重 或 相同磅单号)
    """
    groups: Dict[str, List[str]] = defaultdict(list)

    for w in waybills:
        if w.is_merged or w.is_split:
            continue
        plate = normalize_license_plate(w.license_plate)
        dt = normalize_date(w.transport_date)
        net = round(w.net_weight, 2) if w.net_weight else 0
        wn = w.weight_note_no.strip() if w.weight_note_no else ""

        key1 = f"{plate}|{dt}|{net}"
        key2 = f"{plate}|{dt}|{wn}" if wn else None

        groups[key1].append(w.id)
        if key2:
            groups[key2].append(w.id)

    duplicates: Dict[str, List[str]] = {}
    for key, ids in groups.items():
        if len(ids) > 1:
            for wid in ids:
                if wid not in duplicates:
                    others = [i for i in ids if i != wid]
                    duplicates[wid] = others

    return duplicates


def find_missing_loading_points(waybills: List[Waybill]) -> List[str]:
    """识别缺少装车点记录的运单"""
    missing = []
    for w in waybills:
        if not w.loading_point_id and not w.loading_point_name:
            missing.append(w.id)
        elif w.loading_point_name and not w.loading_point_id:
            missing.append(w.id)
    return missing


def find_weight_mismatch(waybills: List[Waybill]) -> List[str]:
    """识别重量异常的运单"""
    mismatches = []
    for w in waybills:
        if w.gross_weight > 0 and w.tare_weight > 0 and w.net_weight > 0:
            calc = round(w.gross_weight - w.tare_weight, 3)
            if abs(calc - w.net_weight) > 0.01:
                mismatches.append(w.id)
    return mismatches


def read_excel_file(filepath: str, sheet_name: Optional[str] = None) -> pd.DataFrame:
    """读取 Excel 文件"""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"文件不存在: {filepath}")

    ext = os.path.splitext(filepath)[1].lower()
    if ext in [".xlsx", ".xls"]:
        df = pd.read_excel(filepath, sheet_name=sheet_name or 0, dtype=str)
    elif ext == ".csv":
        try:
            df = pd.read_csv(filepath, dtype=str, encoding="utf-8")
        except UnicodeDecodeError:
            df = pd.read_csv(filepath, dtype=str, encoding="gbk")
    else:
        raise ValueError(f"不支持的文件格式: {ext}")

    df.columns = [str(c).strip() for c in df.columns]
    return df


def safe_float(value: Any, default: float = 0.0) -> float:
    """安全转换为浮点数"""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return default
    s = s.replace(",", "").replace("，", "").replace("吨", "").replace("kg", "").replace("KG", "")
    try:
        return float(s)
    except ValueError:
        return default


def safe_str(value: Any) -> str:
    """安全转换为字符串"""
    if value is None:
        return ""
    if pd.isna(value):
        return ""
    return str(value).strip()


def print_table(data: List[List[Any]], headers: List[str], title: str = ""):
    """打印表格"""
    if title:
        print(f"\n{'=' * 60}")
        print(f"  {title}")
        print(f"{'=' * 60}")
    if not data:
        print("  (无数据)")
        return
    print(tabulate(data, headers=headers, tablefmt="simple", showindex=False))
    print()


def format_money(amount: float) -> str:
    """格式化金额"""
    return f"¥{amount:,.2f}"


def format_weight(weight: float) -> str:
    """格式化重量"""
    return f"{weight:,.3f}吨"


def generate_serial_no(prefix: str, seq: int) -> str:
    """生成流水号"""
    today = datetime.now().strftime("%Y%m%d")
    return f"{prefix}{today}{seq:04d}"


def export_to_excel(
    data: List[Dict[str, Any]],
    filepath: str,
    sheet_name: str = "Sheet1",
    columns: Optional[List[Tuple[str, str]]] = None
):
    """导出数据到 Excel"""
    if not data:
        df = pd.DataFrame()
    else:
        df = pd.DataFrame(data)
        if columns:
            col_map = {old: new for old, new in columns}
            existing_cols = [c for c, _ in columns if c in df.columns]
            df = df[existing_cols]
            df.rename(columns=col_map, inplace=True)

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    df.to_excel(filepath, sheet_name=sheet_name, index=False, engine="openpyxl")
    return filepath


def get_date_range(start_date: str, end_date: str) -> List[str]:
    """获取日期范围内的所有日期"""
    from datetime import timedelta
    start = datetime.strptime(normalize_date(start_date), "%Y-%m-%d")
    end = datetime.strptime(normalize_date(end_date), "%Y-%m-%d")
    dates = []
    current = start
    while current <= end:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return dates


def is_within_date_range(date_str: str, start_date: str, end_date: str) -> bool:
    """判断日期是否在范围内"""
    d = normalize_date(date_str)
    s = normalize_date(start_date)
    e = normalize_date(end_date)
    return s <= d <= e


def is_effective_waybill(w: Waybill) -> bool:
    """判断运单是否为最终有效的运单（用于报表、结算等统计场景）

    有效运单定义：
      - 不是重复运单 (is_duplicate=False)
      - 如果是合并后的运单：保留合并产生的新单（is_merged=True 且 merged_ids 非空）
                           排除被合并掉的原单（is_merged=True 且 merged_ids 为空）
      - 如果是拆分后的运单：保留拆分产生的子单（is_split=True 且 split_parent_id 非空）
                           排除被拆分掉的原单（is_split=True 且 split_parent_id 为空）
      - 其他普通运单：正常保留
    """
    if w.is_duplicate:
        return False
    if w.is_merged and not w.merged_ids:
        return False
    if w.is_split and not w.split_parent_id:
        return False
    return True


def filter_effective_waybills(waybills: List[Waybill]) -> List[Waybill]:
    """过滤出最终有效的运单列表"""
    return [w for w in waybills if is_effective_waybill(w)]


def get_waybill_status_label(w: Waybill) -> str:
    """获取运单的状态标签，用于搜索列表，避免重复显示"""
    tags = []
    if w.is_duplicate:
        tags.append("重复")
    elif w.is_merged:
        if w.merged_ids:
            tags.append("合并结果")
        else:
            tags.append("已被合并")
    elif w.is_split:
        if w.split_parent_id:
            tags.append("拆分子单")
        else:
            tags.append("已被拆分")
    return ", ".join(tags)


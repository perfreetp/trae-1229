"""数据模型定义"""
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from datetime import datetime, date
import uuid


def _generate_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class BambooType:
    """竹种"""
    id: str = field(default_factory=_generate_id)
    name: str = ""
    code: str = ""
    unit_price: float = 0.0
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BambooType":
        return cls(**data)


@dataclass
class LoadingPoint:
    """装车点"""
    id: str = field(default_factory=_generate_id)
    name: str = ""
    address: str = ""
    contact: str = ""
    phone: str = ""
    mileage: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LoadingPoint":
        return cls(**data)


@dataclass
class PurchasePoint:
    """收购点"""
    id: str = field(default_factory=_generate_id)
    name: str = ""
    address: str = ""
    contact: str = ""
    phone: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PurchasePoint":
        return cls(**data)


@dataclass
class Driver:
    """司机"""
    id: str = field(default_factory=_generate_id)
    name: str = ""
    phone: str = ""
    id_card: str = ""
    license_plate: str = ""
    bank_account: str = ""
    bank_name: str = ""
    remark: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Driver":
        return cls(**data)


@dataclass
class Vehicle:
    """车辆"""
    id: str = field(default_factory=_generate_id)
    license_plate: str = ""
    driver_id: str = ""
    driver_name: str = ""
    vehicle_type: str = ""
    load_capacity: float = 0.0
    remark: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Vehicle":
        return cls(**data)


@dataclass
class PricingRule:
    """计价规则"""
    id: str = field(default_factory=_generate_id)
    bamboo_type_id: str = ""
    bamboo_type_name: str = ""
    base_price_per_ton: float = 0.0
    price_per_km_per_ton: float = 0.0
    min_charge: float = 0.0
    mileage_threshold: float = 0.0
    additional_price: float = 0.0
    effective_date: str = ""
    remark: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PricingRule":
        return cls(**data)


@dataclass
class Waybill:
    """运单"""
    id: str = field(default_factory=_generate_id)
    waybill_no: str = ""
    transport_date: str = ""
    license_plate: str = ""
    driver_id: str = ""
    driver_name: str = ""
    driver_phone: str = ""
    bamboo_type_id: str = ""
    bamboo_type_name: str = ""
    loading_point_id: str = ""
    loading_point_name: str = ""
    purchase_point_id: str = ""
    purchase_point_name: str = ""
    mileage: float = 0.0
    gross_weight: float = 0.0
    tare_weight: float = 0.0
    net_weight: float = 0.0
    unit_price: float = 0.0
    freight: float = 0.0
    bamboo_value: float = 0.0
    weight_note_no: str = ""
    weight_note_photo: str = ""
    waybill_photo: str = ""
    is_duplicate: bool = False
    duplicate_of: str = ""
    is_merged: bool = False
    merged_ids: List[str] = field(default_factory=list)
    is_split: bool = False
    split_parent_id: str = ""
    split_remark: str = ""
    is_paid: bool = False
    paid_amount: float = 0.0
    paid_date: str = ""
    paid_remark: str = ""
    payment_target: str = ""
    farmer_id: str = ""
    farmer_name: str = ""
    farmer_phone: str = ""
    farmer_bank_account: str = ""
    farmer_bank_name: str = ""
    farmer_amount: float = 0.0
    remark: str = ""
    exceptions: List[str] = field(default_factory=list)
    manual_notes: List[Dict[str, str]] = field(default_factory=list)
    import_batch_id: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Waybill":
        return cls(**data)

    def add_exception(self, exception: str):
        if exception not in self.exceptions:
            self.exceptions.append(exception)
        self.updated_at = datetime.now().isoformat()

    def add_note(self, content: str, operator: str = "系统"):
        self.manual_notes.append({
            "time": datetime.now().isoformat(),
            "operator": operator,
            "content": content
        })
        self.updated_at = datetime.now().isoformat()


@dataclass
class WeightNote:
    """磅单照片清单"""
    id: str = field(default_factory=_generate_id)
    weight_note_no: str = ""
    photo_path: str = ""
    photo_name: str = ""
    transport_date: str = ""
    license_plate: str = ""
    gross_weight: float = 0.0
    tare_weight: float = 0.0
    net_weight: float = 0.0
    matched: bool = False
    matched_waybill_id: str = ""
    remark: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WeightNote":
        return cls(**data)


@dataclass
class Settlement:
    """结算记录"""
    id: str = field(default_factory=_generate_id)
    settlement_no: str = ""
    settlement_date: str = ""
    settlement_type: str = ""
    target_id: str = ""
    target_name: str = ""
    waybill_ids: List[str] = field(default_factory=list)
    total_weight: float = 0.0
    total_freight: float = 0.0
    total_bamboo_value: float = 0.0
    total_amount: float = 0.0
    paid_amount: float = 0.0
    unpaid_amount: float = 0.0
    status: str = "待结算"
    remark: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Settlement":
        return cls(**data)


@dataclass
class ImportBatch:
    """导入批次记录"""
    id: str = field(default_factory=_generate_id)
    batch_no: str = ""
    import_type: str = ""
    source_file: str = ""
    total_count: int = 0
    success_count: int = 0
    error_count: int = 0
    warning_count: int = 0
    duplicate_count: int = 0
    exception_count: int = 0
    operator: str = ""
    import_time: str = field(default_factory=lambda: datetime.now().isoformat())
    waybill_ids: List[str] = field(default_factory=list)
    weight_note_ids: List[str] = field(default_factory=list)
    error_details: List[Dict[str, Any]] = field(default_factory=list)
    duplicate_details: List[Dict[str, Any]] = field(default_factory=list)
    is_rollback: bool = False
    rollback_time: str = ""
    rollback_operator: str = ""
    remark: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ImportBatch":
        return cls(**data)

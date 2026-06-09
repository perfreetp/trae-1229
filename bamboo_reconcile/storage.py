"""数据存储层"""
import json
import os
from typing import List, Dict, Any, Optional, TypeVar, Type
from pathlib import Path
import copy

from .models import (
    Waybill, WeightNote, PricingRule, Driver, Vehicle,
    BambooType, LoadingPoint, PurchasePoint, Settlement
)

T = TypeVar("T")

DEFAULT_DATA_DIR = os.path.join(os.path.expanduser("~"), ".bamboo_reconcile")


class DataStore:
    """JSON文件数据存储"""

    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir = data_dir or DEFAULT_DATA_DIR
        self._ensure_dirs()
        self._files = {
            "waybills": os.path.join(self.data_dir, "waybills.json"),
            "weight_notes": os.path.join(self.data_dir, "weight_notes.json"),
            "pricing_rules": os.path.join(self.data_dir, "pricing_rules.json"),
            "drivers": os.path.join(self.data_dir, "drivers.json"),
            "vehicles": os.path.join(self.data_dir, "vehicles.json"),
            "bamboo_types": os.path.join(self.data_dir, "bamboo_types.json"),
            "loading_points": os.path.join(self.data_dir, "loading_points.json"),
            "purchase_points": os.path.join(self.data_dir, "purchase_points.json"),
            "settlements": os.path.join(self.data_dir, "settlements.json"),
            "settings": os.path.join(self.data_dir, "settings.json"),
        }
        self._init_files()

    def _ensure_dirs(self):
        Path(self.data_dir).mkdir(parents=True, exist_ok=True)
        Path(os.path.join(self.data_dir, "exports")).mkdir(parents=True, exist_ok=True)
        Path(os.path.join(self.data_dir, "exports", "reports")).mkdir(parents=True, exist_ok=True)
        Path(os.path.join(self.data_dir, "exports", "settlements")).mkdir(parents=True, exist_ok=True)

    def _init_files(self):
        for key, filepath in self._files.items():
            if not os.path.exists(filepath):
                if key == "settings":
                    self._write_json(filepath, {"version": "1.0.0", "created": ""})
                else:
                    self._write_json(filepath, [])

    @staticmethod
    def _read_json(filepath: str) -> Any:
        if not os.path.exists(filepath):
            return []
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return []

    @staticmethod
    def _write_json(filepath: str, data: Any):
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load_all(self, key: str, model_cls: Type[T]) -> List[T]:
        data = self._read_json(self._files[key])
        if not isinstance(data, list):
            return []
        return [model_cls.from_dict(item) for item in data]

    def _save_all(self, key: str, items: List[Any]):
        data = [item.to_dict() for item in items]
        self._write_json(self._files[key], data)

    # ===== Waybills =====
    def load_waybills(self) -> List[Waybill]:
        return self._load_all("waybills", Waybill)

    def save_waybills(self, waybills: List[Waybill]):
        self._save_all("waybills", waybills)

    def add_waybill(self, waybill: Waybill) -> Waybill:
        waybills = self.load_waybills()
        waybills.append(waybill)
        self.save_waybills(waybills)
        return waybill

    def add_waybills_batch(self, waybills: List[Waybill]) -> int:
        existing = self.load_waybills()
        existing.extend(waybills)
        self.save_waybills(existing)
        return len(waybills)

    def update_waybill(self, waybill: Waybill) -> bool:
        waybills = self.load_waybills()
        for i, w in enumerate(waybills):
            if w.id == waybill.id:
                waybills[i] = waybill
                self.save_waybills(waybills)
                return True
        return False

    def update_waybills_batch(self, waybills: List[Waybill]) -> int:
        existing = self.load_waybills()
        id_map = {w.id: w for w in waybills}
        count = 0
        for i, w in enumerate(existing):
            if w.id in id_map:
                existing[i] = id_map[w.id]
                count += 1
        if count > 0:
            self.save_waybills(existing)
        return count

    def delete_waybill(self, waybill_id: str) -> bool:
        waybills = self.load_waybills()
        original_len = len(waybills)
        waybills = [w for w in waybills if w.id != waybill_id]
        if len(waybills) != original_len:
            self.save_waybills(waybills)
            return True
        return False

    def find_waybill(self, waybill_id: str) -> Optional[Waybill]:
        for w in self.load_waybills():
            if w.id == waybill_id:
                return w
        return None

    # ===== Weight Notes =====
    def load_weight_notes(self) -> List[WeightNote]:
        return self._load_all("weight_notes", WeightNote)

    def save_weight_notes(self, notes: List[WeightNote]):
        self._save_all("weight_notes", notes)

    def add_weight_note(self, note: WeightNote) -> WeightNote:
        notes = self.load_weight_notes()
        notes.append(note)
        self.save_weight_notes(notes)
        return note

    def add_weight_notes_batch(self, notes: List[WeightNote]) -> int:
        existing = self.load_weight_notes()
        existing.extend(notes)
        self.save_weight_notes(existing)
        return len(notes)

    def update_weight_note(self, note: WeightNote) -> bool:
        notes = self.load_weight_notes()
        for i, n in enumerate(notes):
            if n.id == note.id:
                notes[i] = note
                self.save_weight_notes(notes)
                return True
        return False

    # ===== Pricing Rules =====
    def load_pricing_rules(self) -> List[PricingRule]:
        return self._load_all("pricing_rules", PricingRule)

    def save_pricing_rules(self, rules: List[PricingRule]):
        self._save_all("pricing_rules", rules)

    def add_pricing_rule(self, rule: PricingRule) -> PricingRule:
        rules = self.load_pricing_rules()
        rules.append(rule)
        self.save_pricing_rules(rules)
        return rule

    def update_pricing_rule(self, rule: PricingRule) -> bool:
        rules = self.load_pricing_rules()
        for i, r in enumerate(rules):
            if r.id == rule.id:
                rules[i] = rule
                self.save_pricing_rules(rules)
                return True
        return False

    def get_pricing_rule_by_bamboo(self, bamboo_type_id: str) -> Optional[PricingRule]:
        for r in self.load_pricing_rules():
            if r.bamboo_type_id == bamboo_type_id:
                return r
        return None

    # ===== Drivers =====
    def load_drivers(self) -> List[Driver]:
        return self._load_all("drivers", Driver)

    def save_drivers(self, drivers: List[Driver]):
        self._save_all("drivers", drivers)

    def add_driver(self, driver: Driver) -> Driver:
        drivers = self.load_drivers()
        drivers.append(driver)
        self.save_drivers(drivers)
        return driver

    def find_driver_by_plate(self, license_plate: str) -> Optional[Driver]:
        for d in self.load_drivers():
            if d.license_plate == license_plate:
                return d
        return None

    def find_driver_by_name(self, name: str) -> Optional[Driver]:
        for d in self.load_drivers():
            if d.name == name:
                return d
        return None

    # ===== Vehicles =====
    def load_vehicles(self) -> List[Vehicle]:
        return self._load_all("vehicles", Vehicle)

    def save_vehicles(self, vehicles: List[Vehicle]):
        self._save_all("vehicles", vehicles)

    def find_vehicle_by_plate(self, license_plate: str) -> Optional[Vehicle]:
        for v in self.load_vehicles():
            if v.license_plate == license_plate:
                return v
        return None

    # ===== Bamboo Types =====
    def load_bamboo_types(self) -> List[BambooType]:
        return self._load_all("bamboo_types", BambooType)

    def save_bamboo_types(self, types: List[BambooType]):
        self._save_all("bamboo_types", types)

    def add_bamboo_type(self, bamboo: BambooType) -> BambooType:
        types = self.load_bamboo_types()
        types.append(bamboo)
        self.save_bamboo_types(types)
        return bamboo

    def find_bamboo_by_name(self, name: str) -> Optional[BambooType]:
        for b in self.load_bamboo_types():
            if b.name == name:
                return b
        return None

    def find_bamboo_by_code(self, code: str) -> Optional[BambooType]:
        for b in self.load_bamboo_types():
            if b.code == code:
                return b
        return None

    # ===== Loading Points =====
    def load_loading_points(self) -> List[LoadingPoint]:
        return self._load_all("loading_points", LoadingPoint)

    def save_loading_points(self, points: List[LoadingPoint]):
        self._save_all("loading_points", points)

    def add_loading_point(self, point: LoadingPoint) -> LoadingPoint:
        points = self.load_loading_points()
        points.append(point)
        self.save_loading_points(points)
        return point

    def find_loading_point_by_name(self, name: str) -> Optional[LoadingPoint]:
        for p in self.load_loading_points():
            if p.name == name:
                return p
        return None

    # ===== Purchase Points =====
    def load_purchase_points(self) -> List[PurchasePoint]:
        return self._load_all("purchase_points", PurchasePoint)

    def save_purchase_points(self, points: List[PurchasePoint]):
        self._save_all("purchase_points", points)

    def add_purchase_point(self, point: PurchasePoint) -> PurchasePoint:
        points = self.load_purchase_points()
        points.append(point)
        self.save_purchase_points(points)
        return point

    def find_purchase_point_by_name(self, name: str) -> Optional[PurchasePoint]:
        for p in self.load_purchase_points():
            if p.name == name:
                return p
        return None

    # ===== Settlements =====
    def load_settlements(self) -> List[Settlement]:
        return self._load_all("settlements", Settlement)

    def save_settlements(self, settlements: List[Settlement]):
        self._save_all("settlements", settlements)

    def add_settlement(self, settlement: Settlement) -> Settlement:
        settlements = self.load_settlements()
        settlements.append(settlement)
        self.save_settlements(settlements)
        return settlement

    # ===== Settings =====
    def get_settings(self) -> Dict[str, Any]:
        data = self._read_json(self._files["settings"])
        if isinstance(data, dict):
            return data
        return {}

    def save_settings(self, settings: Dict[str, Any]):
        self._write_json(self._files["settings"], settings)

    # ===== Export Paths =====
    def get_export_dir(self) -> str:
        return os.path.join(self.data_dir, "exports")

    def get_report_dir(self) -> str:
        return os.path.join(self.data_dir, "exports", "reports")

    def get_settlement_dir(self) -> str:
        return os.path.join(self.data_dir, "exports", "settlements")

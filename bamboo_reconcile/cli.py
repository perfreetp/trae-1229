"""命令行工具主入口 - 彭州竹子运输对账助手"""
import os
import sys

import click

from . import __version__
from .storage import DataStore
from .commands.import_cmd import cmd_import
from .commands.check_cmd import cmd_check
from .commands.price_cmd import price
from .commands.merge_cmd import cmd_merge
from .commands.split_cmd import cmd_split
from .commands.settle_cmd import settle
from .commands.report_cmd import report
from .commands.search_cmd import search


BANNER = r"""
 ____  ____   __  __  ____   ___   ___    __    ____
(  _ \(  _ \ (  \/  )( ___) / __) / __)  /__\  (  _ \
 )___/ )(_) ))    (  )__) ( (__ ( (__  /(__)\  )   /
(__)  (____/(_/\/\_)(____) \___) \___)(__)(__)(_)\_)

  彭州竹子运输对账助手  v{version}
  合作社财务 & 车队调度 批量运单核对工具
""".format(version=__version__)


@click.group(
    help="彭州竹子运输对账助手 - 供合作社财务和车队调度批量核对运单\n\n"
         "命令列表:\n"
         "  import  - 导入运单文件和磅单照片清单\n"
         "  check   - 校验数据（车牌/司机/重复/装车点/重量/磅单）\n"
         "  price   - 计价规则管理与运费计算\n"
         "  merge   - 合并同车多趟运单\n"
         "  split   - 拆分多人分账\n"
         "  settle  - 结算管理（付款标记/司机结算单/竹农付款清单）\n"
         "  report  - 生成对账报表与汇总\n"
         "  search  - 搜索运单与管理备注",
    context_settings=dict(help_option_names=["-h", "--help"], max_content_width=120)
)
@click.version_option(__version__, "-V", "--version", prog_name="bamboo")
@click.option("--data-dir", default=None, envvar="BAMBOO_DATA_DIR",
              type=click.Path(file_okay=False), help="数据存储目录，默认 ~/.bamboo_reconcile")
@click.option("--quiet", "-q", is_flag=True, help="静默模式，不显示 Banner")
@click.pass_context
def cli(ctx: click.Context, data_dir: str, quiet: bool):
    """主命令组入口"""
    if not quiet and ctx.invoked_subcommand is None:
        click.echo(BANNER)
    elif not quiet:
        click.echo()

    ctx.ensure_object(dict)
    store = DataStore(data_dir=data_dir)
    ctx.obj["store"] = store
    ctx.obj["data_dir"] = store.data_dir


cli.add_command(cmd_import)
cli.add_command(cmd_check)
cli.add_command(price)
cli.add_command(cmd_merge)
cli.add_command(cmd_split)
cli.add_command(settle)
cli.add_command(report)
cli.add_command(search)


@cli.command("init")
@click.option("--sample-data", is_flag=True, help="初始化示例数据")
@click.option("--force", is_flag=True, help="强制重置现有数据")
@click.pass_context
def cmd_init(ctx, sample_data: bool, force: bool):
    """初始化数据目录，创建基础档案

    \b
    示例:
      bamboo init
      bamboo init --sample-data
      bamboo init --force
    """
    store: DataStore = ctx.obj["store"]
    data_dir = ctx.obj["data_dir"]

    existing = any([
        os.path.exists(os.path.join(data_dir, f)) and
        os.path.getsize(os.path.join(data_dir, f)) > 10
        for f in ["waybills.json", "drivers.json", "pricing_rules.json"]
    ])

    if existing and not force:
        click.echo(f"\n⚠️  检测到已有数据目录: {data_dir}")
        click.echo("   如需重置请使用 --force 参数")
        if not click.confirm("是否继续（将追加数据而不覆盖）？"):
            click.echo("已取消")
            return

    click.echo(f"\n📁 数据目录: {data_dir}")
    click.echo("初始化基础档案...")

    from .models import BambooType, LoadingPoint, PurchasePoint, Driver, Vehicle, PricingRule
    from datetime import datetime

    if not store.load_bamboo_types() or force:
        bamboos = [
            BambooType(name="毛竹", code="MZ", unit_price=850.0, description="主产竹种"),
            BambooType(name="楠竹", code="NZ", unit_price=950.0, description="大径竹种"),
            BambooType(name="慈竹", code="CZ", unit_price=650.0, description="编织用竹"),
            BambooType(name="刚竹", code="GZ", unit_price=750.0, description="建材用竹"),
            BambooType(name="杂竹", code="ZZ", unit_price=450.0, description="其他竹种"),
        ]
        if force:
            store.save_bamboo_types(bamboos)
        else:
            for b in bamboos:
                if not store.find_bamboo_by_name(b.name):
                    store.add_bamboo_type(b)
        click.echo(f"  ✅ 竹种档案: {len(bamboos)} 种")

    if not store.load_loading_points() or force:
        points = [
            LoadingPoint(name="丹景山镇装车点", address="彭州市丹景山镇", mileage=28.5, contact="王师傅"),
            LoadingPoint(name="隆丰街道装车点", address="彭州市隆丰街道", mileage=15.2, contact="李师傅"),
            LoadingPoint(name="濛阳街道装车点", address="彭州市濛阳街道", mileage=32.0, contact="张师傅"),
            LoadingPoint(name="丽春镇装车点", address="彭州市丽春镇", mileage=22.8, contact="赵师傅"),
            LoadingPoint(name="桂花镇装车点", address="彭州市桂花镇", mileage=38.5, contact="钱师傅"),
            LoadingPoint(name="通济镇装车点", address="彭州市通济镇", mileage=45.0, contact="孙师傅"),
            LoadingPoint(name="白鹿镇装车点", address="彭州市白鹿镇", mileage=52.3, contact="周师傅"),
            LoadingPoint(name="小渔洞装车点", address="彭州市小渔洞镇", mileage=48.0, contact="吴师傅"),
        ]
        if force:
            store.save_loading_points(points)
        else:
            for p in points:
                if not store.find_loading_point_by_name(p.name):
                    store.add_loading_point(p)
        click.echo(f"  ✅ 装车点档案: {len(points)} 个")

    if not store.load_purchase_points() or force:
        purchases = [
            PurchasePoint(name="彭州市竹业加工厂", address="彭州市天彭街道", contact="刘主任"),
            PurchasePoint(name="濛阳竹产品交易市场", address="彭州市濛阳街道", contact="陈经理"),
            PurchasePoint(name="龙门山竹业合作社", address="彭州市龙门山镇", contact="杨社长"),
        ]
        if force:
            store.save_purchase_points(purchases)
        else:
            for p in purchases:
                if not store.find_purchase_point_by_name(p.name):
                    store.add_purchase_point(p)
        click.echo(f"  ✅ 收购点档案: {len(purchases)} 个")

    if not store.load_drivers() or force:
        drivers_data = [
            ("张建国", "川A38K52", "13880011234"),
            ("李明全", "川A72H19", "13880022345"),
            ("王富贵", "川A56M83", "13880033456"),
            ("赵德柱", "川A91B27", "13880044567"),
            ("孙永强", "川A45N68", "13880055678"),
            ("周发财", "川A63P41", "13880066789"),
            ("吴大志", "川A28Q75", "13880077890"),
            ("郑光明", "川A87R19", "13880088901"),
        ]
        drivers = []
        vehicles = []
        for i, (name, plate, phone) in enumerate(drivers_data):
            did = f"DR{i+1:04d}"
            vid = f"VH{i+1:04d}"
            d = Driver(id=did, name=name, phone=phone, license_plate=plate,
                       bank_account=f"62220200{i+1:012d}", bank_name="中国工商银行彭州支行")
            v = Vehicle(id=vid, license_plate=plate, driver_id=did, driver_name=name,
                        vehicle_type="中型自卸货车", load_capacity=15.0)
            drivers.append(d)
            vehicles.append(v)
        if force:
            store.save_drivers(drivers)
            store.save_vehicles(vehicles)
        else:
            for d in drivers:
                if not store.find_driver_by_plate(d.license_plate):
                    store.add_driver(d)
            for v in vehicles:
                if not store.find_vehicle_by_plate(v.license_plate):
                    store.add_vehicle(v)
        click.echo(f"  ✅ 司机档案: {len(drivers)} 人")
        click.echo(f"  ✅ 车辆档案: {len(vehicles)} 辆")

    if not store.load_pricing_rules() or force:
        rules = []
        bamboo_map = {b.name: b for b in store.load_bamboo_types()}
        price_configs = [
            ("毛竹", 18.0, 0.45, 50.0),
            ("楠竹", 22.0, 0.55, 60.0),
            ("慈竹", 15.0, 0.35, 40.0),
            ("刚竹", 16.0, 0.40, 45.0),
            ("杂竹", 12.0, 0.30, 35.0),
        ]
        for i, (bname, base, km, minc) in enumerate(price_configs):
            bamboo = bamboo_map.get(bname)
            if bamboo:
                rules.append(PricingRule(
                    id=f"PR{i+1:04d}",
                    bamboo_type_id=bamboo.id,
                    bamboo_type_name=bname,
                    base_price_per_ton=base,
                    price_per_km_per_ton=km,
                    min_charge=minc,
                    mileage_threshold=50.0,
                    additional_price=0.10,
                    effective_date=datetime.now().strftime("%Y-%m-%d"),
                    remark="标准计价"
                ))
        if force:
            store.save_pricing_rules(rules)
        else:
            for r in rules:
                if not store.get_pricing_rule_by_bamboo(r.bamboo_type_id):
                    store.add_pricing_rule(r)
        click.echo(f"  ✅ 计价规则: {len(rules)} 条")

    if sample_data:
        _create_sample_data(store)
        click.echo("  ✅ 已生成示例运单数据")

    settings = store.get_settings()
    settings["version"] = __version__
    settings["initialized"] = datetime.now().isoformat()
    settings["data_dir"] = data_dir
    store.save_settings(settings)

    click.echo(f"\n🎉 初始化完成！")
    click.echo(f"   数据目录: {data_dir}")
    click.echo(f"   下次使用: 直接运行 bamboo 命令即可")
    click.echo(f"   查看帮助: bamboo --help 或 bamboo <命令> --help")


def _create_sample_data(store: DataStore):
    """生成示例运单数据用于演示"""
    from .models import Waybill, _generate_id
    from .utils import calculate_freight, calculate_bamboo_value, normalize_license_plate
    import random
    from datetime import datetime, timedelta

    drivers = store.load_drivers()
    bamboos = store.load_bamboo_types()
    loading_points = store.load_loading_points()
    purchase_points = store.load_purchase_points()
    rules = {r.bamboo_type_id: r for r in store.load_pricing_rules()}

    waybills = []
    seq = 1
    start_date = datetime.now() - timedelta(days=30)

    farmers = [
        ("陈竹生", "13909011234", "6217000012345678", "中国建设银行彭州支行"),
        ("林竹根", "13909012345", "6217000023456789", "中国农业银行彭州支行"),
        ("黄竹海", "13909013456", "6217000034567890", "中国工商银行彭州支行"),
        ("徐竹林", "13909014567", "6217000045678901", "中国银行彭州支行"),
        ("何山竹", "13909015678", "6217000056789012", "中国邮政储蓄银行彭州支行"),
        ("罗竹叶", "13909016789", "6217000067890123", "中国建设银行彭州支行"),
        ("马竹坡", "13909017890", "6217000078901234", "中国农村商业银行彭州支行"),
    ]

    for day_offset in range(30):
        current_date = start_date + timedelta(days=day_offset)
        trips_per_day = random.randint(3, 10)

        for _ in range(trips_per_day):
            driver = random.choice(drivers) if drivers else None
            bamboo = random.choice(bamboos) if bamboos else None
            lp = random.choice(loading_points) if loading_points else None
            pp = random.choice(purchase_points) if purchase_points else None
            farmer = random.choice(farmers)

            gross = round(random.uniform(12.0, 18.5), 3)
            tare = round(random.uniform(4.5, 6.5), 3)
            net = round(gross - tare, 3)

            mileage = lp.mileage if lp else random.uniform(15, 55)
            rule = rules.get(bamboo.id) if bamboo else None

            freight = calculate_freight(net, mileage, rule)
            unit_price = bamboo.unit_price if bamboo else 700.0
            bamboo_value = calculate_bamboo_value(net, unit_price)

            paid = random.random() < 0.65

            w = Waybill(
                id=_generate_id(),
                waybill_no=f"WB{current_date.strftime('%Y%m%d')}{seq:04d}",
                transport_date=current_date.strftime("%Y-%m-%d"),
                license_plate=normalize_license_plate(driver.license_plate) if driver else "",
                driver_id=driver.id if driver else "",
                driver_name=driver.name if driver else "",
                driver_phone=driver.phone if driver else "",
                bamboo_type_id=bamboo.id if bamboo else "",
                bamboo_type_name=bamboo.name if bamboo else "",
                loading_point_id=lp.id if lp else "",
                loading_point_name=lp.name if lp else "",
                purchase_point_id=pp.id if pp else "",
                purchase_point_name=pp.name if pp else "",
                mileage=round(mileage, 1),
                gross_weight=gross,
                tare_weight=tare,
                net_weight=net,
                unit_price=unit_price,
                freight=freight,
                bamboo_value=bamboo_value,
                weight_note_no=f"BN{current_date.strftime('%Y%m%d')}{random.randint(1000, 9999)}",
                farmer_name=farmer[0],
                farmer_phone=farmer[1],
                farmer_bank_account=farmer[2],
                farmer_bank_name=farmer[3],
                farmer_amount=bamboo_value,
                is_paid=paid,
                paid_amount=freight + bamboo_value if paid else 0.0,
                paid_date=current_date.strftime("%Y-%m-%d") if paid else "",
                paid_remark=random.choice(["银行转账", "现金", "微信支付"]) if paid else ""
            )

            if random.random() < 0.08:
                w.license_plate = "川A???"
                w.add_exception("车牌号格式异常")
            if random.random() < 0.05:
                w.loading_point_name = ""
                w.loading_point_id = ""
                w.add_exception("缺少装车点记录")
            if random.random() < 0.03:
                w.net_weight = round(net * 1.05, 3)
                w.add_exception("净重不符")
            if random.random() < 0.04:
                w.weight_note_no = ""
                w.add_exception("缺少磅单号")
            if random.random() < 0.02:
                w.driver_name = ""
                w.add_exception("缺少司机姓名")

            waybills.append(w)
            seq += 1

    store.add_waybills_batch(waybills)


def main():
    """程序入口"""
    try:
        cli(obj={})
    except KeyboardInterrupt:
        click.echo("\n\n⚠️  操作已取消")
        sys.exit(130)
    except Exception as e:
        click.echo(f"\n❌ 运行出错: {e}", err=True)
        if "--debug" in sys.argv:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

"""split 命令 - 拆分多人分账"""
from typing import List, Dict, Any
from datetime import datetime
import copy

import click

from ..models import Waybill
from ..storage import DataStore
from ..utils import (
    print_table, format_money, format_weight, safe_float
)


@click.command("split")
@click.option("--id", "waybill_id", required=True, help="要拆分的运单ID或运单号")
@click.option("--by", "split_by",
              type=click.Choice(["weight", "amount", "ratio", "manual"]),
              default="ratio", help="拆分方式: weight(按重量), amount(按金额), ratio(按比例), manual(手动输入)")
@click.option("--count", type=int, default=2, help="拆分成几份，默认2份")
@click.option("--weights", default=None,
              help="按重量拆分时的各份重量，逗号分隔，如: 5.5,4.3,6.2")
@click.option("--amounts", default=None,
              help="按金额拆分时的各份运费，逗号分隔，如: 100,150,200")
@click.option("--ratios", default=None,
              help="按比例拆分时的各份比例，逗号分隔，总和应为100，如: 40,30,30")
@click.option("--farmer-names", default=None, help="各分账人姓名，逗号分隔")
@click.option("--list", "list_only", is_flag=True, help="只预览拆分结果，不实际保存")
@click.option("--yes", is_flag=True, help="跳过确认")
@click.pass_context
def cmd_split(
    ctx, waybill_id: str, split_by: str, count: int,
    weights: str, amounts: str, ratios: str, farmer_names: str,
    list_only: bool, yes: bool
):
    """拆分运单进行多人分账

    \b
    拆分方式说明:
      ratio   - 按比例拆分 (默认)，如 --ratios 60,40
      weight  - 按重量拆分，如 --weights 8.5,7.2
      amount  - 按金额拆分运费，如 --amounts 200,180
      manual  - 交互式手动输入各份分配

    \b
    示例:
      bamboo split --id WB00123 --by ratio --ratios 50,30,20 --count 3
      bamboo split --id WB00456 --by weight --weights 5.2,4.8
      bamboo split --id WB00789 --by amount --amounts 300,250 --farmer-names 张三,李四
    """
    store: DataStore = ctx.obj["store"]

    waybill = None
    all_waybills = store.load_waybills()
    for w in all_waybills:
        if w.id == waybill_id or w.waybill_no == waybill_id:
            waybill = w
            break

    if not waybill:
        click.echo(f"\n❌ 未找到运单: {waybill_id}", err=True)
        return

    if waybill.is_merged:
        click.echo(f"\n⚠️  运单 [{waybill.waybill_no}] 是合并后的运单，不建议再次拆分")
        if not click.confirm("是否继续拆分？"):
            click.echo("已取消")
            return

    if waybill.is_split:
        click.echo(f"\n❌ 运单 [{waybill.waybill_no}] 已被拆分，不能重复拆分", err=True)
        return

    click.echo(f"\n原运单信息:")
    orig_data = [
        ["运单号", waybill.waybill_no],
        ["运输日期", waybill.transport_date],
        ["车牌/司机", f"{waybill.license_plate} / {waybill.driver_name}"],
        ["竹种", waybill.bamboo_type_name],
        ["净重", format_weight(waybill.net_weight)],
        ["运费", format_money(waybill.freight)],
        ["竹款", format_money(waybill.bamboo_value)],
        ["竹农", waybill.farmer_name or "-"],
    ]
    print_table(orig_data, ["项目", "内容"], "原运单")

    farmer_list = []
    if farmer_names:
        farmer_list = [n.strip() for n in farmer_names.split(",") if n.strip()]
        count = len(farmer_list)

    weight_list = []
    amount_list = []
    ratio_list = []

    if split_by == "weight":
        if not weights:
            click.echo("\n❌ 按重量拆分时必须提供 --weights 参数", err=True)
            return
        weight_list = [safe_float(x) for x in weights.split(",")]
        count = len(weight_list)
        sum_w = sum(weight_list)
        if abs(sum_w - waybill.net_weight) > 0.01:
            click.echo(f"\n⚠️  拆分重量总和({sum_w:.3f}吨)与原净重({waybill.net_weight:.3f}吨)不一致")
            if not click.confirm("是否继续？"):
                click.echo("已取消")
                return

    elif split_by == "amount":
        if not amounts:
            click.echo("\n❌ 按金额拆分时必须提供 --amounts 参数", err=True)
            return
        amount_list = [safe_float(x) for x in amounts.split(",")]
        count = len(amount_list)
        sum_a = sum(amount_list)
        if abs(sum_a - waybill.freight) > 0.01:
            click.echo(f"\n⚠️  拆分运费总和({format_money(sum_a)})与原运费({format_money(waybill.freight)})不一致")
            if not click.confirm("是否继续？"):
                click.echo("已取消")
                return

    elif split_by == "ratio":
        if ratios:
            ratio_list = [safe_float(x) for x in ratios.split(",")]
            count = len(ratio_list)
        else:
            if count <= 1:
                click.echo("\n❌ 拆分数必须大于1", err=True)
                return
            equal_ratio = round(100.0 / count, 2)
            ratio_list = [equal_ratio] * count
            remainder = round(100 - equal_ratio * count, 2)
            if remainder != 0:
                ratio_list[0] += remainder

        sum_r = sum(ratio_list)
        if abs(sum_r - 100) > 0.01:
            click.echo(f"\n⚠️  比例总和({sum_r}%)不等于100%，已自动调整")
            ratio_list = [r / sum_r * 100 for r in ratio_list]

    elif split_by == "manual":
        click.echo(f"\n请手动输入 {count} 份拆分信息:")
        for i in range(count):
            click.echo(f"\n--- 第 {i+1} 份 ---")
            w = click.prompt(f"  净重(吨)", type=float, default=round(waybill.net_weight / count, 3))
            f = click.prompt(f"  运费(元)", type=float, default=round(waybill.freight / count, 2))
            b = click.prompt(f"  竹款(元)", type=float, default=round(waybill.bamboo_value / count, 2))
            weight_list.append(w)
            amount_list.append(f)
            ratio_list.append(0)
            if not farmer_list or len(farmer_list) <= i:
                fn = click.prompt(f"  分账人姓名(可选)", default="", show_default=False)
                if fn:
                    farmer_list.append(fn)

    splits = []
    for i in range(count):
        if split_by == "weight" and weight_list:
            w = weight_list[i]
            ratio = (w / waybill.net_weight) if waybill.net_weight > 0 else 0
            f = round(waybill.freight * ratio, 2)
            b = round(waybill.bamboo_value * ratio, 2)
        elif split_by == "amount" and amount_list:
            f = amount_list[i]
            ratio = (f / waybill.freight) if waybill.freight > 0 else 0
            w = round(waybill.net_weight * ratio, 3)
            b = round(waybill.bamboo_value * ratio, 2)
        elif split_by == "ratio" and ratio_list:
            ratio = ratio_list[i] / 100.0
            w = round(waybill.net_weight * ratio, 3)
            f = round(waybill.freight * ratio, 2)
            b = round(waybill.bamboo_value * ratio, 2)
        else:
            w = weight_list[i] if i < len(weight_list) else 0
            f = amount_list[i] if i < len(amount_list) else 0
            ratio = (w / waybill.net_weight) if waybill.net_weight > 0 else 0
            b = round(waybill.bamboo_value * ratio, 2)

        farmer = farmer_list[i] if i < len(farmer_list) else (waybill.farmer_name or "")

        splits.append({
            "index": i + 1,
            "weight": w,
            "freight": f,
            "bamboo": b,
            "farmer": farmer,
            "ratio": ratio * 100
        })

    diff_w = round(waybill.net_weight - sum(s["weight"] for s in splits), 3)
    diff_f = round(waybill.freight - sum(s["freight"] for s in splits), 2)
    diff_b = round(waybill.bamboo_value - sum(s["bamboo"] for s in splits), 2)
    if diff_w != 0 and splits:
        splits[-1]["weight"] = round(splits[-1]["weight"] + diff_w, 3)
    if diff_f != 0 and splits:
        splits[-1]["freight"] = round(splits[-1]["freight"] + diff_f, 2)
    if diff_b != 0 and splits:
        splits[-1]["bamboo"] = round(splits[-1]["bamboo"] + diff_b, 2)

    preview_data = []
    for s in splits:
        preview_data.append([
            s["index"],
            format_weight(s["weight"]),
            format_money(s["freight"]),
            format_money(s["bamboo"]),
            f"{s['ratio']:.1f}%",
            s["farmer"] or "-"
        ])
    preview_data.append([
        "合计",
        format_weight(sum(s["weight"] for s in splits)),
        format_money(sum(s["freight"] for s in splits)),
        format_money(sum(s["bamboo"] for s in splits)),
        "100.0%",
        ""
    ])
    print_table(preview_data, ["序号", "净重", "运费", "竹款", "比例", "分账人"], "拆分预览")

    if list_only:
        click.echo("\n⚠️  预览模式，未执行拆分")
        return

    if not yes:
        if not click.confirm(f"\n确认将运单拆分为 {len(splits)} 份吗？"):
            click.echo("已取消")
            return

    new_waybills: List[Waybill] = []
    for i, s in enumerate(splits):
        nb = copy.deepcopy(waybill)
        nb.id = None
        from ..models import _generate_id
        nb.id = _generate_id()
        nb.waybill_no = f"{waybill.waybill_no}-{i+1:02d}"
        nb.net_weight = s["weight"]
        nb.gross_weight = round(waybill.gross_weight * (s["weight"] / waybill.net_weight if waybill.net_weight > 0 else 0), 3) if waybill.net_weight > 0 else 0
        nb.tare_weight = round(waybill.tare_weight * (s["weight"] / waybill.net_weight if waybill.net_weight > 0 else 0), 3) if waybill.net_weight > 0 else 0
        nb.freight = s["freight"]
        nb.bamboo_value = s["bamboo"]
        nb.farmer_amount = s["bamboo"]
        nb.is_split = True
        nb.split_parent_id = waybill.id
        nb.split_remark = f"从运单{waybill.waybill_no}拆分，第{i+1}/{len(splits)}份"
        if s["farmer"]:
            nb.farmer_name = s["farmer"]
        nb.is_paid = False
        nb.paid_amount = 0.0
        nb.paid_date = ""
        nb.exceptions = []
        nb.add_note(f"系统拆分运单 {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        new_waybills.append(nb)

    remaining = []
    for w in all_waybills:
        if w.id == waybill.id:
            w.is_split = True
            w.split_remark = f"已拆分为{len(splits)}份: " + ", ".join(nb.waybill_no for nb in new_waybills)
            w.add_note(f"已拆分为{len(splits)}份子运单 {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        remaining.append(w)

    remaining.extend(new_waybills)
    store.save_waybills(remaining)

    click.echo(f"\n✅ 拆分完成!")
    click.echo(f"  原运单标记为已拆分: {waybill.waybill_no}")
    click.echo(f"  新增子运单: {len(new_waybills)} 条")
    for nb in new_waybills:
        click.echo(f"    - {nb.waybill_no}: {format_weight(nb.net_weight)}, "
                   f"运费{format_money(nb.freight)}, 竹款{format_money(nb.bamboo_value)} "
                   f"({nb.farmer_name or '无分账人'})")

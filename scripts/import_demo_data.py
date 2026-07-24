import re
import sys
import os
import xmlrpc.client
from datetime import date, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT / "addons" / "zfmd_pm" / "tools"))
from excel_reader import read_workbook_tables

DATA_DIR = ROOT / "软件开发基础资料"
ODOO_URL = "http://127.0.0.1:8069"
DB = os.environ.get("ODOO_DB", "zfmd-PM")
USERNAME = os.environ.get("ODOO_USERNAME", "admin")
PASSWORD = os.environ.get("ODOO_PASSWORD")
if not PASSWORD:
    raise SystemExit("请通过 ODOO_PASSWORD 环境变量提供登录密码。")


def norm_text(value):
    value = "" if value is None else str(value)
    value = (
        value.replace("\n", "").replace("\r", "").replace(" ", "").replace("\u3000", "")
    )
    return value.strip()


def clean_value(value):
    if value is None:
        return False
    value = str(value).strip()
    if value in {"", "/", "无", "未流转"}:
        return False
    return value


def parse_float(value):
    value = clean_value(value)
    if value is False:
        return 0.0
    value = str(value).replace(",", "").replace("税率", "").replace("%", "").strip()
    try:
        return float(value)
    except ValueError:
        match = re.search(r"-?\d+(?:\.\d+)?", value)
        return float(match.group(0)) if match else 0.0


def parse_date(value):
    value = clean_value(value)
    if value is False:
        return False
    text = str(value)
    match = re.search(r"(\d{4})[.\-/年](\d{1,2})[.\-/月](\d{1,2})", text)
    if match:
        year, month, day = map(int, match.groups())
        return date(year, month, day).isoformat()
    return False


def extract_contract_key(value):
    value = clean_value(value)
    if value is False:
        return False
    match = re.search(r"(\d{5}(?:-\d+)?)", str(value))
    return match.group(1) if match else str(value)


def extract_records(path, required_headers):
    tables = read_workbook_tables(path)
    records = []
    norm_required = {norm_text(h) for h in required_headers}
    for sheet_name, rows in tables.items():
        header = None
        for i, row in enumerate(rows):
            normalized = [norm_text(cell) for cell in row]
            if norm_required.issubset(set(normalized)):
                header = row
                for data_row in rows[i + 1 :]:
                    if not any(norm_text(cell) for cell in data_row):
                        continue
                    row_dict = {}
                    for idx, head in enumerate(header):
                        key = norm_text(head)
                        if not key:
                            continue
                        row_dict[key] = data_row[idx] if idx < len(data_row) else ""
                    row_dict["_sheet_name"] = sheet_name
                    records.append(row_dict)
                break
    return records


class OdooClient:
    def __init__(self):
        common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
        self.uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        self.models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
        self.partner_cache = {}
        self.site_cache = {}
        self.contract_cache = {}

    def execute(self, model, method, *args, **kwargs):
        return self.models.execute_kw(
            DB, self.uid, PASSWORD, model, method, list(args), kwargs or {}
        )

    def search(self, model, domain, limit=None):
        if (
            domain
            and len(domain) == 1
            and isinstance(domain[0], list)
            and domain[0]
            and isinstance(domain[0][0], list)
        ):
            domain = domain[0]
        kwargs = {}
        if limit:
            kwargs["limit"] = limit
        return self.execute(model, "search", domain, **kwargs)

    def read(self, model, ids, fields):
        return self.execute(model, "read", ids, fields)

    def create(self, model, vals):
        return self.execute(model, "create", vals)

    def write(self, model, ids, vals):
        return self.execute(model, "write", ids, vals)

    def ensure_partner(self, name, province=False, group_name=False):
        name = clean_value(name)
        if not name:
            return False
        if name in self.partner_cache:
            return self.partner_cache[name]
        ids = self.search("res.partner", [[["name", "=", name]]], limit=1)
        vals = {
            "name": name,
            "zfmd_customer_manual": True,
            "province_name": province or False,
            "group_name": group_name or False,
            "company_type": "company",
        }
        if ids:
            self.write("res.partner", ids, vals)
            partner_id = ids[0]
        else:
            partner_id = self.create("res.partner", vals)
        self.partner_cache[name] = partner_id
        return partner_id

    def ensure_site(
        self,
        name,
        partner_id=False,
        province=False,
        group_name=False,
        site_category=False,
    ):
        name = clean_value(name)
        if not name:
            return False
        key = (name, partner_id or 0)
        if key in self.site_cache:
            return self.site_cache[key]
        domain = [[["name", "=", name]]]
        if partner_id:
            domain[0].append(["partner_id", "=", partner_id])
        ids = self.search("zfmd.site", domain, limit=1)
        vals = {
            "name": name,
            "partner_id": partner_id or False,
            "province_name": province or False,
            "group_name": group_name or False,
            "site_category": site_category or False,
        }
        if ids:
            self.write("zfmd.site", ids, vals)
            site_id = ids[0]
        else:
            site_id = self.create("zfmd.site", vals)
        self.site_cache[key] = site_id
        return site_id

    def find_contract_id(
        self, contract_no, contract_name=False, partner_id=False, site_id=False
    ):
        contract_no = clean_value(contract_no)
        key = extract_contract_key(contract_no or contract_name)
        if key and key in self.contract_cache:
            return self.contract_cache[key]
        ids = []
        if key:
            ids = self.search("zfmd.contract", [[["contract_key", "=", key]]], limit=1)
        if not ids and contract_no:
            ids = self.search("zfmd.contract", [[["name", "=", contract_no]]], limit=1)
        if ids:
            contract_id = ids[0]
        else:
            contract_id = self.create(
                "zfmd.contract",
                {
                    "name": contract_no or contract_name or key or "TEMP-CONTRACT",
                    "contract_key": key or False,
                    "contract_name": contract_name or False,
                    "partner_id": partner_id or False,
                    "site_id": site_id or False,
                    "state": "draft",
                },
            )
        if key:
            self.contract_cache[key] = contract_id
        return contract_id

    def upsert_contract(self, vals):
        key = vals.get("contract_key")
        ids = []
        if key:
            ids = self.search("zfmd.contract", [[["contract_key", "=", key]]], limit=1)
        if not ids:
            ids = self.search("zfmd.contract", [[["name", "=", vals["name"]]]], limit=1)
        if ids:
            self.write("zfmd.contract", ids, vals)
            contract_id = ids[0]
        else:
            contract_id = self.create("zfmd.contract", vals)
        if key:
            self.contract_cache[key] = contract_id
        return contract_id


def import_contracts(client):
    path = next(DATA_DIR.glob("06 *.xlsx"))
    rows = extract_records(path, ["合同编号", "客户名称"])
    count = 0
    for row in rows:
        contract_no = clean_value(row.get("合同编号"))
        if not contract_no:
            continue
        partner_id = client.ensure_partner(
            row.get("客户名称"), row.get("省（区）"), row.get("集团")
        )
        site_id = client.ensure_site(
            row.get("场站名称"),
            partner_id,
            row.get("省（区）"),
            row.get("集团"),
            row.get("场站类别"),
        )
        vals = {
            "name": contract_no,
            "contract_key": extract_contract_key(contract_no),
            "contract_name": clean_value(row.get("合同名称")),
            "partner_id": partner_id or False,
            "site_id": site_id or False,
            "province_name": clean_value(row.get("省（区）")),
            "group_name": clean_value(row.get("集团")),
            "product_line": clean_value(row.get("产品线")),
            "project_content": clean_value(row.get("合同项目内容")),
            "sale_manager": clean_value(row.get("签订合同销售经理")),
            "sale_contact": clean_value(row.get("销售联系人")),
            "contract_sign_date": parse_date(row.get("合同签订日期")),
            "archive_date": parse_date(row.get("合同存档日期")),
            "service_start_date": parse_date(row.get("服务收费起始时间")),
            "service_end_date": parse_date(row.get("服务收费终止时间")),
            "initial_fee": parse_float(row.get("初装费")),
            "service_fee": parse_float(row.get("预测服务费")),
            "amount_total": parse_float(row.get("合同总额")),
            "amount_untaxed": parse_float(row.get("不含税合同金额")),
            "delivery_department": clean_value(row.get("交付部门")),
            "project_manager": clean_value(row.get("项目经理")),
            "start_application_no": clean_value(row.get("开工申请编号")),
            "after_sale_no": clean_value(row.get("售后服务编号")),
            "change_no": clean_value(row.get("合同变更号")),
            "note": clean_value(row.get("备注")),
            "special_contract": "特殊" in str(row.get("备注") or ""),
            "state": "running",
        }
        client.upsert_contract(vals)
        count += 1
    return count


def import_invoices(client):
    path = next(DATA_DIR.glob("05 *.xlsx"))
    rows = extract_records(path, ["合同号", "开票日期", "发票金额（元）"])
    count = 0
    for row in rows:
        contract_id = client.find_contract_id(row.get("合同号"))
        invoice_date = parse_date(row.get("开票日期"))
        amount = parse_float(row.get("发票金额（元）"))
        if not contract_id or not invoice_date:
            continue
        state_map = {"未回款": "open", "已回款": "paid", "作废发票": "cancel"}
        sheet_name = row.get("_sheet_name", "")
        state = "draft"
        for key, value in state_map.items():
            if key in sheet_name:
                state = value
                break
        domain = [
            [
                ["contract_id", "=", contract_id],
                ["invoice_date", "=", invoice_date],
                ["invoice_amount", "=", amount],
            ]
        ]
        ids = client.search("zfmd.invoice.record", domain, limit=1)
        vals = {
            "contract_id": contract_id,
            "invoice_date": invoice_date,
            "invoice_request_date": parse_date(row.get("申请开票日期")),
            "invoice_partner_name": clean_value(row.get("开票单位")),
            "province_name": clean_value(row.get("省（区）")),
            "group_name": clean_value(row.get("集团")),
            "site_name": clean_value(row.get("场站名称")),
            "product_line": clean_value(row.get("产品线")),
            "project_content": clean_value(row.get("合同项目内容")),
            "sale_manager": clean_value(row.get("签订合同销售经理"))
            or clean_value(row.get("销售经理")),
            "sale_contact": clean_value(row.get("销售联系人")),
            "contract_amount": parse_float(row.get("合同金额（元）"))
            or parse_float(row.get("合同额（元）")),
            "invoice_amount": amount,
            "tax_rate": clean_value(row.get("税率")),
            "amount_untaxed": parse_float(row.get("不含税金额（元）")),
            "promised_payment_date": parse_date(row.get("承诺回款日期")),
            "promised_payment_amount": parse_float(row.get("承诺回款金额")),
            "actual_payment_date": parse_date(row.get("实际回款日期")),
            "actual_payment_amount": parse_float(row.get("实际回款金额")),
            "express_no": clean_value(row.get("发票快递单号")),
            "cancel_date": parse_date(row.get("作废时间")),
            "cancel_reason": clean_value(row.get("作废原因")),
            "state": state,
            "note": clean_value(row.get("备注")),
        }
        if ids:
            client.write("zfmd.invoice.record", ids, vals)
        else:
            client.create("zfmd.invoice.record", vals)
        count += 1
    return count


def import_payments(client):
    path = next(DATA_DIR.glob("04 *.xlsx"))
    rows = extract_records(path, ["回款日期", "合同号"])
    count = 0
    for row in rows:
        contract_id = client.find_contract_id(row.get("合同号"))
        payment_date = (
            parse_date(row.get("回款日期"))
            or parse_date(row.get("日期"))
            or parse_date(row.get("日期"))
        )
        amount_total = parse_float(row.get("汇票回款(元)")) + parse_float(
            row.get("现金回款(元)")
        )
        if amount_total == 0:
            amount_total = parse_float(row.get("金额"))
        if not contract_id or not payment_date:
            continue
        domain = [
            [
                ["contract_id", "=", contract_id],
                ["payment_date", "=", payment_date],
                ["amount_total", "=", amount_total],
            ]
        ]
        ids = client.search("zfmd.payment.record", domain, limit=1)
        vals = {
            "contract_id": contract_id,
            "payment_date": payment_date,
            "payer_name": clean_value(row.get("付款单位")),
            "province_name": clean_value(row.get("省（区）")),
            "group_name": clean_value(row.get("集团")),
            "site_name": clean_value(row.get("场站名称"))
            or clean_value(row.get("风电场名称")),
            "product_line": clean_value(row.get("产品线")),
            "project_content": clean_value(row.get("合同项目内容")),
            "bill_amount": parse_float(row.get("汇票回款(元)")),
            "cash_amount": parse_float(row.get("现金回款(元)"))
            or parse_float(row.get("金额")),
            "payment_ratio_text": clean_value(row.get("回款比例")),
            "payment_item_name": clean_value(row.get("款项名称")),
            "sale_manager": clean_value(row.get("签订合同销售经理"))
            or clean_value(row.get("销售经理"))
            or clean_value(row.get("业务员")),
            "sale_contact": clean_value(row.get("销售联系人")),
            "note": clean_value(row.get("备注")),
        }
        if ids:
            client.write("zfmd.payment.record", ids, vals)
        else:
            client.create("zfmd.payment.record", vals)
        count += 1
    return count


def import_project_starts(client):
    path = next(DATA_DIR.glob("07 *.xlsx"))
    rows = extract_records(path, ["开工申请编号", "产品线"])
    count = 0
    for row in rows:
        name = clean_value(row.get("开工申请编号"))
        if not name:
            continue
        contract_id = client.find_contract_id(row.get("对应合同编号"))
        ids = client.search("zfmd.project.start", [[["name", "=", name]]], limit=1)
        vals = {
            "name": name,
            "contract_id": contract_id or False,
            "change_request_no": clean_value(row.get("开工变更申请表编号")),
            "cancel_date": parse_date(row.get("开工申请取消时间")),
            "has_cost": (
                "yes"
                if clean_value(row.get("是否发生成本费用")) == "是"
                else "no" if clean_value(row.get("是否发生成本费用")) == "否" else False
            ),
            "cost_handling": clean_value(row.get("成本费用处理")),
            "transfer_date": parse_date(row.get("开工申请流转时间")),
            "province_name": clean_value(row.get("省（区）")),
            "group_name": clean_value(row.get("集团")),
            "site_name": clean_value(row.get("场站名称")),
            "site_category": clean_value(row.get("场站类型")),
            "product_line": clean_value(row.get("产品线")),
            "project_content": clean_value(row.get("开工项目内容")),
            "sale_manager": clean_value(row.get("销售经理")),
            "handover_meeting_date": parse_date(row.get("项目交底会时间")),
            "estimated_contract_amount": parse_float(row.get("预计合同金额")),
            "estimated_cost_amount": parse_float(row.get("预计成本")),
            "actual_contract_amount": parse_float(row.get("实际合同金额")),
            "delivery_department": clean_value(row.get("交付部门")),
            "project_manager": clean_value(row.get("项目经理")),
            "arrival_date": parse_date(row.get("到货时间")),
            "acceptance_date": parse_date(row.get("验收时间")),
            "note": clean_value(row.get("备注")),
            "state": "cancel" if parse_date(row.get("开工申请取消时间")) else "running",
        }
        if ids:
            client.write("zfmd.project.start", ids, vals)
        else:
            client.create("zfmd.project.start", vals)
        count += 1
    return count


def import_services(client):
    path = next(DATA_DIR.glob("08 *.xlsx"))
    rows = extract_records(path, ["销售经理", "场站名称", "服务合同到期时间"])
    count = 0
    for row in rows:
        site_name = clean_value(row.get("场站名称"))
        if not site_name:
            continue
        partner_id = client.ensure_partner(
            clean_value(row.get("集团")) or "未指定客户",
            row.get("省（区）"),
            row.get("集团"),
        )
        site_id = client.ensure_site(
            site_name,
            partner_id,
            row.get("省（区）"),
            row.get("集团"),
            row.get("场站类别"),
        )
        domain = [
            [
                ["site_id", "=", site_id],
                [
                    "formal_forecast_date",
                    "=",
                    parse_date(row.get("正式预报时间")) or False,
                ],
                [
                    "service_end_date",
                    "=",
                    parse_date(row.get("服务合同到期时间")) or False,
                ],
            ]
        ]
        ids = client.search("zfmd.service.record", domain, limit=1)
        vals = {
            "name": "New",
            "site_id": site_id,
            "sale_manager": clean_value(row.get("销售经理"))
            or clean_value(row.get("签订合同销售经理")),
            "province_name": clean_value(row.get("省（区）")),
            "group_name": clean_value(row.get("集团")),
            "product_line": "数值天气预报服务",
            "service_content": "数值天气预报服务",
            "chargeable": False,
            "start_forecast_date": parse_date(row.get("开始预报时间")),
            "formal_forecast_date": parse_date(row.get("正式预报时间")),
            "service_end_date": parse_date(row.get("服务合同到期时间")),
            "expected_contract_amount": parse_float(
                row.get("预计签订服务合同金额（万元）")
            ),
            "expected_contract_sign_date": parse_date(row.get("预计签订服务合同时间")),
            "renewal_note": clean_value(row.get("续签服务合同情况说明")),
        }
        if ids:
            vals.pop("name", None)
            client.write("zfmd.service.record", ids, vals)
        else:
            client.create("zfmd.service.record", vals)
        count += 1
    return count


def import_receivables(client):
    path = next(DATA_DIR.glob("09 *.xlsx"))
    rows = extract_records(path, ["合同编号", "应收款项名称", "应收款金额"])
    count = 0
    for row in rows:
        contract_id = client.find_contract_id(row.get("合同编号"))
        receivable_item_name = clean_value(row.get("应收款项名称"))
        receivable_amount = parse_float(row.get("应收款金额"))
        receivable_date = parse_date(row.get("应收时间"))
        if not contract_id or not receivable_item_name:
            continue
        domain = [
            [
                ["contract_id", "=", contract_id],
                ["receivable_item_name", "=", receivable_item_name],
                ["receivable_amount", "=", receivable_amount],
                ["receivable_date", "=", receivable_date or False],
            ]
        ]
        ids = client.search("zfmd.receivable.plan", domain, limit=1)
        sheet_name = row.get("_sheet_name", "")
        note = clean_value(row.get("备注"))
        if "已扣款" in sheet_name and note:
            note = f"{note}; 来源: 已扣款"
        vals = {
            "name": "New",
            "contract_id": contract_id,
            "sale_manager": clean_value(row.get("签订合同销售经理")),
            "sale_contact": clean_value(row.get("销售联系人")),
            "province_name": clean_value(row.get("省（区）")),
            "group_name": clean_value(row.get("集团")),
            "site_name": clean_value(row.get("场站名称")),
            "product_line": clean_value(row.get("产品线")),
            "project_content": clean_value(row.get("合同项目内容")),
            "contract_amount": parse_float(row.get("合同金额（万元）")),
            "receivable_item_name": receivable_item_name,
            "receivable_amount": receivable_amount,
            "receivable_date": receivable_date,
            "pending_progress_date": clean_value(row.get("待工程实施进展确定回款时间")),
            "promised_entry_date": parse_date(row.get("销售经理承诺进入回款期时间")),
            "promised_payment_date": parse_date(row.get("销售经理承诺回款时间")),
            "promised_payment_amount": parse_float(row.get("销售经理承诺回款金额")),
            "actual_payment_date": parse_date(row.get("实际回款时间")),
            "actual_payment_amount": parse_float(row.get("实际回款金额")),
            "overdue_months": int(parse_float(row.get("超期时间（月）"))),
            "actual_invoice_date": parse_date(row.get("实际开票时间")),
            "actual_arrival_date": parse_date(row.get("实际到货时间")),
            "actual_acceptance_date": parse_date(row.get("实际验收时间")),
            "payment_term": clean_value(row.get("合同约定付款条件")),
            "note": note,
        }
        if ids:
            vals.pop("name", None)
            client.write("zfmd.receivable.plan", ids, vals)
        else:
            client.create("zfmd.receivable.plan", vals)
        count += 1
    return count


def main():
    client = OdooClient()
    summary = {
        "contracts": import_contracts(client),
        "project_starts": import_project_starts(client),
        "services": import_services(client),
        "invoices": import_invoices(client),
        "payments": import_payments(client),
        "receivables": import_receivables(client),
    }
    print("IMPORT SUMMARY")
    for key, value in summary.items():
        print(f"{key}: {value}")
    print("NOTE: 10 号统计表建议作为结果校验来源，暂不直接导入为主数据。")


if __name__ == "__main__":
    main()

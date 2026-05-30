import re
import sys
import xmlrpc.client
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT / "addons" / "zfmd_pm" / "tools"))
from excel_reader import read_workbook_tables

ODOO_URL = "http://127.0.0.1:8069"
DB = "zfmd_pm"
USERNAME = "admin"
PASSWORD = "admin"


def find_data_dir():
    for path in ROOT.iterdir():
        if path.is_dir() and any(
            child.suffix.lower() == ".xlsx" for child in path.iterdir()
        ):
            return path
    raise FileNotFoundError("Could not locate data directory with xlsx files.")


DATA_DIR = find_data_dir()


def norm_text(value):
    value = "" if value is None else str(value)
    return (
        value.replace("\n", "")
        .replace("\r", "")
        .replace(" ", "")
        .replace("\u3000", "")
        .strip()
    )


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
    required = {norm_text(header) for header in required_headers}
    for sheet_name, rows in tables.items():
        header = None
        for i, row in enumerate(rows):
            normalized = [norm_text(cell) for cell in row]
            if required.issubset(set(normalized)):
                header = [norm_text(cell) for cell in row]
                for data_row in rows[i + 1 :]:
                    if not any(norm_text(cell) for cell in data_row):
                        continue
                    row_dict = {}
                    for idx, key in enumerate(header):
                        if not key:
                            continue
                        row_dict[key] = data_row[idx] if idx < len(data_row) else ""
                    row_dict["_sheet_name"] = sheet_name
                    records.append(row_dict)
                break
    return records


def first_value(row, *keys):
    for key in keys:
        value = row.get(key)
        if clean_value(value) is not False:
            return value
    return False


class OdooClient:
    def __init__(self):
        common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
        self.uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        self.models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
        self.contract_cache = {}
        self.partner_cache = {}
        self.site_cache = {}

    def execute(self, model, method, *args, **kwargs):
        return self.models.execute_kw(
            DB, self.uid, PASSWORD, model, method, list(args), kwargs or {}
        )

    def search(self, model, domain, limit=None):
        kwargs = {}
        if limit:
            kwargs["limit"] = limit
        return self.execute(model, "search", domain, **kwargs)

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
        ids = self.search("res.partner", [["name", "=", name]], limit=1)
        vals = {
            "name": name,
            "zfmd_customer_manual": True,
            "province_name": clean_value(province) or False,
            "group_name": clean_value(group_name) or False,
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
        other_name=False,
    ):
        name = clean_value(name)
        if not name:
            return False
        key = (name, partner_id or 0)
        if key in self.site_cache:
            return self.site_cache[key]
        domain = [["name", "=", name]]
        if partner_id:
            domain.append(["partner_id", "=", partner_id])
        ids = self.search("zfmd.site", domain, limit=1)
        vals = {
            "name": name,
            "partner_id": partner_id or False,
            "province_name": clean_value(province) or False,
            "group_name": clean_value(group_name) or False,
            "site_category": clean_value(site_category) or False,
            "other_name": clean_value(other_name) or False,
        }
        if ids:
            self.write("zfmd.site", ids, vals)
            site_id = ids[0]
        else:
            site_id = self.create("zfmd.site", vals)
        self.site_cache[key] = site_id
        return site_id

    def find_contract_id(self, contract_no):
        contract_no = clean_value(contract_no)
        key = extract_contract_key(contract_no)
        if key and key in self.contract_cache:
            return self.contract_cache[key]
        ids = []
        if key:
            ids = self.search("zfmd.contract", [["contract_key", "=", key]], limit=1)
        if not ids and contract_no:
            ids = self.search("zfmd.contract", [["name", "=", contract_no]], limit=1)
        contract_id = ids[0] if ids else False
        if key and contract_id:
            self.contract_cache[key] = contract_id
        return contract_id

    def ensure_contract(self, contract_no):
        contract_no = clean_value(contract_no)
        if not contract_no:
            return False
        contract_id = self.find_contract_id(contract_no)
        vals = {
            "name": contract_no,
            "contract_key": extract_contract_key(contract_no),
            "state": "running",
        }
        if contract_id:
            self.write("zfmd.contract", [contract_id], vals)
            return contract_id
        return self.upsert_contract(vals)

    def upsert_contract(self, vals):
        ids = []
        if vals.get("contract_key"):
            ids = self.search(
                "zfmd.contract", [["contract_key", "=", vals["contract_key"]]], limit=1
            )
        if not ids and vals.get("name"):
            ids = self.search("zfmd.contract", [["name", "=", vals["name"]]], limit=1)
        if ids:
            self.write("zfmd.contract", ids, vals)
            contract_id = ids[0]
        else:
            contract_id = self.create("zfmd.contract", vals)
        if vals.get("contract_key"):
            self.contract_cache[vals["contract_key"]] = contract_id
        return contract_id


def get_file(prefix):
    matches = sorted(DATA_DIR.glob(f"{prefix} *.xlsx"))
    if not matches:
        raise FileNotFoundError(f"Missing xlsx file for prefix {prefix}")
    return matches[0]


def import_contracts(client):
    rows = extract_records(get_file("06"), ["合同编号", "客户名称"])
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
            row.get("其他名称"),
        )
        vals = {
            "name": contract_no,
            "contract_key": extract_contract_key(contract_no),
            "contract_name": clean_value(row.get("合同名称")) or False,
            "partner_id": partner_id or False,
            "site_id": site_id or False,
            "province_name": clean_value(row.get("省（区）")) or False,
            "group_name": clean_value(row.get("集团")) or False,
            "product_line": clean_value(row.get("产品线")) or False,
            "project_content": clean_value(row.get("合同项目内容")) or False,
            "sale_manager": clean_value(
                first_value(row, "签订合同销售经理", "销售经理")
            )
            or False,
            "sale_contact": clean_value(row.get("销售联系人")) or False,
            "contract_sign_date": parse_date(row.get("合同签订日期")),
            "archive_date": parse_date(row.get("合同存档日期")),
            "service_start_date": parse_date(row.get("服务收费起始时间")),
            "service_end_date": parse_date(row.get("服务收费终止时间")),
            "initial_fee": parse_float(row.get("初装费")),
            "service_fee": parse_float(row.get("预测服务费")),
            "amount_total": parse_float(row.get("合同总额")),
            "amount_untaxed": parse_float(row.get("不含税合同金额")),
            "delivery_department": clean_value(row.get("交付部门")) or False,
            "project_manager": clean_value(row.get("项目经理")) or False,
            "start_application_no": clean_value(row.get("开工申请编号")) or False,
            "after_sale_no": clean_value(row.get("售后服务编号")) or False,
            "change_no": clean_value(row.get("合同变更号")) or False,
            "note": clean_value(row.get("备注")) or False,
            "state": "running",
        }
        client.upsert_contract(vals)
        count += 1
    return count


def match_existing(client, model, domain, vals):
    ids = client.search(model, domain, limit=1)
    if ids:
        client.write(model, ids, vals)
    else:
        client.create(model, vals)


def import_project_starts(client):
    rows = extract_records(get_file("07"), ["开工申请编号", "产品线"])
    count = 0
    for row in rows:
        name = clean_value(row.get("开工申请编号"))
        if not name:
            continue
        contract_id = client.ensure_contract(row.get("对应合同编号"))
        vals = {
            "name": name,
            "contract_id": contract_id or False,
            "change_request_no": clean_value(row.get("开工变更申请表编号")) or False,
            "cancel_date": parse_date(row.get("开工申请取消时间")),
            "has_cost": (
                "yes"
                if clean_value(row.get("是否发生成本费用")) == "是"
                else "no" if clean_value(row.get("是否发生成本费用")) == "否" else False
            ),
            "cost_handling": clean_value(row.get("成本费用处理")) or False,
            "transfer_date": parse_date(row.get("开工申请流转时间")),
            "province_name": clean_value(row.get("省（区）")) or False,
            "group_name": clean_value(row.get("集团")) or False,
            "site_name": clean_value(row.get("场站名称")) or False,
            "site_category": clean_value(row.get("场站类型")) or False,
            "product_line": clean_value(row.get("产品线")) or False,
            "project_content": clean_value(row.get("开工项目内容")) or False,
            "sale_manager": clean_value(row.get("销售经理")) or False,
            "handover_meeting_date": parse_date(row.get("项目交底会时间")),
            "estimated_contract_amount": parse_float(row.get("预计合同金额")),
            "estimated_cost_amount": parse_float(row.get("预计成本")),
            "actual_contract_amount": parse_float(row.get("实际合同金额")),
            "delivery_department": clean_value(row.get("交付部门")) or False,
            "project_manager": clean_value(row.get("项目经理")) or False,
            "arrival_date": parse_date(row.get("到货时间")),
            "acceptance_date": parse_date(row.get("验收时间")),
            "note": clean_value(row.get("备注")) or False,
            "state": "cancel" if parse_date(row.get("开工申请取消时间")) else "running",
        }
        ids = client.search("zfmd.project.start", [["name", "=", name]], limit=1)
        if ids:
            client.write("zfmd.project.start", ids, vals)
        else:
            client.create("zfmd.project.start", vals)
        count += 1
    return count


def import_services(client):
    rows = extract_records(get_file("08"), ["销售经理", "场站名称", "服务合同到期时间"])
    count = 0
    for row in rows:
        site_name = clean_value(row.get("场站名称"))
        if not site_name:
            continue
        site_id = client.ensure_site(
            site_name, False, row.get("省（区）"), row.get("集团"), row.get("场站类别")
        )
        vals = {
            "site_id": site_id or False,
            "sale_manager": clean_value(
                first_value(row, "销售经理", "签订合同销售经理")
            )
            or False,
            "province_name": clean_value(row.get("省（区）")) or False,
            "group_name": clean_value(row.get("集团")) or False,
            "product_line": clean_value(row.get("产品线")) or False,
            "service_content": clean_value(
                first_value(row, "服务项目内容", "合同项目内容")
            )
            or False,
            "chargeable": False,
            "start_forecast_date": parse_date(row.get("开始预报时间")),
            "formal_forecast_date": parse_date(row.get("正式预报时间")),
            "service_end_date": parse_date(row.get("服务合同到期时间")),
            "expected_contract_amount": parse_float(
                row.get("预计签订服务合同金额（万元）")
            ),
            "expected_contract_sign_date": parse_date(row.get("预计签订服务合同时间")),
            "renewal_note": clean_value(row.get("续签服务合同情况说明")) or False,
        }
        ids = client.search(
            "zfmd.service.record",
            [
                ["site_id", "=", site_id],
                ["formal_forecast_date", "=", vals["formal_forecast_date"] or False],
                ["service_end_date", "=", vals["service_end_date"] or False],
            ],
            limit=1,
        )
        if ids:
            client.write("zfmd.service.record", ids, vals)
        else:
            vals["name"] = "New"
            client.create("zfmd.service.record", vals)
        count += 1
    return count


def import_invoices(client):
    rows = extract_records(get_file("05"), ["合同号", "开票日期", "发票金额（元）"])
    count = 0
    for row in rows:
        contract_id = client.ensure_contract(row.get("合同号"))
        invoice_date = parse_date(row.get("开票日期"))
        amount = parse_float(row.get("发票金额（元）"))
        if not invoice_date:
            continue
        sheet_name = row.get("_sheet_name", "")
        state = "draft"
        if "未回款" in sheet_name:
            state = "open"
        elif "已回款" in sheet_name:
            state = "paid"
        elif "作废" in sheet_name:
            state = "cancel"
        vals = {
            "contract_id": contract_id or False,
            "invoice_date": invoice_date,
            "invoice_request_date": parse_date(row.get("申请开票日期")),
            "invoice_partner_name": clean_value(row.get("开票单位")) or False,
            "province_name": clean_value(row.get("省（区）")) or False,
            "group_name": clean_value(row.get("集团")) or False,
            "site_name": clean_value(row.get("场站名称")) or False,
            "product_line": clean_value(row.get("产品线")) or False,
            "project_content": clean_value(row.get("合同项目内容")) or False,
            "sale_manager": clean_value(
                first_value(row, "签订合同销售经理", "销售经理")
            )
            or False,
            "sale_contact": clean_value(row.get("销售联系人")) or False,
            "contract_amount": parse_float(
                first_value(row, "合同金额（元）", "合同额（元）")
            ),
            "invoice_amount": amount,
            "tax_rate": clean_value(row.get("税率")) or False,
            "amount_untaxed": parse_float(row.get("不含税金额（元）")),
            "promised_payment_date": parse_date(row.get("承诺回款日期")),
            "promised_payment_amount": parse_float(row.get("承诺回款金额")),
            "actual_payment_date": parse_date(row.get("实际回款日期")),
            "actual_payment_amount": parse_float(row.get("实际回款金额")),
            "express_no": clean_value(row.get("发票快递单号")) or False,
            "cancel_date": parse_date(row.get("作废时间")),
            "cancel_reason": clean_value(row.get("作废原因")) or False,
            "state": state,
            "note": clean_value(row.get("备注")) or False,
        }
        domain = [
            ["invoice_date", "=", invoice_date],
            ["invoice_amount", "=", amount],
            ["site_name", "=", vals["site_name"] or False],
            ["sale_manager", "=", vals["sale_manager"] or False],
        ]
        match_existing(client, "zfmd.invoice.record", domain, vals)
        count += 1
    return count


def import_payments(client):
    rows = extract_records(get_file("04"), ["回款日期", "付款单位", "合同号"])
    count = 0
    for row in rows:
        payment_date = parse_date(row.get("回款日期"))
        if not payment_date:
            continue
        contract_id = client.ensure_contract(row.get("合同号"))
        bill_amount = parse_float(row.get("汇票回款(元)"))
        cash_amount = parse_float(row.get("现金回款(元)"))
        amount_total = bill_amount + cash_amount
        vals = {
            "contract_id": contract_id or False,
            "payment_date": payment_date,
            "payer_name": clean_value(row.get("付款单位")) or False,
            "province_name": clean_value(row.get("省（区）")) or False,
            "group_name": clean_value(row.get("集团")) or False,
            "site_name": clean_value(row.get("场站名称")) or False,
            "product_line": clean_value(row.get("产品线")) or False,
            "project_content": clean_value(row.get("合同项目内容")) or False,
            "bill_amount": bill_amount,
            "cash_amount": cash_amount,
            "payment_ratio_text": clean_value(row.get("回款比例")) or False,
            "payment_item_name": clean_value(row.get("款项名称")) or False,
            "sale_manager": clean_value(
                first_value(row, "签订合同销售经理", "销售经理")
            )
            or False,
            "sale_contact": clean_value(row.get("销售联系人")) or False,
            "note": clean_value(row.get("备注")) or False,
        }
        domain = [
            ["payment_date", "=", payment_date],
            ["amount_total", "=", amount_total],
            ["site_name", "=", vals["site_name"] or False],
            ["payment_item_name", "=", vals["payment_item_name"] or False],
        ]
        match_existing(client, "zfmd.payment.record", domain, vals)
        count += 1
    return count


def import_receivables(client):
    rows = extract_records(get_file("09"), ["合同编号", "应收款项名称", "应收款金额"])
    count = 0
    for row in rows:
        receivable_item_name = clean_value(row.get("应收款项名称"))
        if not receivable_item_name:
            continue
        contract_id = client.ensure_contract(row.get("合同编号"))
        vals = {
            "contract_id": contract_id or False,
            "sale_manager": clean_value(
                first_value(row, "签订合同销售经理", "销售经理")
            )
            or False,
            "sale_contact": clean_value(row.get("销售联系人")) or False,
            "province_name": clean_value(row.get("省（区）")) or False,
            "group_name": clean_value(row.get("集团")) or False,
            "site_name": clean_value(row.get("场站名称")) or False,
            "product_line": clean_value(row.get("产品线")) or False,
            "project_content": clean_value(row.get("合同项目内容")) or False,
            "contract_amount": parse_float(row.get("合同金额（万元）")),
            "receivable_item_name": receivable_item_name,
            "receivable_amount": parse_float(row.get("应收款金额")),
            "receivable_date": parse_date(row.get("应收时间")),
            "pending_progress_date": clean_value(row.get("待工程实施进展确定回款时间"))
            or False,
            "promised_entry_date": parse_date(row.get("销售经理承诺进入回款期时间")),
            "promised_payment_date": parse_date(row.get("销售经理承诺回款时间")),
            "promised_payment_amount": parse_float(row.get("销售经理承诺回款金额")),
            "actual_payment_date": parse_date(row.get("实际回款时间")),
            "actual_payment_amount": parse_float(row.get("实际回款金额")),
            "overdue_months": int(parse_float(row.get("超期时间（月）"))),
            "actual_invoice_date": parse_date(row.get("实际开票时间")),
            "actual_arrival_date": parse_date(row.get("实际到货时间")),
            "actual_acceptance_date": parse_date(row.get("实际验收时间")),
            "payment_term": clean_value(row.get("合同约定付款条件")) or False,
            "note": clean_value(row.get("备注")) or False,
        }
        domain = [
            ["receivable_item_name", "=", receivable_item_name],
            ["receivable_amount", "=", vals["receivable_amount"]],
            ["site_name", "=", vals["site_name"] or False],
            ["sale_manager", "=", vals["sale_manager"] or False],
        ]
        match_existing(client, "zfmd.receivable.plan", domain, vals)
        count += 1
    return count


def summarize(client):
    models = [
        "zfmd.contract",
        "zfmd.project.start",
        "zfmd.service.record",
        "zfmd.invoice.record",
        "zfmd.payment.record",
        "zfmd.receivable.plan",
    ]
    counts = {model: client.execute(model, "search_count", []) for model in models}
    linked = {
        "project_start_with_contract": client.execute(
            "zfmd.project.start", "search_count", [["contract_id", "!=", False]]
        ),
        "service_with_contract": client.execute(
            "zfmd.service.record", "search_count", [["contract_id", "!=", False]]
        ),
        "invoice_with_contract": client.execute(
            "zfmd.invoice.record", "search_count", [["contract_id", "!=", False]]
        ),
        "payment_with_contract": client.execute(
            "zfmd.payment.record", "search_count", [["contract_id", "!=", False]]
        ),
        "receivable_with_contract": client.execute(
            "zfmd.receivable.plan", "search_count", [["contract_id", "!=", False]]
        ),
    }
    return counts, linked


def main():
    client = OdooClient()
    before_counts, before_linked = summarize(client)
    summary = {
        "contracts": import_contracts(client),
        "project_starts": import_project_starts(client),
        "services": import_services(client),
        "invoices": import_invoices(client),
        "payments": import_payments(client),
        "receivables": import_receivables(client),
    }
    after_counts, after_linked = summarize(client)
    print("REPAIR SUMMARY")
    print("before counts:", before_counts)
    print("before linked:", before_linked)
    print("imported rows:", summary)
    print("after counts:", after_counts)
    print("after linked:", after_linked)


if __name__ == "__main__":
    main()

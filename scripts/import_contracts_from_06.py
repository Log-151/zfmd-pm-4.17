import re
import zipfile
import xml.etree.ElementTree as ET
import xmlrpc.client
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ODOO_URL = "http://127.0.0.1:8069"
DB = "zfmd_pm"
USERNAME = "admin"
PASSWORD = "admin"

NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def find_data_dir():
    for path in ROOT.iterdir():
        if path.is_dir() and any(child.suffix.lower() == ".xlsx" for child in path.iterdir()):
            return path
    raise FileNotFoundError("Could not locate data directory with xlsx files.")


DATA_DIR = find_data_dir()


def get_file(prefix):
    matches = sorted(DATA_DIR.glob(f"{prefix} *.xlsx"))
    if not matches:
        raise FileNotFoundError(f"Missing xlsx file for prefix {prefix}")
    return matches[0]


def norm_text(value):
    value = "" if value is None else str(value)
    return value.replace("\n", "").replace("\r", "").replace(" ", "").replace("\u3000", "").strip()


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
    value = str(value).replace(",", "").strip()
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
    if not match:
        return False
    year, month, day = map(int, match.groups())
    return f"{year:04d}-{month:02d}-{day:02d}"


def extract_contract_key(value):
    value = clean_value(value)
    if value is False:
        return False
    match = re.search(r"(\d{5}(?:-\d+)?)", str(value))
    return match.group(1) if match else str(value)


def col_to_index(ref):
    letters = "".join(ch for ch in ref if ch.isalpha())
    result = 0
    for char in letters:
        result = result * 26 + ord(char.upper()) - 64
    return result - 1


def read_workbook_tables(path):
    with zipfile.ZipFile(path) as zf:
        shared = []
        if "xl/sharedStrings.xml" in zf.namelist():
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in root.findall("a:si", NS):
                shared.append("".join(t.text or "" for t in si.findall(".//a:t", NS)))

        workbook = ET.fromstring(zf.read("xl/workbook.xml"))
        rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        relmap = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}

        result = {}
        for sheet in workbook.find("a:sheets", NS):
            name = sheet.attrib["name"]
            rid = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
            target = "xl/" + relmap[rid].lstrip("/")
            ws = ET.fromstring(zf.read(target))
            rows = []
            for row in ws.findall(".//a:sheetData/a:row", NS):
                values = {}
                for cell in row.findall("a:c", NS):
                    idx = col_to_index(cell.attrib.get("r", "A1"))
                    cell_type = cell.attrib.get("t")
                    value_node = cell.find("a:v", NS)
                    value = "" if value_node is None else (value_node.text or "")
                    if cell_type == "s" and value != "":
                        try:
                            value = shared[int(value)]
                        except Exception:
                            pass
                    values[idx] = value
                if values:
                    max_idx = max(values)
                    rows.append([values.get(i, "") for i in range(max_idx + 1)])
            result[name] = rows
        return result


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


class OdooClient:
    def __init__(self):
        common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
        self.uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        self.models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
        self.partner_cache = {}
        self.site_cache = {}

    def execute(self, model, method, *args, **kwargs):
        return self.models.execute_kw(DB, self.uid, PASSWORD, model, method, list(args), kwargs or {})

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
            "is_zfmd_customer": True,
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

    def ensure_site(self, name, partner_id=False, province=False, group_name=False, site_category=False, other_name=False):
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

    def upsert_contract(self, vals):
        ids = []
        if vals.get("contract_key"):
            ids = self.search("zfmd.contract", [["contract_key", "=", vals["contract_key"]]], limit=1)
        if not ids:
            ids = self.search("zfmd.contract", [["name", "=", vals["name"]]], limit=1)
        if ids:
            self.write("zfmd.contract", ids, vals)
            return ids[0]
        return self.create("zfmd.contract", vals)


def import_contracts():
    client = OdooClient()
    rows = extract_records(get_file("06"), ["合同编号", "客户名称"])
    imported = 0
    for row in rows:
        contract_no = clean_value(row.get("合同编号"))
        if not contract_no:
            continue
        partner_id = client.ensure_partner(row.get("客户名称"), row.get("省（区）"), row.get("集团"))
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
            "sale_manager": clean_value(row.get("签订合同销售经理")) or False,
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
        imported += 1
    print(f"IMPORTED CONTRACT ROWS: {imported}")


if __name__ == "__main__":
    import_contracts()

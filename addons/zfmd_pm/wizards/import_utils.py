import io
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, timedelta

_EXCEL_EPOCH = date(1899, 12, 30)


NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def _normalize_text(value):
    text = "" if value is None else str(value)
    return (
        text.replace("\n", "")
        .replace("\r", "")
        .replace(" ", "")
        .replace("\u3000", "")
        .strip()
    )


class ZfmdImportUtilityMixin:
    def _norm_text(self, value):
        return _normalize_text(value)

    def _clean_value(self, value):
        if value is None:
            return False
        if isinstance(value, str):
            raw = value.strip()
            if raw in {"", "/"}:
                return False
            return raw
        text = _normalize_text(value)
        if text in {"", "/"}:
            return False
        return value

    def _parse_float(self, value):
        value = self._clean_value(value)
        if value is False:
            return 0.0

        text = (
            str(value)
            .replace(",", "")
            .replace("\uff0c", "")
            .replace("\u4e07\u5143", "")
            .replace("\u4e07", "")
            .replace("\u5143", "")
            .replace("\u7a0e\u7387", "")
            .replace("%", "")
            .strip()
        )
        try:
            return float(text)
        except ValueError:
            match = re.search(r"-?\d+(?:\.\d+)?", text)
            return float(match.group(0)) if match else 0.0

    def _parse_money(self, value, source_unit="元"):
        amount = self._parse_float(value)
        if source_unit == "万元":
            return amount * 10000.0
        return amount

    def _parse_date(self, value):
        value = self._clean_value(value)
        if value is False:
            return False
        text = str(value)
        match = re.search(r"(\d{4})[.\-/\u5e74](\d{1,2})[.\-/\u6708](\d{1,2})", text)
        if match:
            year, month, day = map(int, match.groups())
            return f"{year:04d}-{month:02d}-{day:02d}"
        # Excel stores dates as serial numbers; reasonable range covers 2000-2099
        try:
            serial = float(text)
            if 36526 <= serial <= 73050:
                d = _EXCEL_EPOCH + timedelta(days=int(serial))
                return d.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            pass
        return False

    def _extract_contract_key(self, value):
        value = self._clean_value(value)
        if value is False:
            return False
        match = re.search(r"(\d{5}(?:-\d+)?)", str(value))
        return match.group(1) if match else str(value)

    def _first_value(self, row, *keys):
        for key in keys:
            value = row.get(key)
            if self._clean_value(value) is not False:
                return value
        return False

    def _write_import_summary(
        self,
        *,
        total_count,
        imported_count=0,
        unmatched_count=0,
        skipped_count=0,
        issue_lines=None,
    ):
        issue_lines = issue_lines or []
        summary = [
            f"\u8bc6\u522b\u8bb0\u5f55\u6570\uff1a{total_count}",
            f"\u5bfc\u5165\u6210\u529f\u6570\uff1a{imported_count}",
            f"\u672a\u5339\u914d\u5408\u540c\u6570\uff1a{unmatched_count}",
            f"\u8df3\u8fc7/\u95ee\u9898\u8bb0\u5f55\u6570\uff1a{skipped_count}",
        ]
        if issue_lines:
            summary.extend(["", "\u95ee\u9898\u660e\u7ec6\uff1a", *issue_lines[:30]])
        return "\n".join(summary)


def zfmd_col_to_index(ref):
    letters = "".join(ch for ch in ref if ch.isalpha())
    result = 0
    for char in letters:
        result = result * 26 + ord(char.upper()) - 64
    return result - 1


def zfmd_read_workbook_tables(file_bytes):
    with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
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
            rid = sheet.attrib[
                "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
            ]
            target = "xl/" + relmap[rid].lstrip("/")
            ws = ET.fromstring(zf.read(target))
            rows = []
            for row in ws.findall(".//a:sheetData/a:row", NS):
                values = {}
                for cell in row.findall("a:c", NS):
                    idx = zfmd_col_to_index(cell.attrib.get("r", "A1"))
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


def zfmd_extract_records(file_bytes, required_headers):
    tables = zfmd_read_workbook_tables(file_bytes)
    records = []
    required = {_normalize_text(header) for header in required_headers}
    for sheet_name, rows in tables.items():
        for i, row in enumerate(rows):
            normalized = [_normalize_text(cell) for cell in row]
            if required.issubset(set(normalized)):
                header = normalized
                for data_row in rows[i + 1 :]:
                    if not any(_normalize_text(cell) for cell in data_row):
                        continue
                    row_dict = {}
                    for idx, key in enumerate(header):
                        if key:
                            row_dict[key] = data_row[idx] if idx < len(data_row) else ""
                    row_dict["_sheet_name"] = sheet_name
                    records.append(row_dict)
                break
    return records


# ---------------------------------------------------------------------------
# Field alias table for contract import
# Keys starting with "_" are virtual fields (resolved to partner/site IDs).
# ---------------------------------------------------------------------------
CONTRACT_FIELD_ALIASES = {
    "name": ["合同编号", "合同号", "销售合同编号"],
    "_customer_name": ["客户名称", "客户", "付款单位", "甲方", "委托方"],
    "contract_name": ["合同名称", "项目名称"],
    "customer_level_1": ["一级公司", "一级客户"],
    "customer_level_2": ["二级公司", "二级客户"],
    "customer_level_3": ["三级公司", "三级客户"],
    "_site_name": ["场站名称", "场站"],
    "site_other_name": ["其他名称"],
    "site_category": ["场站类别", "场站类型"],
    "capacity_text": ["场站容量", "容量"],
    "contract_project_no": ["项目编号"],
    "province_name": ["省（区）", "省区", "省份"],
    "group_name": ["集团"],
    "product_line": ["产品线"],
    "project_content": ["合同项目内容", "项目内容"],
    "sale_manager": ["签订合同销售经理", "销售经理", "业务经理"],
    "sale_contact": ["销售联系人"],
    "contract_sign_date": ["合同签订日期", "签订日期", "签约日期"],
    "archive_date": ["合同存档日期", "存档日期"],
    "archive_document_type": ["合同存档原件/复印件"],
    "archive_copy_count": ["合同存档份数", "存档份数"],
    "service_start_date": ["服务收费起始时间", "服务开始日期"],
    "service_end_date": ["服务收费终止时间", "服务结束日期"],
    "initial_fee": ["初装费"],
    "service_fee": ["预测服务费"],
    "amount_total": ["合同总额", "合同金额"],
    "amount_untaxed": ["不含税合同金额", "不含税金额"],
    "exclude_sales_revenue": ["不算销售收入"],
    "exclude_sales_performance": ["不算销售业绩"],
    "bond_status": ["保函开具情况"],
    "delivery_department": ["交付部门"],
    "project_manager": ["项目经理"],
    "handover_meeting_date": ["合同交底会时间"],
    "third_party_interface_fee": ["第三方接口费"],
    "start_application_no": ["开工申请编号"],
    "after_sale_no": ["售后服务编号"],
    "change_no": ["合同变更号", "变更号"],
    "note": ["备注"],
}

CONTRACT_FIELD_LABELS = {
    "name": "合同编号",
    "_customer_name": "客户名称",
    "contract_name": "合同名称",
    "customer_level_1": "一级公司",
    "customer_level_2": "二级公司",
    "customer_level_3": "三级公司",
    "_site_name": "场站名称",
    "site_other_name": "其他名称",
    "site_category": "场站类别",
    "capacity_text": "场站容量",
    "contract_project_no": "项目编号",
    "province_name": "省区",
    "group_name": "集团",
    "product_line": "产品线",
    "project_content": "项目内容",
    "sale_manager": "销售经理",
    "sale_contact": "销售联系人",
    "contract_sign_date": "合同签订日期",
    "archive_date": "存档日期",
    "archive_document_type": "存档类型",
    "archive_copy_count": "存档份数",
    "service_start_date": "服务开始日期",
    "service_end_date": "服务结束日期",
    "initial_fee": "初装费",
    "service_fee": "预测服务费",
    "amount_total": "合同总额",
    "amount_untaxed": "不含税金额",
    "exclude_sales_revenue": "不算销售收入",
    "exclude_sales_performance": "不算销售业绩",
    "bond_status": "保函情况",
    "delivery_department": "交付部门",
    "project_manager": "项目经理",
    "handover_meeting_date": "交底会时间",
    "third_party_interface_fee": "三方接口费",
    "start_application_no": "开工申请编号",
    "after_sale_no": "售后服务编号",
    "change_no": "变更号",
    "note": "备注",
}


def zfmd_match_headers(excel_headers, field_aliases):
    """
    Match each Excel header to a field name via the alias table.
    Returns list of (original_header, matched_field_name_or_None).
    """
    reverse = {}
    for field_name, aliases in field_aliases.items():
        for alias in aliases:
            norm = _normalize_text(alias)
            if norm and norm not in reverse:
                reverse[norm] = field_name
    return [(h, reverse.get(_normalize_text(h))) for h in excel_headers]


def zfmd_find_best_sheet_header(file_bytes, field_aliases):
    """
    Scan all sheets and find the row with the highest number of alias matches.
    Returns (tables, sheet_name, header_row_idx, raw_headers_list).
    """
    tables = zfmd_read_workbook_tables(file_bytes)
    reverse = {
        _normalize_text(a): fn
        for fn, aliases in field_aliases.items()
        for a in aliases
        if _normalize_text(a)
    }
    best_sheet, best_idx, best_headers, best_count = None, 0, [], -1
    for sheet_name, rows in tables.items():
        for i, row in enumerate(rows[:30]):
            count = sum(1 for c in row if _normalize_text(c) in reverse)
            if count > best_count:
                best_count = count
                best_sheet, best_idx, best_headers = sheet_name, i, list(row)
    return tables, best_sheet, best_idx, best_headers


def zfmd_extract_by_alias(file_bytes, field_aliases, confirmed_norm_mapping=None):
    """
    Extract rows from file using field aliases or an explicit confirmed mapping.

    confirmed_norm_mapping: optional {normalized_excel_header: field_name}.
      If None, auto-detect via field_aliases.

    Returns (header_pairs, data_rows):
      header_pairs — [(excel_header, matched_field_or_None)]
      data_rows    — list of dicts keyed by field_name (virtual keys like
                     '_customer_name' included)
    """
    tables, sheet_name, header_row_idx, raw_headers = zfmd_find_best_sheet_header(
        file_bytes, field_aliases
    )
    if sheet_name is None:
        return [], []

    if confirmed_norm_mapping is not None:
        pairs = [
            (h, confirmed_norm_mapping.get(_normalize_text(h)))
            for h in raw_headers
        ]
    else:
        pairs = zfmd_match_headers(raw_headers, field_aliases)

    col_to_field = {idx: fn for idx, (_, fn) in enumerate(pairs) if fn}
    rows = tables[sheet_name]

    data_rows = []
    for row in rows[header_row_idx + 1 :]:
        if not any(_normalize_text(c) for c in row):
            continue
        data_rows.append(
            {fn: (row[idx] if idx < len(row) else "") for idx, fn in col_to_field.items()}
        )

    return pairs, data_rows

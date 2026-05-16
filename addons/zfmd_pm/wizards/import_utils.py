import html
import io
import re
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, timedelta

from odoo.exceptions import UserError

from odoo import fields, models

_EXCEL_EPOCH = date(1899, 12, 30)


NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def _normalize_text(value):
    text = "" if value is None else str(value)
    return text.replace("\n", "").replace("\r", "").replace(" ", "").replace("\u3000", "").strip()


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
            try:
                return date(year, month, day).strftime("%Y-%m-%d")
            except ValueError:
                return False
        match = re.fullmatch(r"\s*(\d{4})[.\-/\u5e74](\d{1,2})\s*(?:\u6708)?\s*", text)
        if match:
            year, month = map(int, match.groups())
            try:
                return date(year, month, 1).strftime("%Y-%m-%d")
            except ValueError:
                return False
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

    def _format_unmatched_contract_issue(self, row_index, contract_no=None, imported=False):
        suffix = "已标记为未匹配合同" if imported else "导入后将标记为未匹配合同"
        if contract_no:
            return f"第 {row_index} 行：合同号 {contract_no} 未匹配到合同，{suffix}。"
        return f"第 {row_index} 行：未匹配到合同，{suffix}。"

    def _build_import_result_html(
        self,
        *,
        title,
        total_count,
        success_count=0,
        unmatched_count=0,
        issue_count=0,
        issue_lines=None,
        mode="import",
    ):
        issue_lines = issue_lines or []
        escaped_issues = [html.escape(line) for line in issue_lines[:50]]
        issue_items = "".join(
            f'<li style="margin: 0 0 8px 0; line-height: 1.5;">{line}</li>' for line in escaped_issues
        )
        if not issue_items:
            issue_items = '<li style="line-height: 1.5;">无问题记录。</li>'
        more_text = ""
        if len(issue_lines) > 50:
            more_text = (
                f'<p style="margin: 8px 0 0 0; color: #6b7280;">'
                f"共 {len(issue_lines)} 条问题记录，当前仅展示前 50 条。"
                f"</p>"
            )
        primary_label = "成功处理数" if mode == "import" else "待导入数"
        return f"""
            <div style="min-width: 720px; max-width: 900px; width: 100%; box-sizing: border-box;">
                <h3 style="margin: 0 0 16px 0; font-size: 18px; font-weight: 600; white-space: nowrap;">
                    {html.escape(title)}
                </h3>
                <div style="display: grid; grid-template-columns: repeat(3, minmax(160px, 1fr)); gap: 12px; margin-bottom: 20px;">
                    <div style="border: 1px solid #d8dee4; border-radius: 6px; padding: 12px;">
                        <div style="font-size: 12px; color: #6b7280; margin-bottom: 4px;">识别记录数</div>
                        <div style="font-size: 22px; font-weight: 600; line-height: 1.2;">{total_count}</div>
                    </div>
                    <div style="border: 1px solid #d8dee4; border-radius: 6px; padding: 12px;">
                        <div style="font-size: 12px; color: #6b7280; margin-bottom: 4px;">{primary_label}</div>
                        <div style="font-size: 22px; font-weight: 600; line-height: 1.2;">{success_count}</div>
                    </div>
                    <div style="border: 1px solid #d8dee4; border-radius: 6px; padding: 12px;">
                        <div style="font-size: 12px; color: #6b7280; margin-bottom: 4px;">未匹配合同数</div>
                        <div style="font-size: 22px; font-weight: 600; line-height: 1.2;">{unmatched_count}</div>
                    </div>
                    <div style="border: 1px solid #d8dee4; border-radius: 6px; padding: 12px;">
                        <div style="font-size: 12px; color: #6b7280; margin-bottom: 4px;">需核对记录数</div>
                        <div style="font-size: 22px; font-weight: 600; line-height: 1.2;">{issue_count}</div>
                    </div>
                    <div style="border: 1px solid #d8dee4; border-radius: 6px; padding: 12px; grid-column: span 2;">
                        <div style="font-size: 12px; color: #6b7280; margin-bottom: 4px;">结果</div>
                        <div style="font-size: 15px; font-weight: 600; line-height: 1.4;">{html.escape(title)}</div>
                    </div>
                </div>
                <h4 style="margin: 0 0 10px 0; font-size: 15px; font-weight: 600;">问题明细</h4>
                <div style="max-height: 340px; overflow: auto; border: 1px solid #d8dee4; border-radius: 6px; padding: 12px 16px;">
                    <ul style="margin: 0; padding-left: 20px;">{issue_items}</ul>
                </div>
                {more_text}
            </div>
        """

    def _get_mapping_lines(self):
        line_field = getattr(self, "_mapping_line_field", False)
        return self[line_field] if line_field else self.env["zfmd.import.mapping.line"]

    def _get_confirmed_mapping_from_lines(self):
        lines = self._get_mapping_lines()
        if not lines:
            return None
        required_fields = set(getattr(self, "_required_mapping_fields", set()) or set())
        mapped_fields = {line.field_key for line in lines if line.field_key}
        missing_required = required_fields - mapped_fields
        if missing_required:
            labels = getattr(self, "_import_field_labels", {}) or {}
            missing_text = "、".join(labels.get(field, field) for field in missing_required)
            raise UserError(f"字段映射缺少必填字段：{missing_text}。请先在映射表中补齐。")
        return {
            _normalize_text(line.excel_header): line.field_key
            for line in lines
            if _normalize_text(line.excel_header) and line.field_key
        }

    def _build_mapping_summary(self, pairs, field_labels, required_fields):
        matched = [(h, fn) for h, fn in pairs if fn]
        unmatched = [h for h, fn in pairs if not fn and _normalize_text(h)]
        missing_required = set(required_fields or []) - {fn for _, fn in matched if fn}
        lines = [
            f"识别到 {len([h for h, _fn in pairs if _normalize_text(h)])} 个表头，自动匹配 {len(matched)} 个字段。",
        ]
        if missing_required:
            missing_text = "、".join(field_labels.get(fn, fn) for fn in missing_required)
            lines.append(f"缺少必填字段：{missing_text}。")
        if unmatched:
            lines.append(f"有 {len(unmatched)} 个 Excel 列未匹配，可在下方表格中选择对应字段。")
        if not missing_required and not unmatched:
            lines.append("字段已全部自动匹配，无需人工调整。")
        return "\n".join(lines)

    def _prepare_mapping_step(self, file_bytes, field_aliases, field_labels, required_fields):
        pairs, _data_rows = zfmd_extract_by_alias(file_bytes, field_aliases)
        if not pairs:
            raise ValueError("未能识别到有效表头。")

        self._get_mapping_lines().unlink()
        line_field = getattr(self, "_mapping_line_field", False)
        inverse_field = getattr(self, "_mapping_line_inverse_name", False)
        if not line_field or not inverse_field:
            return pairs, False

        commands = []
        for index, (header, field_key) in enumerate(pairs, start=1):
            if not _normalize_text(header):
                continue
            commands.append(
                (
                    0,
                    0,
                    {
                        "sequence": index,
                        "excel_header": header,
                        "field_key": field_key or False,
                        "required": bool(field_key in (required_fields or set())),
                    },
                )
            )
        self.write({line_field: commands})
        unmatched = [h for h, fn in pairs if not fn and _normalize_text(h)]
        missing_required = set(required_fields or []) - {fn for _, fn in pairs if fn}
        return pairs, bool(unmatched or missing_required)


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
            rid = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
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

INVOICE_FIELD_ALIASES = {
    "合同号": ["合同号", "合同编号"],
    "开票日期": ["开票日期"],
    "申请开票日期": ["申请开票日期"],
    "开票单位": ["开票单位", "开票客户"],
    "省（区）": ["省（区）", "省区"],
    "集团": ["集团"],
    "场站名称": ["场站名称", "场站"],
    "产品线": ["产品线"],
    "合同项目内容": ["合同项目内容", "项目内容"],
    "签订合同销售经理": ["签订合同销售经理", "销售经理"],
    "销售联系人": ["销售联系人"],
    "合同金额（元）": ["合同金额（元）", "合同额（元）", "合同金额"],
    "发票金额（元）": ["发票金额（元）", "发票金额"],
    "税率": ["税率"],
    "不含税金额（元）": ["不含税金额（元）", "不含税金额"],
    "承诺回款日期": ["承诺回款日期"],
    "承诺回款金额": ["承诺回款金额"],
    "实际回款日期": ["实际回款日期"],
    "实际回款金额": ["实际回款金额"],
    "发票快递单号": ["发票快递单号"],
    "作废时间": ["作废时间"],
    "作废原因": ["作废原因"],
    "备注": ["备注"],
}

PAYMENT_FIELD_ALIASES = {
    "合同号": ["合同号", "合同编号"],
    "回款日期": ["回款日期", "日期"],
    "付款单位": ["付款单位"],
    "省（区）": ["省（区）", "省区"],
    "集团": ["集团"],
    "场站名称": ["场站名称", "风电场名称", "场站"],
    "产品线": ["产品线"],
    "合同项目内容": ["合同项目内容", "项目内容"],
    "合同金额": ["合同金额", "合同金额（元）", "合同金额(元)"],
    "汇票回款(元)": ["汇票回款(元)", "汇票回款（元）"],
    "现金回款(元)": ["现金回款(元)", "现金回款（元）", "金额"],
    "回款比例": ["回款比例"],
    "款项名称": ["款项名称"],
    "类型": ["类型"],
    "签订合同销售经理": ["签订合同销售经理", "销售经理", "业务员"],
    "销售联系人": ["销售联系人"],
    "备注": ["备注"],
}

PROJECT_START_FIELD_ALIASES = {
    "开工申请编号": ["开工申请编号"],
    "开工变更申请表编号": ["开工变更申请表编号"],
    "对应合同编号": ["对应合同编号", "合同编号", "合同号"],
    "开工申请取消时间": ["开工申请取消时间"],
    "是否发生成本费用": ["是否发生成本费用"],
    "成本费用处理": ["成本费用处理"],
    "开工申请流转时间": ["开工申请流转时间"],
    "省（区）": ["省（区）", "省区"],
    "集团": ["集团"],
    "场站名称": ["场站名称", "场站"],
    "场站类型": ["场站类型", "场站类别"],
    "产品线": ["产品线"],
    "开工项目内容": ["开工项目内容", "项目内容"],
    "销售经理": ["销售经理", "签订合同销售经理"],
    "项目交底会时间": ["项目交底会时间"],
    "预计合同金额": ["预计合同金额"],
    "预计成本": ["预计成本"],
    "实际合同金额": ["实际合同金额"],
    "交付部门": ["交付部门"],
    "项目经理": ["项目经理"],
    "到货时间": ["到货时间"],
    "验收时间": ["验收时间"],
    "备注": ["备注"],
}

RECEIVABLE_FIELD_ALIASES = {
    "合同编号": ["合同编号", "合同号"],
    "签订合同销售经理": ["签订合同销售经理", "销售经理"],
    "销售联系人": ["销售联系人"],
    "省（区）": ["省（区）", "省区"],
    "集团": ["集团"],
    "场站名称": ["场站名称", "场站"],
    "产品线": ["产品线"],
    "合同项目内容": ["合同项目内容", "项目内容"],
    "合同金额（元）": ["合同金额（元）", "合同金额"],
    "应收款项名称": ["应收款项名称"],
    "应收款金额": ["应收款金额"],
    "应收时间": ["应收时间"],
    "待工程实施进展确定回款时间": ["待工程实施进展确定回款时间"],
    "销售经理承诺进入回款期时间": ["销售经理承诺进入回款期时间"],
    "销售经理承诺回款时间": ["销售经理承诺回款时间"],
    "销售经理承诺回款金额": ["销售经理承诺回款金额"],
    "实际回款时间": ["实际回款时间"],
    "实际回款金额": ["实际回款金额"],
    "超期时间（月）": ["超期时间（月）"],
    "实际开票时间": ["实际开票时间"],
    "实际到货时间": ["实际到货时间"],
    "实际验收时间": ["实际验收时间"],
    "合同约定付款条件": ["合同约定付款条件"],
    "备注": ["备注"],
}

SERVICE_FIELD_ALIASES = {
    "签订合同销售经理": ["签订合同销售经理"],
    "销售经理": ["销售经理"],
    "省（区）": ["省（区）", "省区"],
    "集团": ["集团"],
    "场站名称": ["场站名称", "场站"],
    "场站类别": ["场站类别", "场站类型"],
    "开始预报时间": ["开始预报时间"],
    "正式预报时间": ["正式预报时间"],
    "服务合同到期时间": ["服务合同到期时间"],
    "超期时间（月）": ["超期时间（月）"],
    "是否超期（是/否）": ["是否超期（是/否）"],
    "预计签订服务合同金额（元）": ["预计签订服务合同金额（元）", "预计签订服务合同金额"],
    "预计签订服务合同时间": ["预计签订服务合同时间"],
    "停止预报时间": ["停止预报时间"],
    "中断时间（月）": ["中断时间（月）"],
    "续签服务合同情况说明": ["续签服务合同情况说明"],
    "记录日期": ["记录日期"],
    "续签前服务到期时间": ["续签前服务到期时间"],
    "续签后服务开始时间": ["续签后服务开始时间"],
    "中断期间服务费如何处理": ["中断期间服务费如何处理"],
    "备注": ["备注"],
}

INVOICE_FIELD_LABELS = {key: key for key in INVOICE_FIELD_ALIASES}
PAYMENT_FIELD_LABELS = {key: key for key in PAYMENT_FIELD_ALIASES}
PROJECT_START_FIELD_LABELS = {key: key for key in PROJECT_START_FIELD_ALIASES}
RECEIVABLE_FIELD_LABELS = {key: key for key in RECEIVABLE_FIELD_ALIASES}
SERVICE_FIELD_LABELS = {key: key for key in SERVICE_FIELD_ALIASES}


def _mapping_field_selection(_records=None):
    labels = {}
    for source in (
        CONTRACT_FIELD_LABELS,
        INVOICE_FIELD_LABELS,
        PAYMENT_FIELD_LABELS,
        PROJECT_START_FIELD_LABELS,
        RECEIVABLE_FIELD_LABELS,
        SERVICE_FIELD_LABELS,
    ):
        labels.update(source)
    return sorted(labels.items(), key=lambda item: item[1])


class ZfmdImportMappingLine(models.TransientModel):
    _name = "zfmd.import.mapping.line"
    _description = "导入字段映射行"
    _order = "sequence, id"

    sequence = fields.Integer(string="序号", default=10)
    contract_wizard_id = fields.Many2one("zfmd.contract.import.wizard", ondelete="cascade")
    invoice_wizard_id = fields.Many2one("zfmd.invoice.import.wizard", ondelete="cascade")
    payment_wizard_id = fields.Many2one("zfmd.payment.import.wizard", ondelete="cascade")
    project_start_wizard_id = fields.Many2one("zfmd.project.start.import.wizard", ondelete="cascade")
    receivable_wizard_id = fields.Many2one("zfmd.receivable.import.wizard", ondelete="cascade")
    service_record_wizard_id = fields.Many2one("zfmd.service.record.import.wizard", ondelete="cascade")
    excel_header = fields.Char(string="Excel 列名", required=True, readonly=True)
    field_key = fields.Selection(selection=_mapping_field_selection, string="系统字段")
    required = fields.Boolean(string="必填")

    def check_access_rights(self, operation, raise_exception=True):
        return True

    def check_access_rule(self, operation):
        return True

    def init(self):
        model = self.env["ir.model"].sudo().search([("model", "=", self._name)], limit=1)
        if not model:
            return
        access = (
            self.env["ir.model.access"]
            .sudo()
            .search(
                [("name", "=", "zfmd.import.mapping.line user")],
                limit=1,
            )
        )
        vals = {
            "name": "zfmd.import.mapping.line user",
            "model_id": model.id,
            "group_id": False,
            "perm_read": True,
            "perm_write": True,
            "perm_create": True,
            "perm_unlink": True,
        }
        if access:
            access.write(vals)
        else:
            self.env["ir.model.access"].sudo().create(vals)


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
    reverse = {_normalize_text(a): fn for fn, aliases in field_aliases.items() for a in aliases if _normalize_text(a)}
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
    tables, sheet_name, header_row_idx, raw_headers = zfmd_find_best_sheet_header(file_bytes, field_aliases)
    if sheet_name is None:
        return [], []

    if confirmed_norm_mapping is not None:
        pairs = [(h, confirmed_norm_mapping.get(_normalize_text(h))) for h in raw_headers]
    else:
        pairs = zfmd_match_headers(raw_headers, field_aliases)

    col_to_field = {idx: fn for idx, (_, fn) in enumerate(pairs) if fn}
    rows = tables[sheet_name]

    data_rows = []
    for row in rows[header_row_idx + 1 :]:
        if not any(_normalize_text(c) for c in row):
            continue
        data_rows.append({fn: (row[idx] if idx < len(row) else "") for idx, fn in col_to_field.items()})

    return pairs, data_rows

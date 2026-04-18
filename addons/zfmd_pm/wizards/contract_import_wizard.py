import base64
import io
import re
import zipfile
import xml.etree.ElementTree as ET

from odoo import _, fields, models
from odoo.exceptions import UserError


NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


class ZfmdContractImportWizard(models.TransientModel):
    _name = "zfmd.contract.import.wizard"
    _description = "合同导入向导"

    file_name = fields.Char(string="文件名")
    upload_file = fields.Binary(string="上传 Excel", required=True)
    preview_summary = fields.Text(string="预览结果", readonly=True)
    preview_line_count = fields.Integer(string="识别记录数", readonly=True)
    imported_count = fields.Integer(string="导入成功数", readonly=True)
    warning_count = fields.Integer(string="问题记录数", readonly=True)
    state = fields.Selection(
        [
            ("draft", "待处理"),
            ("previewed", "已预览"),
            ("done", "已导入"),
        ],
        default="draft",
        string="状态",
        readonly=True,
    )

    def _norm_text(self, value):
        value = "" if value is None else str(value)
        return value.replace("\n", "").replace("\r", "").replace(" ", "").replace("\u3000", "").strip()

    def _clean_value(self, value):
        if value is None:
            return False
        value = str(value).strip()
        if value in {"", "/", "无", "未流转"}:
            return False
        return value

    def _parse_float(self, value):
        value = self._clean_value(value)
        if value is False:
            return 0.0
        text = str(value).replace(",", "").strip()
        try:
            return float(text)
        except ValueError:
            match = re.search(r"-?\d+(?:\.\d+)?", text)
            return float(match.group(0)) if match else 0.0

    def _parse_date(self, value):
        value = self._clean_value(value)
        if value is False:
            return False
        text = str(value)
        match = re.search(r"(\d{4})[.\-/年](\d{1,2})[.\-/月](\d{1,2})", text)
        if not match:
            return False
        year, month, day = map(int, match.groups())
        return f"{year:04d}-{month:02d}-{day:02d}"

    def _extract_contract_key(self, value):
        value = self._clean_value(value)
        if value is False:
            return False
        match = re.search(r"(\d{5}(?:-\d+)?)", str(value))
        return match.group(1) if match else str(value)

    def _col_to_index(self, ref):
        letters = "".join(ch for ch in ref if ch.isalpha())
        result = 0
        for char in letters:
            result = result * 26 + ord(char.upper()) - 64
        return result - 1

    def _read_workbook_tables(self, file_bytes):
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
                        idx = self._col_to_index(cell.attrib.get("r", "A1"))
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

    def _extract_records(self, file_bytes, required_headers):
        tables = self._read_workbook_tables(file_bytes)
        records = []
        required = {self._norm_text(header) for header in required_headers}
        for sheet_name, rows in tables.items():
            for i, row in enumerate(rows):
                normalized = [self._norm_text(cell) for cell in row]
                if required.issubset(set(normalized)):
                    header = normalized
                    for data_row in rows[i + 1 :]:
                        if not any(self._norm_text(cell) for cell in data_row):
                            continue
                        row_dict = {}
                        for idx, key in enumerate(header):
                            if key:
                                row_dict[key] = data_row[idx] if idx < len(data_row) else ""
                        row_dict["_sheet_name"] = sheet_name
                        records.append(row_dict)
                    break
        return records

    def _ensure_partner(self, name, province=False, group_name=False):
        partner_name = self._clean_value(name)
        if not partner_name:
            return False
        partner = self.env["res.partner"].search([("name", "=", partner_name)], limit=1)
        vals = {
            "name": partner_name,
            "is_zfmd_customer": True,
            "province_name": self._clean_value(province) or False,
            "group_name": self._clean_value(group_name) or False,
            "company_type": "company",
        }
        if partner:
            partner.write(vals)
            return partner.id
        return self.env["res.partner"].create(vals).id

    def _ensure_site(self, name, partner_id=False, province=False, group_name=False, site_category=False, other_name=False):
        site_name = self._clean_value(name)
        if not site_name:
            return False
        domain = [("name", "=", site_name)]
        if partner_id:
            domain.append(("partner_id", "=", partner_id))
        site = self.env["zfmd.site"].search(domain, limit=1)
        vals = {
            "name": site_name,
            "partner_id": partner_id or False,
            "province_name": self._clean_value(province) or False,
            "group_name": self._clean_value(group_name) or False,
            "site_category": self._clean_value(site_category) or False,
            "other_name": self._clean_value(other_name) or False,
        }
        if site:
            site.write(vals)
            return site.id
        return self.env["zfmd.site"].create(vals).id

    def _upsert_contract(self, vals):
        contract = self.env["zfmd.contract"]
        existing = False
        if vals.get("contract_key"):
            existing = contract.search([("contract_key", "=", vals["contract_key"])], limit=1)
        if not existing and vals.get("name"):
            existing = contract.search([("name", "=", vals["name"])], limit=1)
        if existing:
            existing.write(vals)
            return existing
        return contract.create(vals)

    def _prepare_contract_vals(self, row):
        contract_no = self._clean_value(row.get("合同编号"))
        if not contract_no:
            return False
        partner_id = self._ensure_partner(row.get("客户名称"), row.get("省（区）"), row.get("集团"))
        site_id = self._ensure_site(
            row.get("场站名称"),
            partner_id,
            row.get("省（区）"),
            row.get("集团"),
            row.get("场站类别"),
            row.get("其他名称"),
        )
        return {
            "name": contract_no,
            "contract_key": self._extract_contract_key(contract_no),
            "contract_name": self._clean_value(row.get("合同名称")) or False,
            "partner_id": partner_id or False,
            "site_id": site_id or False,
            "province_name": self._clean_value(row.get("省（区）")) or False,
            "group_name": self._clean_value(row.get("集团")) or False,
            "product_line": self._clean_value(row.get("产品线")) or False,
            "project_content": self._clean_value(row.get("合同项目内容")) or False,
            "sale_manager": self._clean_value(row.get("签订合同销售经理")) or False,
            "sale_contact": self._clean_value(row.get("销售联系人")) or False,
            "contract_sign_date": self._parse_date(row.get("合同签订日期")),
            "archive_date": self._parse_date(row.get("合同存档日期")),
            "service_start_date": self._parse_date(row.get("服务收费起始时间")),
            "service_end_date": self._parse_date(row.get("服务收费终止时间")),
            "initial_fee": self._parse_float(row.get("初装费")),
            "service_fee": self._parse_float(row.get("预测服务费")),
            "amount_total": self._parse_float(row.get("合同总额")),
            "amount_untaxed": self._parse_float(row.get("不含税合同金额")),
            "delivery_department": self._clean_value(row.get("交付部门")) or False,
            "project_manager": self._clean_value(row.get("项目经理")) or False,
            "start_application_no": self._clean_value(row.get("开工申请编号")) or False,
            "after_sale_no": self._clean_value(row.get("售后服务编号")) or False,
            "change_no": self._clean_value(row.get("合同变更号")) or False,
            "note": self._clean_value(row.get("备注")) or False,
            "state": "running",
        }

    def action_preview(self):
        self.ensure_one()
        if not self.upload_file:
            raise UserError(_("请先上传 06 销售合同登记台账 Excel 文件。"))
        file_bytes = base64.b64decode(self.upload_file)
        rows = self._extract_records(file_bytes, ["合同编号", "客户名称"])
        if not rows:
            raise UserError(_("未识别到有效数据，请确认上传的是 06 销售合同登记台账。"))

        missing_contract = 0
        missing_customer = 0
        for row in rows:
            if not self._clean_value(row.get("合同编号")):
                missing_contract += 1
            if not self._clean_value(row.get("客户名称")):
                missing_customer += 1

        summary = [
            f"识别记录数：{len(rows)}",
            f"缺少合同编号：{missing_contract}",
            f"缺少客户名称：{missing_customer}",
            "正式导入时将按 合同编号 -> 合同核心号 进行更新或新增。",
        ]
        self.write(
            {
                "preview_line_count": len(rows),
                "warning_count": missing_contract + missing_customer,
                "preview_summary": "\n".join(summary),
                "state": "previewed",
            }
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "预览完成",
                "message": f"已识别 {len(rows)} 条合同记录。",
                "type": "success",
                "sticky": False,
            },
        }

    def action_import(self):
        self.ensure_one()
        if not self.upload_file:
            raise UserError(_("请先上传 06 销售合同登记台账 Excel 文件。"))

        file_bytes = base64.b64decode(self.upload_file)
        rows = self._extract_records(file_bytes, ["合同编号", "客户名称"])
        if not rows:
            raise UserError(_("未识别到有效数据，请确认上传的是 06 销售合同登记台账。"))

        imported_count = 0
        warning_lines = []
        for index, row in enumerate(rows, start=1):
            vals = self._prepare_contract_vals(row)
            if not vals:
                warning_lines.append(f"第 {index} 行：缺少合同编号，已跳过。")
                continue
            if not vals.get("partner_id"):
                warning_lines.append(f"第 {index} 行：缺少客户名称，已跳过。")
                continue
            self._upsert_contract(vals)
            imported_count += 1

        summary = [
            f"识别记录数：{len(rows)}",
            f"导入成功数：{imported_count}",
            f"问题记录数：{len(warning_lines)}",
        ]
        if warning_lines:
            summary.extend(["", "问题明细：", *warning_lines[:30]])

        self.write(
            {
                "imported_count": imported_count,
                "warning_count": len(warning_lines),
                "preview_summary": "\n".join(summary),
                "state": "done",
            }
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "导入完成",
                "message": f"成功导入 {imported_count} 条合同记录。",
                "type": "success" if not warning_lines else "warning",
                "sticky": bool(warning_lines),
            },
        }

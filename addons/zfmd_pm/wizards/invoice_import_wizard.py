import base64

from odoo import _, fields, models
from odoo.exceptions import UserError

from .import_utils import ZfmdImportUtilityMixin, zfmd_extract_records


H_CONTRACT_NO = "合同号"
H_INVOICE_DATE = "开票日期"
H_REQUEST_DATE = "申请开票日期"
H_PARTNER = "开票单位"
H_PARTNER_ALT = "开票客户"
H_PROVINCE = "省（区）"
H_GROUP = "集团"
H_SITE = "场站名称"
H_PRODUCT_LINE = "产品线"
H_PROJECT_CONTENT = "合同项目内容"
H_SALE_MANAGER = "签订合同销售经理"
H_SALE_MANAGER_ALT = "销售经理"
H_SALE_CONTACT = "销售联系人"
H_CONTRACT_AMOUNT = "合同金额（元）"
H_CONTRACT_AMOUNT_ALT = "合同额（元）"
H_INVOICE_AMOUNT = "发票金额（元）"
H_TAX_RATE = "税率"
H_UNTAXED_AMOUNT = "不含税金额（元）"
H_PROMISED_PAYMENT_DATE = "承诺回款日期"
H_PROMISED_PAYMENT_AMOUNT = "承诺回款金额"
H_ACTUAL_PAYMENT_DATE = "实际回款日期"
H_ACTUAL_PAYMENT_AMOUNT = "实际回款金额"
H_EXPRESS_NO = "发票快递单号"
H_CANCEL_DATE = "作废时间"
H_CANCEL_REASON = "作废原因"
H_NOTE = "备注"


class ZfmdInvoiceImportWizard(models.TransientModel, ZfmdImportUtilityMixin):
    _name = "zfmd.invoice.import.wizard"
    _description = "开票导入向导"

    file_name = fields.Char(string="文件名")
    upload_file = fields.Binary(string="上传 Excel", required=True)
    preview_summary = fields.Text(string="导入结果", readonly=True)
    preview_line_count = fields.Integer(string="识别记录数", readonly=True)
    imported_count = fields.Integer(string="导入成功数", readonly=True)
    unmatched_count = fields.Integer(string="未匹配合同数", readonly=True)
    warning_count = fields.Integer(string="跳过/问题记录数", readonly=True)
    state = fields.Selection(
        [("draft", "待处理"), ("previewed", "已预览"), ("done", "已导入")],
        default="draft",
        string="状态",
        readonly=True,
    )

    def _find_contract(self, contract_no):
        return self.env["zfmd.contract"].sudo().find_by_contract_no(self._clean_value(contract_no))

    def _header_value(self, row, *keys):
        return self._clean_value(self._first_value(row, *keys))

    def _determine_state(self, sheet_name):
        name = self._clean_value(sheet_name) or ""
        if "未回款" in name:
            return "open"
        if "已回款" in name:
            return "paid"
        if "作废" in name:
            return "cancel"
        return "draft"

    def _prepare_invoice_vals(self, row):
        invoice_date = self._parse_date(row.get(H_INVOICE_DATE))
        if not invoice_date:
            return False, "缺少开票日期"

        contract_no = self._header_value(row, H_CONTRACT_NO)
        contract = self._find_contract(contract_no)
        vals = {
            "contract_id": contract.id if contract else False,
            "source_contract_no": contract.name if contract else contract_no,
            "invoice_date": invoice_date,
            "invoice_request_date": self._parse_date(row.get(H_REQUEST_DATE)),
            "invoice_partner_name": self._header_value(row, H_PARTNER, H_PARTNER_ALT) or False,
            "province_name": self._header_value(row, H_PROVINCE) or False,
            "group_name": self._header_value(row, H_GROUP) or False,
            "site_name": self._header_value(row, H_SITE) or False,
            "product_line": self._header_value(row, H_PRODUCT_LINE) or False,
            "project_content": self._header_value(row, H_PROJECT_CONTENT) or False,
            "sale_manager": self._header_value(row, H_SALE_MANAGER, H_SALE_MANAGER_ALT) or False,
            "sale_contact": self._header_value(row, H_SALE_CONTACT) or False,
            "contract_amount": self._parse_money(self._first_value(row, H_CONTRACT_AMOUNT, H_CONTRACT_AMOUNT_ALT), "元"),
            "invoice_amount": self._parse_money(row.get(H_INVOICE_AMOUNT), "元"),
            "tax_rate": self._header_value(row, H_TAX_RATE) or False,
            "amount_untaxed": self._parse_money(row.get(H_UNTAXED_AMOUNT), "元"),
            "promised_payment_date": self._parse_date(row.get(H_PROMISED_PAYMENT_DATE)),
            "promised_payment_amount": self._parse_money(row.get(H_PROMISED_PAYMENT_AMOUNT), "元"),
            "actual_payment_date": self._parse_date(row.get(H_ACTUAL_PAYMENT_DATE)),
            "actual_payment_amount": self._parse_money(row.get(H_ACTUAL_PAYMENT_AMOUNT), "元"),
            "express_no": self._header_value(row, H_EXPRESS_NO) or False,
            "cancel_date": self._parse_date(row.get(H_CANCEL_DATE)),
            "cancel_reason": self._header_value(row, H_CANCEL_REASON) or False,
            "state": self._determine_state(row.get("_sheet_name")),
            "note": self._header_value(row, H_NOTE) or False,
        }
        return vals, False

    def _upsert_invoice(self, vals):
        invoice_model = self.env["zfmd.invoice.record"].sudo()
        domain = [
            ("invoice_date", "=", vals["invoice_date"]),
            ("invoice_amount", "=", vals["invoice_amount"]),
            ("site_name", "=", vals["site_name"] or False),
            ("sale_manager", "=", vals["sale_manager"] or False),
        ]
        record = invoice_model.search(domain, limit=1)
        if record:
            record.write(vals)
            return record
        return invoice_model.create(vals)

    def _read_rows(self):
        if not self.upload_file:
            raise UserError(_("请先上传 05 销售合同开发票登记台账 Excel 文件。"))
        file_bytes = base64.b64decode(self.upload_file)
        rows = zfmd_extract_records(file_bytes, [H_CONTRACT_NO, H_INVOICE_DATE, H_INVOICE_AMOUNT])
        if not rows:
            raise UserError(_("未识别到有效数据，请确认上传的是 05 销售合同开发票登记台账。"))
        return rows

    def action_preview(self):
        self.ensure_one()
        rows = self._read_rows()
        issue_lines = []
        unmatched_contract = 0

        for index, row in enumerate(rows, start=1):
            if not self._parse_date(row.get(H_INVOICE_DATE)):
                issue_lines.append(f"第 {index} 行：缺少开票日期")
                continue
            contract_no = self._header_value(row, H_CONTRACT_NO)
            if contract_no and not self._find_contract(contract_no):
                unmatched_contract += 1

        self.write(
            {
                "preview_line_count": len(rows),
                "imported_count": 0,
                "unmatched_count": unmatched_contract,
                "warning_count": len(issue_lines),
                "preview_summary": self._write_import_summary(
                    total_count=len(rows),
                    imported_count=0,
                    unmatched_count=unmatched_contract,
                    skipped_count=len(issue_lines),
                    issue_lines=issue_lines,
                ),
                "state": "previewed",
            }
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "预览完成",
                "message": f"已识别 {len(rows)} 条开票记录。",
                "type": "success",
                "sticky": False,
            },
        }

    def action_import(self):
        self.ensure_one()
        rows = self._read_rows()
        imported_count = 0
        unmatched_contract = 0
        issue_lines = []

        for index, row in enumerate(rows, start=1):
            vals, error_message = self._prepare_invoice_vals(row)
            if not vals:
                issue_lines.append(f"第 {index} 行：{error_message}，已跳过。")
                continue
            if not vals.get("contract_id") and vals.get("source_contract_no"):
                unmatched_contract += 1
            self._upsert_invoice(vals)
            imported_count += 1

        self.write(
            {
                "preview_line_count": len(rows),
                "imported_count": imported_count,
                "unmatched_count": unmatched_contract,
                "warning_count": len(issue_lines),
                "preview_summary": self._write_import_summary(
                    total_count=len(rows),
                    imported_count=imported_count,
                    unmatched_count=unmatched_contract,
                    skipped_count=len(issue_lines),
                    issue_lines=issue_lines,
                ),
                "state": "done",
            }
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "导入完成",
                "message": f"成功导入 {imported_count} 条开票记录。",
                "type": "success" if not issue_lines else "warning",
                "sticky": bool(issue_lines),
            },
        }

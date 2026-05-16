import base64

from odoo.exceptions import UserError

from odoo import _, fields, models

from .import_utils import (
    RECEIVABLE_FIELD_ALIASES,
    RECEIVABLE_FIELD_LABELS,
    ZfmdImportUtilityMixin,
    zfmd_extract_by_alias,
)

H_CONTRACT_NO = "\u5408\u540c\u7f16\u53f7"
H_SALE_MANAGER = "\u7b7e\u8ba2\u5408\u540c\u9500\u552e\u7ecf\u7406"
H_SALE_CONTACT = "\u9500\u552e\u8054\u7cfb\u4eba"
H_PROVINCE = "\u7701\uff08\u533a\uff09"
H_GROUP = "\u96c6\u56e2"
H_SITE = "\u573a\u7ad9\u540d\u79f0"
H_PRODUCT_LINE = "\u4ea7\u54c1\u7ebf"
H_PROJECT_CONTENT = "\u5408\u540c\u9879\u76ee\u5185\u5bb9"
H_CONTRACT_AMOUNT = "\u5408\u540c\u91d1\u989d\uff08\u5143\uff09"
H_ITEM_NAME = "\u5e94\u6536\u6b3e\u9879\u540d\u79f0"
H_RECEIVABLE_AMOUNT = "\u5e94\u6536\u6b3e\u91d1\u989d"
H_RECEIVABLE_DATE = "\u5e94\u6536\u65f6\u95f4"
H_PENDING_PROGRESS_DATE = "\u5f85\u5de5\u7a0b\u5b9e\u65bd\u8fdb\u5c55\u786e\u5b9a\u56de\u6b3e\u65f6\u95f4"
H_PROMISED_ENTRY_DATE = "\u9500\u552e\u7ecf\u7406\u627f\u8bfa\u8fdb\u5165\u56de\u6b3e\u671f\u65f6\u95f4"
H_PROMISED_PAYMENT_DATE = "\u9500\u552e\u7ecf\u7406\u627f\u8bfa\u56de\u6b3e\u65f6\u95f4"
H_PROMISED_PAYMENT_AMOUNT = "\u9500\u552e\u7ecf\u7406\u627f\u8bfa\u56de\u6b3e\u91d1\u989d"
H_ACTUAL_PAYMENT_DATE = "\u5b9e\u9645\u56de\u6b3e\u65f6\u95f4"
H_ACTUAL_PAYMENT_AMOUNT = "\u5b9e\u9645\u56de\u6b3e\u91d1\u989d"
H_OVERDUE_MONTHS = "\u8d85\u671f\u65f6\u95f4\uff08\u6708\uff09"
H_ACTUAL_INVOICE_DATE = "\u5b9e\u9645\u5f00\u7968\u65f6\u95f4"
H_ACTUAL_ARRIVAL_DATE = "\u5b9e\u9645\u5230\u8d27\u65f6\u95f4"
H_ACTUAL_ACCEPTANCE_DATE = "\u5b9e\u9645\u9a8c\u6536\u65f6\u95f4"
H_PAYMENT_TERM = "\u5408\u540c\u7ea6\u5b9a\u4ed8\u6b3e\u6761\u4ef6"
H_NOTE = "\u5907\u6ce8"

SUMMARY_KEYWORDS = {
    "",
    "\u5408\u8ba1",
    "\u603b\u8ba1",
    "\u6c47\u603b",
    "\u5c0f\u8ba1",
}


class ZfmdReceivableImportWizard(models.TransientModel, ZfmdImportUtilityMixin):
    _name = "zfmd.receivable.import.wizard"
    _description = "\u5e94\u6536\u5bfc\u5165\u5411\u5bfc"

    file_name = fields.Char(string="\u6587\u4ef6\u540d")
    upload_file = fields.Binary(string="\u4e0a\u4f20 Excel", required=True)
    preview_summary = fields.Text(string="\u5bfc\u5165\u7ed3\u679c", readonly=True)
    preview_line_count = fields.Integer(string="\u8bc6\u522b\u8bb0\u5f55\u6570", readonly=True)
    imported_count = fields.Integer(string="\u5bfc\u5165\u6210\u529f\u6570", readonly=True)
    unmatched_count = fields.Integer(string="\u672a\u5339\u914d\u5408\u540c\u6570", readonly=True)
    warning_count = fields.Integer(string="\u8df3\u8fc7/\u95ee\u9898\u8bb0\u5f55\u6570", readonly=True)
    mapping_summary = fields.Text(string="字段映射摘要", readonly=True)
    mapping_line_ids = fields.One2many("zfmd.import.mapping.line", "receivable_wizard_id", string="字段映射")
    state = fields.Selection(
        [
            ("draft", "\u5f85\u5904\u7406"),
            ("mapping", "确认字段映射"),
            ("previewed", "\u5df2\u9884\u89c8"),
            ("done", "\u5df2\u5bfc\u5165"),
        ],
        default="draft",
        string="\u72b6\u6001",
        readonly=True,
    )
    _mapping_line_field = "mapping_line_ids"
    _mapping_line_inverse_name = "receivable_wizard_id"
    _import_field_aliases = RECEIVABLE_FIELD_ALIASES
    _import_field_labels = RECEIVABLE_FIELD_LABELS
    _required_mapping_fields = {H_CONTRACT_NO, H_ITEM_NAME}

    def _find_contract(self, contract_no):
        return self.env["zfmd.contract"].sudo().find_by_contract_no(self._clean_value(contract_no))

    def _header_value(self, row, *keys):
        return self._clean_value(self._first_value(row, *keys))

    def _parse_date_and_text(self, value):
        clean = self._clean_value(value)
        if clean is False:
            return False, False
        parsed = self._parse_date(clean)
        return parsed, False if parsed else clean

    def _is_summary_or_blank_row(self, row):
        item_name = self._norm_text(self._header_value(row, H_ITEM_NAME))
        if item_name in SUMMARY_KEYWORDS:
            return True

        contract_no = self._header_value(row, H_CONTRACT_NO)
        receivable_amount = self._parse_float(row.get(H_RECEIVABLE_AMOUNT))
        receivable_date = self._parse_date(row.get(H_RECEIVABLE_DATE))
        promised_payment_amount = self._parse_float(row.get(H_PROMISED_PAYMENT_AMOUNT))
        actual_payment_amount = self._parse_float(row.get(H_ACTUAL_PAYMENT_AMOUNT))

        has_business_value = any(
            [
                contract_no,
                receivable_amount,
                receivable_date,
                promised_payment_amount,
                actual_payment_amount,
            ]
        )
        return not has_business_value

    def _prepare_receivable_vals(self, row):
        receivable_item_name = self._header_value(row, H_ITEM_NAME)
        if not receivable_item_name:
            return False, "\u7f3a\u5c11\u5e94\u6536\u6b3e\u9879\u540d\u79f0"

        contract_no = self._header_value(row, H_CONTRACT_NO)
        contract = self._find_contract(contract_no)

        receivable_date, receivable_date_text = self._parse_date_and_text(row.get(H_RECEIVABLE_DATE))
        promised_entry_date, promised_entry_date_text = self._parse_date_and_text(row.get(H_PROMISED_ENTRY_DATE))
        promised_payment_date, promised_payment_date_text = self._parse_date_and_text(row.get(H_PROMISED_PAYMENT_DATE))
        actual_payment_date, actual_payment_date_text = self._parse_date_and_text(row.get(H_ACTUAL_PAYMENT_DATE))
        actual_invoice_date, actual_invoice_date_text = self._parse_date_and_text(row.get(H_ACTUAL_INVOICE_DATE))
        actual_arrival_date, actual_arrival_date_text = self._parse_date_and_text(row.get(H_ACTUAL_ARRIVAL_DATE))
        actual_acceptance_date, actual_acceptance_date_text = self._parse_date_and_text(
            row.get(H_ACTUAL_ACCEPTANCE_DATE)
        )

        vals = {
            "display_order": row.get("_row_number") or 0,
            "contract_id": contract.id if contract else False,
            "source_contract_no": contract.name if contract else contract_no,
            "sale_manager": self._header_value(row, H_SALE_MANAGER) or False,
            "sale_contact": self._header_value(row, H_SALE_CONTACT) or False,
            "province_name": self._header_value(row, H_PROVINCE) or False,
            "group_name": self._header_value(row, H_GROUP) or False,
            "site_name": self._header_value(row, H_SITE) or False,
            "product_line": self._header_value(row, H_PRODUCT_LINE) or False,
            "project_content": self._header_value(row, H_PROJECT_CONTENT) or False,
            "contract_amount": self._parse_float(row.get(H_CONTRACT_AMOUNT)),
            "receivable_item_name": receivable_item_name,
            "receivable_amount": self._parse_float(row.get(H_RECEIVABLE_AMOUNT)),
            "receivable_date": receivable_date,
            "receivable_date_text": receivable_date_text,
            "pending_progress_date": self._header_value(row, H_PENDING_PROGRESS_DATE) or False,
            "promised_entry_date": promised_entry_date,
            "promised_entry_date_text": promised_entry_date_text,
            "promised_payment_date": promised_payment_date,
            "promised_payment_date_text": promised_payment_date_text,
            "promised_payment_amount": self._parse_float(row.get(H_PROMISED_PAYMENT_AMOUNT)),
            "actual_payment_date": actual_payment_date,
            "actual_payment_date_text": actual_payment_date_text,
            "actual_payment_amount": self._parse_float(row.get(H_ACTUAL_PAYMENT_AMOUNT)),
            "overdue_months": int(self._parse_float(row.get(H_OVERDUE_MONTHS)) or 0),
            "actual_invoice_date": actual_invoice_date,
            "actual_invoice_date_text": actual_invoice_date_text,
            "actual_arrival_date": actual_arrival_date,
            "actual_arrival_date_text": actual_arrival_date_text,
            "actual_acceptance_date": actual_acceptance_date,
            "actual_acceptance_date_text": actual_acceptance_date_text,
            "payment_term": self._header_value(row, H_PAYMENT_TERM) or False,
            "note": self._header_value(row, H_NOTE) or False,
        }
        return vals, False

    def _upsert_receivable(self, vals):
        receivable_model = self.env["zfmd.receivable.plan"].sudo()
        domain = [
            ("source_contract_no", "=", vals.get("source_contract_no") or False),
            ("receivable_item_name", "=", vals["receivable_item_name"]),
            ("receivable_amount", "=", vals["receivable_amount"]),
            ("receivable_date", "=", vals.get("receivable_date") or False),
            ("receivable_date_text", "=", vals.get("receivable_date_text") or False),
        ]
        record = receivable_model.search(domain, limit=1)
        if record:
            record.write(vals)
            return record
        return receivable_model.create(vals)

    def _read_rows(self):
        if not self.upload_file:
            raise UserError(
                _(
                    "\u8bf7\u5148\u4e0a\u4f20 09 \u6267\u884c\u4e2d\u5408\u540c\u5e94\u6536\u6b3e\u660e\u7ec6\u53f0\u8d26 Excel \u6587\u4ef6\u3002"
                )
            )
        file_bytes = base64.b64decode(self.upload_file)
        raw_rows = zfmd_extract_by_alias(
            file_bytes, self._import_field_aliases, self._get_confirmed_mapping_from_lines()
        )[1]
        if not raw_rows:
            raise UserError(
                _(
                    "\u672a\u8bc6\u522b\u5230\u6709\u6548\u6570\u636e\uff0c\u8bf7\u786e\u8ba4\u4e0a\u4f20\u7684\u662f 09 \u6267\u884c\u4e2d\u5408\u540c\u5e94\u6536\u6b3e\u660e\u7ec6\u53f0\u8d26\u3002"
                )
            )

        rows = []
        for row in raw_rows:
            if self._is_summary_or_blank_row(row):
                continue
            rows.append(row)

        if not rows:
            raise UserError(
                _(
                    "\u8bc6\u522b\u5230\u7684\u5185\u5bb9\u5747\u4e3a\u6c47\u603b\u884c\u6216\u7a7a\u767d\u8bf4\u660e\u884c\uff0c\u6ca1\u6709\u53ef\u5bfc\u5165\u7684\u5e94\u6536\u8bb0\u5f55\u3002"
                )
            )

        for index, row in enumerate(rows, start=1):
            row["_row_number"] = index
        return rows

    def _reload_wizard_action(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("导入应收台账"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_detect_mapping(self):
        self.ensure_one()
        if not self.upload_file:
            raise UserError(_("请先上传 Excel 文件。"))
        file_bytes = base64.b64decode(self.upload_file)
        try:
            pairs, review_required = self._prepare_mapping_step(
                file_bytes, self._import_field_aliases, self._import_field_labels, self._required_mapping_fields
            )
        except ValueError:
            raise UserError(_("未能识别到有效表头，请确认上传的是 09 执行中合同应收款明细台账。"))
        self.write(
            {
                "mapping_summary": self._build_mapping_summary(
                    pairs, self._import_field_labels, self._required_mapping_fields
                ),
                "state": "mapping" if review_required else "draft",
            }
        )
        if review_required:
            return self._reload_wizard_action()
        self.action_preview()
        return self._reload_wizard_action()

    def action_preview(self):
        self.ensure_one()
        rows = self._read_rows()
        issue_lines = []
        unmatched_contract = 0

        for index, row in enumerate(rows, start=1):
            if not self._header_value(row, H_ITEM_NAME):
                issue_lines.append(f"\u7b2c {index} \u884c\uff1a\u7f3a\u5c11\u5e94\u6536\u6b3e\u9879\u540d\u79f0")
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
        return self._reload_wizard_action()

    def action_import(self):
        self.ensure_one()
        rows = self._read_rows()

        issue_lines = []
        imported = 0
        unmatched_contract = 0

        for index, row in enumerate(rows, start=1):
            vals, error = self._prepare_receivable_vals(row)
            if error:
                issue_lines.append(f"\u7b2c {index} \u884c\uff1a{error}")
                continue
            if vals.get("source_contract_no") and not vals.get("contract_id"):
                unmatched_contract += 1
            self._upsert_receivable(vals)
            imported += 1

        self.write(
            {
                "preview_line_count": len(rows),
                "imported_count": imported,
                "unmatched_count": unmatched_contract,
                "warning_count": len(issue_lines),
                "preview_summary": self._write_import_summary(
                    total_count=len(rows),
                    imported_count=imported,
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
                "title": "\u5bfc\u5165\u5b8c\u6210",
                "message": f"\u6210\u529f\u5bfc\u5165 {imported} \u6761\u5e94\u6536\u8bb0\u5f55\u3002",
                "type": "success",
                "sticky": False,
            },
        }

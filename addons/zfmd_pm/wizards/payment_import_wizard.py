import base64

from odoo.exceptions import UserError

from odoo import _, fields, models

from .import_utils import PAYMENT_FIELD_ALIASES, PAYMENT_FIELD_LABELS, ZfmdImportUtilityMixin, zfmd_extract_by_alias

H_CONTRACT_NO = "合同号"
H_PAYMENT_DATE = "回款日期"
H_DATE = "日期"
H_DATE_OLD = "日期"
H_PAYER = "付款单位"
H_PROVINCE = "省（区）"
H_PROVINCE_ALT = "省区"
H_GROUP = "集团"
H_SITE = "场站名称"
H_SITE_OLD = "风电场名称"
H_PRODUCT_LINE = "产品线"
H_PROJECT_CONTENT = "合同项目内容"
H_CONTRACT_AMOUNT = "合同金额"
H_CONTRACT_AMOUNT_YUAN_1 = "合同金额（元）"
H_CONTRACT_AMOUNT_YUAN_2 = "合同金额(元)"
H_BILL_AMOUNT_1 = "汇票回款(元)"
H_BILL_AMOUNT_2 = "汇票回款（元）"
H_CASH_AMOUNT_1 = "现金回款(元)"
H_CASH_AMOUNT_2 = "现金回款（元）"
H_AMOUNT = "金额"
H_AMOUNT_OLD = "金额"
H_RATIO = "回款比例"
H_ITEM_NAME = "款项名称"
H_TYPE = "类型"
H_SALE_MANAGER = "签订合同销售经理"
H_SALE_MANAGER_ALT = "销售经理"
H_SALE_MANAGER_OLD = "业务员"
H_SALE_CONTACT = "销售联系人"
H_NOTE = "备注"
H_NOTE_OLD = "备注"


class ZfmdPaymentImportWizard(models.TransientModel, ZfmdImportUtilityMixin):
    _name = "zfmd.payment.import.wizard"
    _description = "回款导入向导"

    file_name = fields.Char(string="文件名")
    upload_file = fields.Binary(string="上传 Excel", required=True)
    preview_summary = fields.Text(string="导入结果", readonly=True)
    preview_line_count = fields.Integer(string="识别记录数", readonly=True)
    imported_count = fields.Integer(string="导入成功数", readonly=True)
    unmatched_count = fields.Integer(string="未匹配合同数", readonly=True)
    warning_count = fields.Integer(string="跳过/问题记录数", readonly=True)
    mapping_summary = fields.Text(string="字段映射摘要", readonly=True)
    mapping_line_ids = fields.One2many("zfmd.import.mapping.line", "payment_wizard_id", string="字段映射")
    result_summary_html = fields.Html(string="导入结果摘要", readonly=True, sanitize=False)
    state = fields.Selection(
        [("draft", "待处理"), ("mapping", "确认字段映射"), ("previewed", "已预览"), ("done", "已导入")],
        default="draft",
        string="状态",
        readonly=True,
    )
    _mapping_line_field = "mapping_line_ids"
    _mapping_line_inverse_name = "payment_wizard_id"
    _import_field_aliases = PAYMENT_FIELD_ALIASES
    _import_field_labels = PAYMENT_FIELD_LABELS
    _required_mapping_fields = {H_PAYER, H_CONTRACT_NO}

    def _find_contract(self, contract_no):
        return self.env["zfmd.contract"].sudo().find_by_contract_no(self._clean_value(contract_no))

    def _header_value(self, row, *keys):
        return self._clean_value(self._first_value(row, *keys))

    def _find_contract_for_row(self, row):
        contract_no = self._header_value(row, H_CONTRACT_NO)
        return self._find_contract(contract_no) if contract_no else False

    def _prepare_payment_vals(self, row):
        payment_date_raw = self._first_value(row, H_PAYMENT_DATE, H_DATE, H_DATE_OLD)
        payment_date = self._parse_date(payment_date_raw)
        if not payment_date:
            if self._clean_value(payment_date_raw) is not False:
                return False, f"回款日期格式不正确：{payment_date_raw}"
            return False, "缺少回款日期"

        source_contract_no = self._header_value(row, H_CONTRACT_NO)
        contract = self._find_contract_for_row(row)
        single_amount = self._parse_float(self._first_value(row, H_AMOUNT, H_AMOUNT_OLD))
        vals = {
            "contract_id": contract.id if contract else False,
            "source_contract_no": contract.name if contract else source_contract_no,
            "payment_date": payment_date,
            "payer_name": self._header_value(row, H_PAYER) or False,
            "province_name": self._header_value(row, H_PROVINCE, H_PROVINCE_ALT) or False,
            "group_name": self._header_value(row, H_GROUP) or False,
            "site_name": self._header_value(row, H_SITE, H_SITE_OLD) or False,
            "product_line": self._header_value(row, H_PRODUCT_LINE) or False,
            "project_content": self._header_value(row, H_PROJECT_CONTENT) or False,
            "contract_amount": self._parse_float(
                self._first_value(row, H_CONTRACT_AMOUNT, H_CONTRACT_AMOUNT_YUAN_1, H_CONTRACT_AMOUNT_YUAN_2)
            ),
            "bill_amount": self._parse_float(self._first_value(row, H_BILL_AMOUNT_1, H_BILL_AMOUNT_2)),
            "cash_amount": self._parse_float(self._first_value(row, H_CASH_AMOUNT_1, H_CASH_AMOUNT_2)) or single_amount,
            "payment_ratio_text": self._header_value(row, H_RATIO) or False,
            "payment_item_name": self._header_value(row, H_ITEM_NAME) or False,
            "payment_type": self._header_value(row, H_TYPE) or False,
            "sale_manager": self._header_value(row, H_SALE_MANAGER, H_SALE_MANAGER_ALT, H_SALE_MANAGER_OLD) or False,
            "sale_contact": self._header_value(row, H_SALE_CONTACT) or False,
            "note": self._header_value(row, H_NOTE, H_NOTE_OLD) or False,
        }
        return vals, False

    def _create_payment(self, vals):
        return self.env["zfmd.payment.record"].sudo().create(vals)

    def _read_rows(self):
        if not self.upload_file:
            raise UserError(_("请先上传 04 销售合同回款登记台账 Excel 文件。"))
        file_bytes = base64.b64decode(self.upload_file)
        rows = zfmd_extract_by_alias(file_bytes, self._import_field_aliases, self._get_confirmed_mapping_from_lines())[
            1
        ]
        if not rows:
            raise UserError(_("未识别到有效数据，请确认上传的是 04 销售合同回款登记台账。"))
        return rows

    def _reload_wizard_action(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("导入回款台账"),
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
            raise UserError(_("未能识别到有效表头，请确认上传的是 04 销售合同回款登记台账。"))
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
        skipped_count = 0

        for index, row in enumerate(rows, start=1):
            payment_date_raw = self._first_value(row, H_PAYMENT_DATE, H_DATE, H_DATE_OLD)
            if not self._parse_date(payment_date_raw):
                if self._clean_value(payment_date_raw) is not False:
                    issue_lines.append(f"第 {index} 行：回款日期格式不正确：{payment_date_raw}")
                else:
                    issue_lines.append(f"第 {index} 行：缺少回款日期")
                skipped_count += 1
                continue
            contract_no = self._header_value(row, H_CONTRACT_NO)
            if contract_no and not self._find_contract(contract_no):
                unmatched_contract += 1
                issue_lines.append(self._format_unmatched_contract_issue(index, contract_no))

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
                "result_summary_html": self._build_import_result_html(
                    title="预览完成，确认后可正式导入",
                    total_count=len(rows),
                    success_count=len(rows) - skipped_count,
                    unmatched_count=unmatched_contract,
                    issue_count=len(issue_lines),
                    issue_lines=issue_lines,
                    mode="preview",
                ),
                "state": "previewed",
            }
        )
        return self._reload_wizard_action()

    def action_import(self):
        self.ensure_one()
        rows = self._read_rows()
        imported_count = 0
        unmatched_contract = 0
        issue_lines = []

        for index, row in enumerate(rows, start=1):
            vals, error_message = self._prepare_payment_vals(row)
            if not vals:
                issue_lines.append(f"第 {index} 行：{error_message}，已跳过。")
                continue
            if not vals.get("contract_id") and vals.get("source_contract_no"):
                unmatched_contract += 1
                issue_lines.append(
                    self._format_unmatched_contract_issue(index, vals.get("source_contract_no"), imported=True)
                )
            self._create_payment(vals)
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
                "result_summary_html": self._build_import_result_html(
                    title="导入完成" if not issue_lines else "导入完成，存在需核对记录",
                    total_count=len(rows),
                    success_count=imported_count,
                    unmatched_count=unmatched_contract,
                    issue_count=len(issue_lines),
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
                "message": f"成功导入 {imported_count} 条回款记录。",
                "type": "success" if not issue_lines else "warning",
                "sticky": bool(issue_lines),
            },
        }

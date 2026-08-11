import base64
import json
import re

from odoo.exceptions import UserError

from odoo import _, fields, models

from .import_utils import (
    PROJECT_START_FIELD_ALIASES,
    PROJECT_START_FIELD_LABELS,
    ZfmdImportUtilityMixin,
    zfmd_extract_by_alias,
)

H_START_NO = "开工申请编号"
H_CHANGE_NO = "开工变更申请表编号"
H_CONTRACT_NO = "对应合同编号"
H_CANCEL_DATE = "开工申请取消时间"
H_HAS_COST = "是否发生成本费用"
H_COST_HANDLING = "成本费用处理"
H_TRANSFER_DATE = "开工申请流转时间"
H_PROVINCE = "省（区）"
H_GROUP = "集团"
H_SITE = "场站名称"
H_SITE_CATEGORY = "场站类型"
H_PRODUCT_LINE = "产品线"
H_PROJECT_CONTENT = "开工项目内容"
H_SALE_MANAGER = "销售经理"
H_HANDOVER_DATE = "项目交底会时间"
H_EST_CONTRACT_AMOUNT = "预计合同金额"
H_EST_COST_AMOUNT = "预计成本"
H_ACTUAL_CONTRACT_AMOUNT = "实际合同金额"
H_NOTE = "备注"
H_DELIVERY_DEPT = "交付部门"
H_PROJECT_MANAGER = "项目经理"
H_ARRIVAL_DATE = "到货时间"
H_ACCEPTANCE_DATE = "验收时间"


class ZfmdProjectStartImportWizard(models.TransientModel, ZfmdImportUtilityMixin):
    _name = "zfmd.project.start.import.wizard"
    _description = "开工申请导入向导"

    file_name = fields.Char(string="文件名")
    upload_file = fields.Binary(string="上传 Excel", required=True)
    preview_summary = fields.Text(string="导入结果", readonly=True)
    preview_line_count = fields.Integer(string="识别记录数", readonly=True)
    imported_count = fields.Integer(string="导入成功数", readonly=True)
    unmatched_count = fields.Integer(string="未匹配合同数", readonly=True)
    warning_count = fields.Integer(string="跳过/问题记录数", readonly=True)
    mapping_summary = fields.Text(string="字段映射摘要", readonly=True)
    mapping_line_ids = fields.One2many("zfmd.import.mapping.line", "project_start_wizard_id", string="字段映射")
    result_summary_html = fields.Html(string="导入结果摘要", readonly=True, sanitize=False)
    state = fields.Selection(
        [
            ("draft", "待处理"),
            ("mapping", "确认字段映射"),
            ("previewed", "已预览"),
            ("done", "已导入"),
        ],
        default="draft",
        string="状态",
        readonly=True,
    )
    _mapping_line_field = "mapping_line_ids"
    _mapping_line_inverse_name = "project_start_wizard_id"
    _import_field_aliases = PROJECT_START_FIELD_ALIASES
    _import_field_labels = PROJECT_START_FIELD_LABELS
    _required_mapping_fields = {H_START_NO}

    def _find_contracts(self, contract_no):
        raw = self._clean_value(contract_no)
        if not raw:
            return self.env["zfmd.contract"]
        candidates = []
        for item in re.split(r"[\n,，；;]+", str(raw)):
            text = item.strip()
            if text:
                candidates.append(text)
        contracts = self.env["zfmd.contract"]
        for candidate in candidates:
            contracts |= self.env["zfmd.contract"].sudo().find_by_contract_no(candidate)
        return contracts

    def _header_value(self, row, *keys):
        return self._clean_value(self._first_value(row, *keys))

    def _normalize_yes_no(self, value):
        text = self._clean_value(value)
        if not text:
            return False, False
        if text in {"是", "有", "Y", "y", "YES", "yes"}:
            return "yes", text
        if text in {"否", "无", "N", "n", "NO", "no"}:
            return "no", text
        return False, text

    def _parse_date_and_text(self, value):
        clean = self._clean_value(value)
        if clean is False:
            return False, False
        parsed = self._parse_date(clean)
        return parsed, False if parsed else str(clean)

    def _parse_amount_and_text(self, value):
        clean = self._clean_value(value)
        if clean is False:
            return 0.0, False
        return self._parse_float(clean), str(clean)

    def _prepare_project_start_vals(self, row):
        start_no = self._header_value(row, H_START_NO)
        if not start_no:
            return False, "缺少开工申请编号"

        source_contract_no = self._header_value(row, H_CONTRACT_NO)
        matched_contracts = self._find_contracts(source_contract_no)
        contract = matched_contracts[:1] if len(matched_contracts) == 1 else self.env["zfmd.contract"]

        cancel_date, cancel_date_text = self._parse_date_and_text(row.get(H_CANCEL_DATE))
        transfer_date, transfer_date_text = self._parse_date_and_text(row.get(H_TRANSFER_DATE))
        handover_meeting_date, handover_meeting_date_text = self._parse_date_and_text(row.get(H_HANDOVER_DATE))
        arrival_date, arrival_date_text = self._parse_date_and_text(row.get(H_ARRIVAL_DATE))
        acceptance_date, acceptance_date_text = self._parse_date_and_text(row.get(H_ACCEPTANCE_DATE))
        has_cost, has_cost_text = self._normalize_yes_no(row.get(H_HAS_COST))
        estimated_contract_amount, estimated_contract_amount_text = self._parse_amount_and_text(
            row.get(H_EST_CONTRACT_AMOUNT)
        )
        estimated_cost_amount, estimated_cost_amount_text = self._parse_amount_and_text(row.get(H_EST_COST_AMOUNT))
        actual_contract_amount, actual_contract_amount_text = self._parse_amount_and_text(
            row.get(H_ACTUAL_CONTRACT_AMOUNT)
        )

        vals = {
            "name": start_no,
            "contract_id": contract.id if contract else False,
            "source_contract_no": source_contract_no,
            "raw_import_data": json.dumps(row, ensure_ascii=False),
            "change_request_no": self._header_value(row, H_CHANGE_NO) or False,
            "cancel_date": cancel_date,
            "cancel_date_text": cancel_date_text,
            "has_cost": has_cost,
            "has_cost_text": has_cost_text,
            "cost_handling": self._header_value(row, H_COST_HANDLING) or False,
            "transfer_date": transfer_date,
            "transfer_date_text": transfer_date_text,
            "province_name": self._header_value(row, H_PROVINCE) or False,
            "group_name": self._header_value(row, H_GROUP) or False,
            "site_name": self._header_value(row, H_SITE) or False,
            "site_category": self._header_value(row, H_SITE_CATEGORY) or False,
            "product_line": self._header_value(row, H_PRODUCT_LINE) or False,
            "project_content": self._header_value(row, H_PROJECT_CONTENT) or False,
            "sale_manager": self._header_value(row, H_SALE_MANAGER) or False,
            "handover_meeting_date": handover_meeting_date,
            "handover_meeting_date_text": handover_meeting_date_text,
            "estimated_contract_amount": estimated_contract_amount,
            "estimated_contract_amount_text": estimated_contract_amount_text,
            "estimated_cost_amount": estimated_cost_amount,
            "estimated_cost_amount_text": estimated_cost_amount_text,
            "actual_contract_amount": actual_contract_amount,
            "actual_contract_amount_text": actual_contract_amount_text,
            "delivery_department": self._header_value(row, H_DELIVERY_DEPT) or False,
            "project_manager": self._header_value(row, H_PROJECT_MANAGER) or False,
            "arrival_date": arrival_date,
            "arrival_date_text": arrival_date_text,
            "acceptance_date": acceptance_date,
            "acceptance_date_text": acceptance_date_text,
            "note": self._header_value(row, H_NOTE) or False,
        }
        return vals, False

    def _upsert_project_start(self, vals):
        model = self.env["zfmd.project.start"].sudo()
        record = model.search([("name", "=", vals["name"])], limit=1)
        vals = self._confirmed_import_vals(vals, record)
        if record:
            record.with_context(skip_entry_confirmation_stage=True).write(vals)
            return record
        return model.create(vals)

    def _read_rows(self):
        if not self.upload_file:
            raise UserError(_("请先上传 07 开工申请登记台账 Excel 文件。"))
        file_bytes = base64.b64decode(self.upload_file)
        rows = zfmd_extract_by_alias(
            file_bytes,
            self._import_field_aliases,
            self._get_confirmed_mapping_from_lines(),
        )[1]
        if not rows:
            raise UserError(_("未识别到有效数据，请确认上传的是 07 开工申请登记台账。"))
        return rows

    def _reload_wizard_action(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("导入开工申请"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_detect_mapping(self):
        self._check_import_manager()
        self.ensure_one()
        if not self.upload_file:
            raise UserError(_("请先上传 Excel 文件。"))
        file_bytes = base64.b64decode(self.upload_file)
        try:
            pairs, review_required = self._prepare_mapping_step(
                file_bytes,
                self._import_field_aliases,
                self._import_field_labels,
                self._required_mapping_fields,
            )
        except ValueError:
            raise UserError(_("未能识别到有效表头，请确认上传的是 07 开工申请登记台账。"))
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
        self._check_import_manager()
        self.ensure_one()
        rows = self._read_rows()
        issue_lines = []
        unmatched_contract = 0
        skipped_count = 0

        for index, row in enumerate(rows, start=1):
            if not self._header_value(row, H_START_NO):
                issue_lines.append(f"第{index}行：缺少开工申请编号")
                skipped_count += 1
                continue
            contract_no = self._header_value(row, H_CONTRACT_NO)
            if contract_no and not self._find_contracts(contract_no):
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
        self._check_import_manager()
        self.ensure_one()
        self._check_import_previewed()
        rows = self._read_rows()
        imported_count = 0
        unmatched_contract = 0
        issue_lines = []

        for index, row in enumerate(rows, start=1):
            vals, error_message = self._prepare_project_start_vals(row)
            if not vals:
                issue_lines.append(f"第{index}行：{error_message}")
                continue
            if not vals.get("contract_id") and vals.get("source_contract_no"):
                unmatched_contract += 1
                issue_lines.append(
                    self._format_unmatched_contract_issue(index, vals.get("source_contract_no"), imported=True)
                )
            record = self._run_import_row_with_savepoint(
                index, issue_lines, lambda vals=vals: self._upsert_project_start(vals)
            )
            if not record:
                continue
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
                "message": f"成功导入 {imported_count} 条开工申请记录。",
                "type": "success" if not issue_lines else "warning",
                "sticky": bool(issue_lines),
            },
        }

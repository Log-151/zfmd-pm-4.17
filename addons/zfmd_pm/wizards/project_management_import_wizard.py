import base64

from odoo.exceptions import UserError

from odoo import _, fields, models

from .import_utils import (
    PROJECT_MANAGEMENT_FIELD_ALIASES,
    PROJECT_MANAGEMENT_FIELD_LABELS,
    ZfmdImportUtilityMixin,
    zfmd_extract_by_alias,
)

DATE_FIELDS = {
    "contract_sign_date",
    "service_start_date",
    "service_end_date",
    "invoice_date",
}
MONEY_FIELDS = {
    "initial_fee",
    "forecast_service_fee",
    "contract_amount",
    "paid_amount",
    "total_receivable_amount",
    "actual_total_receivable_amount",
    "invoiced_receivable_amount",
    "progress_receivable_amount",
    "actual_progress_receivable_amount",
    "bad_debt_amount",
    "invoiced_bad_debt_amount",
}


class ZfmdProjectManagementImportWizard(models.TransientModel, ZfmdImportUtilityMixin):
    _name = "zfmd.project.management.import.wizard"
    _description = "项目管理导入向导"

    file_name = fields.Char(string="文件名")
    upload_file = fields.Binary(string="上传 Excel", required=True)
    preview_summary = fields.Text(string="导入结果", readonly=True)
    preview_line_count = fields.Integer(string="识别记录数", readonly=True)
    imported_count = fields.Integer(string="导入成功数", readonly=True)
    warning_count = fields.Integer(string="跳过/问题记录数", readonly=True)
    mapping_summary = fields.Text(string="字段映射摘要", readonly=True)
    mapping_line_ids = fields.One2many("zfmd.import.mapping.line", "project_management_wizard_id", string="字段映射")
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
    _mapping_line_inverse_name = "project_management_wizard_id"
    _import_field_aliases = PROJECT_MANAGEMENT_FIELD_ALIASES
    _import_field_labels = PROJECT_MANAGEMENT_FIELD_LABELS
    _required_mapping_fields = {"name"}

    def _reload_wizard_action(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("导入项目管理"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def _read_rows(self):
        if not self.upload_file:
            raise UserError(_("请先上传项目管理 Excel 文件。"))
        file_bytes = base64.b64decode(self.upload_file)
        rows = zfmd_extract_by_alias(
            file_bytes,
            self._import_field_aliases,
            self._get_confirmed_mapping_from_lines(),
        )[1]
        rows = [row for row in rows if self._clean_value(row.get("name"))]
        if not rows:
            raise UserError(_("未识别到可导入的项目管理记录，请检查字段映射和表头。"))
        return rows

    def _prepare_vals(self, row):
        vals = {}
        for field_name in PROJECT_MANAGEMENT_FIELD_LABELS:
            value = row.get(field_name)
            if field_name in DATE_FIELDS:
                parsed = self._parse_date(value)
                vals[field_name] = parsed or False
            elif field_name in MONEY_FIELDS:
                vals[field_name] = self._parse_money(value)
            else:
                vals[field_name] = self._clean_value(value) or False
        vals["name"] = self._clean_value(vals.get("name")) or False
        return vals

    def _upsert_record(self, vals):
        model = self.env["zfmd.project.management"].sudo()
        record = model.search(
            [
                ("name", "=", vals["name"]),
                ("site_name", "=", vals.get("site_name") or False),
            ],
            limit=1,
        )
        if record:
            record.write(vals)
            return record
        return model.create(vals)

    def action_detect_mapping(self):
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
            raise UserError(_("未能识别到有效表头，请确认上传的是项目管理台账。"))
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
        seen = set()
        for index, row in enumerate(rows, start=1):
            name = self._clean_value(row.get("name"))
            if not name:
                issue_lines.append(f"第 {index} 行：缺少合同编号。")
                continue
            if name in seen:
                issue_lines.append(f"第 {index} 行：合同编号 {name} 在本次导入文件中重复，将按最后一条更新。")
            seen.add(name)

        self.write(
            {
                "preview_line_count": len(rows),
                "imported_count": 0,
                "warning_count": len(issue_lines),
                "preview_summary": self._write_import_summary(
                    total_count=len(rows),
                    imported_count=0,
                    skipped_count=len(issue_lines),
                    issue_lines=issue_lines,
                ),
                "result_summary_html": self._build_import_result_html(
                    title="预览完成，确认后可正式导入",
                    total_count=len(rows),
                    success_count=len(rows),
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
        issue_lines = []
        imported = 0
        for index, row in enumerate(rows, start=1):
            vals = self._prepare_vals(row)
            if not vals.get("name"):
                issue_lines.append(f"第 {index} 行：缺少合同编号，已跳过。")
                continue
            record = self._run_import_row_with_savepoint(
                index, issue_lines, lambda vals=vals: self._upsert_record(vals)
            )
            if not record:
                continue
            imported += 1

        self.write(
            {
                "preview_line_count": len(rows),
                "imported_count": imported,
                "warning_count": len(issue_lines),
                "preview_summary": self._write_import_summary(
                    total_count=len(rows),
                    imported_count=imported,
                    skipped_count=len(issue_lines),
                    issue_lines=issue_lines,
                ),
                "result_summary_html": self._build_import_result_html(
                    title="导入完成" if not issue_lines else "导入完成，存在需核对记录",
                    total_count=len(rows),
                    success_count=imported,
                    issue_count=len(issue_lines),
                    issue_lines=issue_lines,
                ),
                "state": "done",
            }
        )
        return self._reload_wizard_action()

import base64
import json

from odoo.exceptions import UserError

from odoo import _, fields, models

from .import_utils import (
    SERVICE_FIELD_ALIASES,
    SERVICE_FIELD_LABELS,
    ZfmdImportUtilityMixin,
    zfmd_extract_by_alias,
    zfmd_read_workbook_tables,
)

H_SIGNING_SALE_MANAGER = "签订合同销售经理"
H_SALE_MANAGER = "销售经理"
H_PROVINCE = "省（区）"
H_GROUP = "集团"
H_SITE_NAME = "场站名称"
H_SITE_CATEGORY = "场站类别"
H_START_FORECAST_DATE = "开始预报时间"
H_FORMAL_FORECAST_DATE = "正式预报时间"
H_SERVICE_END_DATE = "服务合同到期时间"
H_EXPIRED_MONTHS = "超期时间（月）"
H_IS_OVERDUE = "是否超期（是/否）"
H_EXPECTED_CONTRACT_AMOUNT = "预计签订服务合同金额（元）"
H_EXPECTED_CONTRACT_SIGN_DATE = "预计签订服务合同时间"
H_STOP_FORECAST_DATE = "停止预报时间"
H_BREAK_MONTHS = "中断时间（月）"
H_RENEWAL_NOTE = "续签服务合同情况说明"

H_RECORD_DATE = "记录日期"
H_RENEWAL_PRE_END = "续签前服务到期时间"
H_RENEWAL_AFTER_START = "续签后服务开始时间"
H_BREAK_FEE_HANDLING = "中断期间服务费如何处理"
H_NOTE = "备注"

SUMMARY_VALUES = {"", "合计", "总计", "小计", "汇总"}


class ZfmdServiceRecordImportWizard(models.TransientModel, ZfmdImportUtilityMixin):
    _name = "zfmd.service.record.import.wizard"
    _description = "气象服务记录导入向导"

    file_name = fields.Char(string="文件名")
    upload_file = fields.Binary(string="上传 Excel", required=True)
    preview_summary = fields.Text(string="导入结果", readonly=True)
    preview_line_count = fields.Integer(string="识别记录数", readonly=True)
    imported_count = fields.Integer(string="导入成功数", readonly=True)
    unmatched_count = fields.Integer(string="未匹配合同数", readonly=True)
    warning_count = fields.Integer(string="跳过/问题记录数", readonly=True)
    mapping_summary = fields.Text(string="字段映射摘要", readonly=True)
    mapping_line_ids = fields.One2many("zfmd.import.mapping.line", "service_record_wizard_id", string="字段映射")
    result_summary_html = fields.Html(string="导入结果摘要", readonly=True, sanitize=False)
    state = fields.Selection(
        [("draft", "待处理"), ("mapping", "确认字段映射"), ("previewed", "已预览"), ("done", "已导入")],
        default="draft",
        string="状态",
        readonly=True,
    )
    _mapping_line_field = "mapping_line_ids"
    _mapping_line_inverse_name = "service_record_wizard_id"
    _import_field_aliases = SERVICE_FIELD_ALIASES
    _import_field_labels = SERVICE_FIELD_LABELS
    _required_mapping_fields = {H_SITE_NAME, H_SERVICE_END_DATE}

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

    def _parse_int_and_text(self, value):
        clean = self._clean_value(value)
        if clean is False:
            return 0, False
        return int(self._parse_float(clean) or 0), str(clean)

    def _find_contract_for_row(self, row):
        site_name = self._header_value(row, H_SITE_NAME)
        if not site_name:
            return self.env["zfmd.contract"]
        domain = [("site_id.name", "=", site_name)]
        province = self._header_value(row, H_PROVINCE)
        group_name = self._header_value(row, H_GROUP)
        sale_manager = self._header_value(row, H_SIGNING_SALE_MANAGER) or self._header_value(row, H_SALE_MANAGER)
        if province:
            domain.append(("province_name", "=", province))
        if group_name:
            domain.append(("group_name", "=", group_name))
        if sale_manager:
            domain.append(("sale_manager", "=", sale_manager))
        contracts = self.env["zfmd.contract"].sudo().search(domain)
        return contracts if len(contracts) == 1 else self.env["zfmd.contract"]

    def _is_summary_or_blank_row(self, row):
        site_name = self._norm_text(self._header_value(row, H_SITE_NAME))
        service_end = self._norm_text(self._header_value(row, H_SERVICE_END_DATE))
        expected_amount = self._norm_text(self._header_value(row, H_EXPECTED_CONTRACT_AMOUNT))
        renewal_note = self._norm_text(self._header_value(row, H_RENEWAL_NOTE))
        if site_name in SUMMARY_VALUES and service_end in SUMMARY_VALUES:
            return True
        if service_end in {"合计", "总计", "小计", "汇总"}:
            return True
        has_business_value = any([site_name, service_end, expected_amount, renewal_note])
        return not has_business_value

    def _make_other_info_key(self, row):
        return (
            self._norm_text(self._header_value(row, H_SALE_MANAGER)),
            self._norm_text(self._header_value(row, H_PROVINCE)),
            self._norm_text(self._header_value(row, H_GROUP)),
            self._norm_text(self._header_value(row, H_SITE_NAME)),
            self._norm_text(self._header_value(row, H_SITE_CATEGORY)),
        )

    def _read_other_info_rows(self, file_bytes):
        tables = zfmd_read_workbook_tables(file_bytes)
        other_rows = {}
        for sheet_name, rows in tables.items():
            if "其他信息" not in str(sheet_name):
                continue
            header = None
            for row in rows:
                normalized = [self._norm_text(cell) for cell in row]
                if self._norm_text(H_RECORD_DATE) in normalized and self._norm_text(H_SITE_NAME) in normalized:
                    header = normalized
                    continue
                if not header:
                    continue
                if not any(normalized):
                    continue
                row_dict = {}
                for idx, key in enumerate(header):
                    if key:
                        row_dict[key] = row[idx] if idx < len(row) else ""
                key = (
                    self._norm_text(row_dict.get(self._norm_text(H_SALE_MANAGER))),
                    self._norm_text(row_dict.get(self._norm_text(H_PROVINCE))),
                    self._norm_text(row_dict.get(self._norm_text(H_GROUP))),
                    self._norm_text(row_dict.get(self._norm_text(H_SITE_NAME))),
                    self._norm_text(row_dict.get(self._norm_text(H_SITE_CATEGORY))),
                )
                other_rows[key] = row_dict
        return other_rows

    def _prepare_service_record_vals(self, row):
        site_name = self._header_value(row, H_SITE_NAME)
        if not site_name:
            return False, "缺少场站名称"

        contract = self._find_contract_for_row(row)
        source_contract_no = contract.name if contract else False
        chargeable, chargeable_text = self._normalize_yes_no("是")
        start_forecast_date, start_forecast_date_text = self._parse_date_and_text(row.get(H_START_FORECAST_DATE))
        formal_forecast_date, formal_forecast_date_text = self._parse_date_and_text(row.get(H_FORMAL_FORECAST_DATE))
        service_end_date, service_end_date_text = self._parse_date_and_text(row.get(H_SERVICE_END_DATE))
        expected_contract_amount, expected_contract_amount_text = self._parse_amount_and_text(
            row.get(H_EXPECTED_CONTRACT_AMOUNT)
        )
        expected_contract_sign_date, expected_contract_sign_date_text = self._parse_date_and_text(
            row.get(H_EXPECTED_CONTRACT_SIGN_DATE)
        )
        stop_forecast_date, stop_forecast_date_text = self._parse_date_and_text(row.get(H_STOP_FORECAST_DATE))
        _break_months_raw, break_months_text = self._parse_int_and_text(row.get(H_BREAK_MONTHS))
        expired_months, expired_months_text = self._parse_int_and_text(row.get(H_EXPIRED_MONTHS))
        is_overdue, is_overdue_text = self._normalize_yes_no(row.get(H_IS_OVERDUE))
        record_date, record_date_text = self._parse_date_and_text(row.get(H_RECORD_DATE))
        renewal_before_end_date, renewal_before_end_date_text = self._parse_date_and_text(row.get(H_RENEWAL_PRE_END))
        renewal_after_start_date, renewal_after_start_date_text = self._parse_date_and_text(
            row.get(H_RENEWAL_AFTER_START)
        )

        vals = {
            "contract_id": contract.id if contract else False,
            "source_contract_no": source_contract_no,
            "raw_import_data": json.dumps(row, ensure_ascii=False),
            "record_date": record_date,
            "record_date_text": record_date_text,
            "site_name": site_name,
            "site_category": self._header_value(row, H_SITE_CATEGORY) or False,
            "signing_sale_manager": self._header_value(row, H_SIGNING_SALE_MANAGER) or False,
            "sale_manager": self._header_value(row, H_SALE_MANAGER) or False,
            "province_name": self._header_value(row, H_PROVINCE) or False,
            "group_name": self._header_value(row, H_GROUP) or False,
            "chargeable": chargeable,
            "chargeable_text": chargeable_text,
            "start_forecast_date": start_forecast_date,
            "start_forecast_date_text": start_forecast_date_text,
            "formal_forecast_date": formal_forecast_date,
            "formal_forecast_date_text": formal_forecast_date_text,
            "service_end_date": service_end_date,
            "service_end_date_text": service_end_date_text,
            "expired_months": expired_months,
            "expired_months_text": expired_months_text,
            "is_overdue": is_overdue,
            "is_overdue_text": is_overdue_text,
            "expected_contract_amount": expected_contract_amount,
            "expected_contract_amount_text": expected_contract_amount_text,
            "expected_contract_sign_date": expected_contract_sign_date,
            "expected_contract_sign_date_text": expected_contract_sign_date_text,
            "stop_forecast_date": stop_forecast_date,
            "stop_forecast_date_text": stop_forecast_date_text,
            "break_months_text": break_months_text,
            "renewal_note": self._header_value(row, H_RENEWAL_NOTE) or False,
            "renewal_before_end_date": renewal_before_end_date,
            "renewal_before_end_date_text": renewal_before_end_date_text,
            "renewal_after_start_date": renewal_after_start_date,
            "renewal_after_start_date_text": renewal_after_start_date_text,
            "break_fee_handling": self._header_value(row, H_BREAK_FEE_HANDLING) or False,
            "note": self._header_value(row, H_NOTE) or False,
        }
        return vals, False

    def _upsert_service_record(self, vals):
        model = self.env["zfmd.service.record"].sudo()
        domain = [
            ("site_name", "=", vals["site_name"]),
            ("formal_forecast_date", "=", vals.get("formal_forecast_date")),
            ("formal_forecast_date_text", "=", vals.get("formal_forecast_date_text") or False),
            ("service_end_date", "=", vals.get("service_end_date")),
            ("service_end_date_text", "=", vals.get("service_end_date_text") or False),
            ("sale_manager", "=", vals.get("sale_manager") or False),
        ]
        record = model.search(domain, limit=1)
        if record:
            record.write(vals)
            return record
        return model.create(vals)

    def _read_rows(self):
        if not self.upload_file:
            raise UserError(_("请先上传 08 气象服务记录台账 Excel 文件。"))
        file_bytes = base64.b64decode(self.upload_file)
        raw_rows = zfmd_extract_by_alias(
            file_bytes, self._import_field_aliases, self._get_confirmed_mapping_from_lines()
        )[1]
        if not raw_rows:
            raise UserError(_("未识别到有效数据，请确认上传的是 08 气象服务记录台账。"))

        other_info_map = self._read_other_info_rows(file_bytes)

        rows = []
        for row in raw_rows:
            if self._is_summary_or_blank_row(row):
                continue
            key = self._make_other_info_key(row)
            if key in other_info_map:
                row.update(other_info_map[key])
            rows.append(row)

        if not rows:
            raise UserError(_("识别到的内容均为汇总行或空白说明行，没有可导入的服务记录。"))
        return rows

    def _reload_wizard_action(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("导入气象服务记录"),
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
            raise UserError(_("未能识别到有效表头，请确认上传的是 08 气象服务记录台账。"))
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
            vals, error_message = self._prepare_service_record_vals(row)
            if not vals:
                issue_lines.append(f"第{index}行：{error_message}")
                skipped_count += 1
                continue
            if not vals.get("contract_id"):
                unmatched_contract += 1
                issue_lines.append(self._format_unmatched_contract_issue(index))

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
            vals, error_message = self._prepare_service_record_vals(row)
            if not vals:
                issue_lines.append(f"第{index}行：{error_message}")
                continue
            if not vals.get("contract_id"):
                unmatched_contract += 1
                issue_lines.append(self._format_unmatched_contract_issue(index, imported=True))
            self._upsert_service_record(vals)
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
                "message": f"成功导入 {imported_count} 条气象服务记录。",
                "type": "success" if not issue_lines else "warning",
                "sticky": bool(issue_lines),
            },
        }

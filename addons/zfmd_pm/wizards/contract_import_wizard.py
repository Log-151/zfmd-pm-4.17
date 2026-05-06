import base64
import json

from odoo import _, fields, models
from odoo.exceptions import UserError

from .import_utils import (
    CONTRACT_FIELD_ALIASES,
    CONTRACT_FIELD_LABELS,
    ZfmdImportUtilityMixin,
    _normalize_text,
    zfmd_extract_by_alias,
)

SUMMARY_KEYWORDS = {"", "合计", "总计", "汇总", "小计"}


class ZfmdContractImportWizard(models.TransientModel, ZfmdImportUtilityMixin):
    _name = "zfmd.contract.import.wizard"
    _description = "合同导入向导"

    file_name = fields.Char(string="文件名")
    upload_file = fields.Binary(string="上传 Excel")

    # Mapping step
    detected_headers_json = fields.Text(string="识别表头 JSON", readonly=True)
    field_mapping_json = fields.Text(string="字段映射 JSON")
    mapping_summary = fields.Text(string="字段映射摘要", readonly=True)

    # Results
    preview_line_count = fields.Integer(string="识别记录数", readonly=True)
    imported_count = fields.Integer(string="导入成功数", readonly=True)
    skipped_count = fields.Integer(string="跳过行数", readonly=True)
    failed_count = fields.Integer(string="失败行数", readonly=True)
    unmatched_count = fields.Integer(string="未匹配合同数", readonly=True)
    warning_count = fields.Integer(string="跳过/问题记录数", readonly=True)
    preview_summary = fields.Text(string="导入结果", readonly=True)

    state = fields.Selection(
        [("draft", "待上传"), ("mapping", "确认字段映射"), ("done", "导入完成")],
        default="draft",
        string="状态",
        readonly=True,
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _read_file_bytes(self):
        if not self.upload_file:
            raise UserError(_("请先上传 Excel 文件。"))
        return base64.b64decode(self.upload_file)

    def _reload_wizard_action(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("导入合同台账"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def _get_confirmed_mapping(self):
        """Return {normalized_header: field_name} from stored JSON, or None."""
        if not self.field_mapping_json:
            return None
        try:
            mapping = json.loads(self.field_mapping_json)
        except Exception:
            raise UserError(_("字段映射 JSON 格式错误，请修正后再导入。"))
        if not isinstance(mapping, dict):
            raise UserError(_("字段映射 JSON 必须是对象格式，例如 {\"合同编号\": \"name\"}。"))
        return mapping

    def _is_summary_or_blank_row(self, row):
        contract_no = self._clean_value(row.get("name"))
        customer_name = self._clean_value(row.get("_customer_name"))
        contract_name = self._clean_value(row.get("contract_name"))
        if (
            self._norm_text(contract_no) in SUMMARY_KEYWORDS
            and self._norm_text(customer_name) in SUMMARY_KEYWORDS
        ):
            return True
        return not any([contract_no, customer_name, contract_name])

    # ------------------------------------------------------------------
    # Cache building  (avoids N+1 queries for 3000-row imports)
    # ------------------------------------------------------------------

    def _build_caches(self):
        contracts = self.env["zfmd.contract"].sudo().search([])
        partners = self.env["res.partner"].sudo().search([])
        sites = self.env["zfmd.site"].sudo().search([])
        return {
            "contracts_by_key": {c.contract_key: c for c in contracts if c.contract_key},
            "contracts_by_name": {c.name: c for c in contracts},
            "partners": {p.name: p for p in partners},
            "sites": {(s.name, s.partner_id.id or False): s for s in sites},
        }

    def _ensure_partner_cached(self, name, province, group_name, cache):
        partner_name = self._clean_value(name)
        if not partner_name:
            return False
        if partner_name in cache["partners"]:
            partner = cache["partners"][partner_name]
            vals_to_update = {}
            if not partner.is_zfmd_customer:
                vals_to_update["is_zfmd_customer"] = True
            if province and not partner.province_name:
                vals_to_update["province_name"] = self._clean_value(province)
            if group_name and not partner.group_name:
                vals_to_update["group_name"] = self._clean_value(group_name)
            if vals_to_update:
                partner.sudo().write(vals_to_update)
            return partner.id
        vals = {
            "name": partner_name,
            "is_zfmd_customer": True,
            "province_name": self._clean_value(province) or False,
            "group_name": self._clean_value(group_name) or False,
            "company_type": "company",
        }
        p = self.env["res.partner"].sudo().create(vals)
        cache["partners"][partner_name] = p
        return p.id

    def _ensure_site_cached(
        self, name, partner_id, province, group_name, site_category, other_name, cache
    ):
        site_name = self._clean_value(name)
        if not site_name:
            return False
        site_key = (site_name, partner_id or False)
        if site_key in cache["sites"]:
            return cache["sites"][site_key].id
        vals = {
            "name": site_name,
            "partner_id": partner_id or False,
            "province_name": self._clean_value(province) or False,
            "group_name": self._clean_value(group_name) or False,
            "site_category": self._clean_value(site_category) or False,
            "other_name": self._clean_value(other_name) or False,
        }
        s = self.env["zfmd.site"].sudo().create(vals)
        cache["sites"][site_key] = s
        return s.id

    def _upsert_contract_cached(self, vals, cache):
        contract_key = vals.get("contract_key")
        name = vals.get("name")
        existing = None
        if contract_key:
            existing = cache["contracts_by_key"].get(contract_key)
        if not existing and name:
            existing = cache["contracts_by_name"].get(name)
        if existing:
            existing.write(vals)
            return existing
        contract = self.env["zfmd.contract"].sudo().create(vals)
        if contract_key:
            cache["contracts_by_key"][contract_key] = contract
        cache["contracts_by_name"][contract.name] = contract
        return contract

    # ------------------------------------------------------------------
    # Row-level helpers
    # ------------------------------------------------------------------

    def _safe_parse_date(self, value, label, warn_list):
        result = self._parse_date(value)
        if result is False and self._clean_value(value):
            warn_list.append(label)
        return result

    def _prepare_contract_vals(self, row, partner_id, site_id, warn_list):
        """Build vals dict from a row keyed by field_name."""
        contract_no = self._clean_value(row.get("name"))
        if not contract_no:
            return False
        return {
            "name": contract_no,
            "contract_key": self._extract_contract_key(contract_no),
            "contract_name": self._clean_value(row.get("contract_name")) or False,
            "customer_level_1": self._clean_value(row.get("customer_level_1")) or False,
            "customer_level_2": self._clean_value(row.get("customer_level_2")) or False,
            "customer_level_3": self._clean_value(row.get("customer_level_3")) or False,
            "partner_id": partner_id or False,
            "site_id": site_id or False,
            "site_other_name": self._clean_value(row.get("site_other_name")) or False,
            "site_category": self._clean_value(row.get("site_category")) or False,
            "capacity_text": self._clean_value(row.get("capacity_text")) or False,
            "contract_project_no": self._clean_value(row.get("contract_project_no")) or False,
            "province_name": self._clean_value(row.get("province_name")) or False,
            "group_name": self._clean_value(row.get("group_name")) or False,
            "product_line": self._clean_value(row.get("product_line")) or False,
            "project_content": self._clean_value(row.get("project_content")) or False,
            "sale_manager": self._clean_value(row.get("sale_manager")) or False,
            "sale_contact": self._clean_value(row.get("sale_contact")) or False,
            "contract_sign_date": self._safe_parse_date(
                row.get("contract_sign_date"), "合同签订日期", warn_list
            ),
            "archive_date": self._safe_parse_date(
                row.get("archive_date"), "存档日期", warn_list
            ),
            "archive_document_type": self._clean_value(row.get("archive_document_type")) or False,
            "archive_copy_count": int(self._parse_float(row.get("archive_copy_count")) or 0),
            "service_start_date": self._safe_parse_date(
                row.get("service_start_date"), "服务开始日期", warn_list
            ),
            "service_end_date": self._safe_parse_date(
                row.get("service_end_date"), "服务结束日期", warn_list
            ),
            "initial_fee": self._parse_float(row.get("initial_fee")),
            "service_fee": self._parse_float(row.get("service_fee")),
            "amount_total": self._parse_float(row.get("amount_total")),
            "amount_untaxed": self._parse_float(row.get("amount_untaxed")),
            "exclude_sales_revenue": self._clean_value(row.get("exclude_sales_revenue")) or False,
            "exclude_sales_performance": self._clean_value(
                row.get("exclude_sales_performance")
            ) or False,
            "bond_status": self._clean_value(row.get("bond_status")) or False,
            "delivery_department": self._clean_value(row.get("delivery_department")) or False,
            "project_manager": self._clean_value(row.get("project_manager")) or False,
            "handover_meeting_date": self._safe_parse_date(
                row.get("handover_meeting_date"), "交底会时间", warn_list
            ),
            "third_party_interface_fee": self._parse_float(row.get("third_party_interface_fee")),
            "start_application_no": self._clean_value(row.get("start_application_no")) or False,
            "after_sale_no": self._clean_value(row.get("after_sale_no")) or False,
            "change_no": self._clean_value(row.get("change_no")) or False,
            "note": self._clean_value(row.get("note")) or False,
            "state": "running",
        }

    # ------------------------------------------------------------------
    # Wizard actions
    # ------------------------------------------------------------------

    def action_detect_mapping(self):
        """Step 1 → Step 2: parse Excel headers and auto-match against alias table."""
        self.ensure_one()
        file_bytes = self._read_file_bytes()
        pairs, _ = zfmd_extract_by_alias(file_bytes, CONTRACT_FIELD_ALIASES)
        if not pairs:
            raise UserError(_("未能识别到有效表头，请确认上传的是合同台账 Excel 文件。"))

        confirmed = {
            _normalize_text(h): fn
            for h, fn in pairs
            if fn and _normalize_text(h)
        }

        matched = [(h, fn) for h, fn in pairs if fn]
        unmatched_headers = [h for h, fn in pairs if not fn and h.strip()]
        missing_required = {"name", "_customer_name"} - {fn for _, fn in matched}

        lines = [
            f"识别到 {len(pairs)} 列表头，成功匹配 {len(matched)} 个字段。",
            "",
            "已匹配字段：",
        ]
        for h, fn in matched:
            lines.append(f"  {h}  →  {CONTRACT_FIELD_LABELS.get(fn, fn)}")

        if unmatched_headers:
            lines += [
                "",
                f"未匹配的 Excel 列（导入时忽略，共 {len(unmatched_headers)} 列）：",
            ]
            for h in unmatched_headers[:20]:
                lines.append(f"  {h}")
            if len(unmatched_headers) > 20:
                lines.append(f"  …共 {len(unmatched_headers)} 列未匹配")

        if missing_required:
            lines += ["", "警告：以下必填字段未匹配，缺失该字段的行将被跳过："]
            for fn in missing_required:
                lines.append(f"  {CONTRACT_FIELD_LABELS.get(fn, fn)}")
        else:
            lines += ["", "必填字段（合同编号、客户名称）均已匹配。"]

        review_required = bool(missing_required or unmatched_headers)
        if review_required:
            lines += [
                "",
                "系统已自动完成可识别字段的映射。请重点检查未匹配列和必填字段；如需调整，请编辑下方字段映射 JSON。",
                "JSON 规则：左侧为 Excel 表头，右侧为系统字段名；未写入 JSON 的 Excel 列会在导入时忽略。",
                "确认无误后，点击「按当前映射导入」开始导入。",
            ]
        else:
            lines += ["", "所有有效表头均已自动匹配，系统将直接按当前映射导入。"]

        self.write(
            {
                "detected_headers_json": json.dumps(
                    [list(p) for p in pairs], ensure_ascii=False
                ),
                "field_mapping_json": json.dumps(confirmed, ensure_ascii=False),
                "mapping_summary": "\n".join(lines),
                "state": "mapping",
            }
        )
        if not review_required:
            return self.action_import()
        return self._reload_wizard_action()

    def action_import(self):
        """Step 2 → Step 3: import using the confirmed field mapping."""
        self.ensure_one()
        file_bytes = self._read_file_bytes()
        confirmed_mapping = self._get_confirmed_mapping()

        _, data_rows = zfmd_extract_by_alias(
            file_bytes, CONTRACT_FIELD_ALIASES, confirmed_mapping
        )
        rows = [r for r in data_rows if not self._is_summary_or_blank_row(r)]
        if not rows:
            raise UserError(_("识别到的内容均为空白行或汇总行，没有可导入的合同记录。"))

        cache = self._build_caches()
        imported_count = 0
        skipped_count = 0
        failed_count = 0
        issue_lines = []

        for index, row in enumerate(rows, start=1):
            try:
                with self.env.cr.savepoint():
                    contract_no = self._clean_value(row.get("name"))
                    if not contract_no:
                        skipped_count += 1
                        issue_lines.append(f"第 {index} 行：缺少合同编号，已跳过。")
                        continue

                    partner_id = self._ensure_partner_cached(
                        row.get("_customer_name"),
                        row.get("province_name"),
                        row.get("group_name"),
                        cache,
                    )
                    site_id = self._ensure_site_cached(
                        row.get("_site_name"),
                        partner_id,
                        row.get("province_name"),
                        row.get("group_name"),
                        row.get("site_category"),
                        row.get("site_other_name"),
                        cache,
                    )

                    warn_fields = []
                    vals = self._prepare_contract_vals(row, partner_id, site_id, warn_fields)
                    if not vals:
                        skipped_count += 1
                        issue_lines.append(f"第 {index} 行：无法构建合同数据，已跳过。")
                        continue

                    if warn_fields:
                        issue_lines.append(
                            f"第 {index} 行（{contract_no}）：以下字段无法解析已置空："
                            + "、".join(warn_fields)
                        )

                    vals["display_order"] = index
                    self._upsert_contract_cached(vals, cache)
                    imported_count += 1

            except Exception as exc:
                failed_count += 1
                short_msg = str(exc)[:120].replace("\n", " ")
                issue_lines.append(f"第 {index} 行：处理失败 — {short_msg}")

        summary_lines = [
            f"识别记录数：{len(rows)}",
            f"导入成功数：{imported_count}",
            f"跳过行数：{skipped_count}",
            f"失败行数：{failed_count}",
        ]
        if issue_lines:
            summary_lines += ["", "问题明细："] + issue_lines[:50]
            if len(issue_lines) > 50:
                summary_lines.append(f"…（共 {len(issue_lines)} 条问题，仅展示前 50 条）")

        self.write(
            {
                "preview_line_count": len(rows),
                "imported_count": imported_count,
                "skipped_count": skipped_count,
                "failed_count": failed_count,
                "warning_count": skipped_count + failed_count,
                "unmatched_count": 0,
                "preview_summary": "\n".join(summary_lines),
                "state": "done",
            }
        )
        return self._reload_wizard_action()

    def action_reset(self):
        """Return to step 1 without clearing the uploaded file."""
        self.ensure_one()
        self.write(
            {
                "state": "draft",
                "detected_headers_json": False,
                "field_mapping_json": False,
                "mapping_summary": False,
                "preview_line_count": 0,
                "imported_count": 0,
                "skipped_count": 0,
                "failed_count": 0,
                "warning_count": 0,
                "unmatched_count": 0,
                "preview_summary": False,
            }
        )
        return True

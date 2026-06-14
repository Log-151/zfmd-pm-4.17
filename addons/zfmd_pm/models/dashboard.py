import json
from calendar import monthrange
from datetime import timedelta
from urllib.parse import quote

from markupsafe import Markup, escape
from odoo.exceptions import UserError
from odoo.tools import format_datetime

from odoo import api, fields, models

ACTIVE_WARNING_STATES = ("open", "processing", "postponed")


class ZfmdDashboard(models.Model):
    _name = "zfmd.dashboard"
    _description = "ZFMD Dashboard"

    name = fields.Char(string="名称", required=True)
    page_mode = fields.Selection(
        [
            ("overview", "全局概览"),
            ("query", "统一查询中心"),
        ],
        string="页面模式",
        default="query",
        required=True,
    )
    query_target = fields.Selection(
        [
            ("contract", "合同台账"),
            ("project_start", "开工申请"),
            ("service_record", "服务记录"),
            ("invoice_record", "开票登记"),
            ("payment_record", "回款登记"),
            ("receivable_plan", "应收计划"),
            ("project_management", "项目管理"),
            ("after_sale_service", "售后服务"),
        ],
        string="查询对象",
        default="contract",
        required=True,
    )
    date_from = fields.Date(string="开始日期")
    date_to = fields.Date(string="结束日期")
    keyword = fields.Char(string="关键词")
    contract_no = fields.Char(string="合同编号")
    customer_name = fields.Char(string="客户/付款单位")
    payer_name = fields.Char(string="付款单位")
    site_name = fields.Char(string="场站")
    sale_manager = fields.Char(string="销售经理")
    province_name = fields.Char(string="省区")
    group_name = fields.Char(string="集团")
    product_line = fields.Char(string="产品线")
    state = fields.Char(string="状态")
    amount_min = fields.Float(string="金额不低于（元）")
    amount_max = fields.Float(string="金额不超过（元）")

    show_customer_filter = fields.Boolean(compute="_compute_filter_visibility", string="显示客户过滤")
    show_payer_filter = fields.Boolean(compute="_compute_filter_visibility", string="显示付款单位过滤")
    show_state_filter = fields.Boolean(compute="_compute_filter_visibility", string="显示状态过滤")

    result_object_label = fields.Char(string="结果对象")
    result_count = fields.Integer(string="匹配记录数")
    result_amount_label = fields.Char(string="金额口径")
    result_amount_total = fields.Float(string="汇总金额")
    result_last_query_at = fields.Datetime(string="最近查询时间")
    result_ids_json = fields.Text(string="结果ID JSON")
    result_domain_json = fields.Text(string="结果Domain JSON")

    condition_hint_html = fields.Html(string="条件提示", sanitize=False)
    result_overview_html = fields.Html(string="结果概览", sanitize=False)
    result_summary_html = fields.Html(string="结果摘要", sanitize=False)
    result_preview_html = fields.Html(string="结果预览", sanitize=False)
    detail_scope_html = fields.Html(string="明细说明", sanitize=False)
    export_scope_html = fields.Html(string="导出说明", sanitize=False)
    sales_report_html = fields.Html(string="销售合同额统计", sanitize=False)
    comparison_years = fields.Char(string="同期对比年份")
    management_report_html = fields.Html(string="经营管理周例会统计", sanitize=False)
    template_name = fields.Char(string="统计模板名称")
    selected_template_id = fields.Many2one("zfmd.dashboard.template", string="已保存统计模板")
    global_result_html = fields.Html(string="全局统计结果", sanitize=False)
    overview_metrics_html = fields.Html(string="概览指标", sanitize=False)
    overview_warning_html = fields.Html(string="概览预警", sanitize=False)
    overview_shortcuts_html = fields.Html(string="概览快捷入口", sanitize=False)

    @api.depends("query_target")
    def _compute_filter_visibility(self):
        for record in self:
            record.show_customer_filter = record.query_target in {
                "contract",
                "invoice_record",
                "project_start",
                "service_record",
                "receivable_plan",
                "project_management",
                "after_sale_service",
            }
            record.show_payer_filter = record.query_target == "payment_record"
            record.show_state_filter = record.query_target in {
                "contract",
                "project_start",
                "invoice_record",
                "receivable_plan",
            }

    def _target_configs(self):
        return {
            "contract": {
                "label": "合同台账",
                "model": "zfmd.contract",
                "date_field": "contract_sign_date",
                "amount_field": "amount_total",
                "amount_label": "合同总额（元）",
                "list_action": "zfmd_pm.action_zfmd_contract",
                "contract_fields": ("name", "contract_key", "contract_project_no"),
                "customer_fields": (
                    "partner_id.name",
                    "customer_level_1",
                    "customer_level_2",
                    "customer_level_3",
                ),
                "site_fields": ("site_id.name", "site_other_name"),
                "keyword_fields": (
                    "name",
                    "contract_key",
                    "contract_name",
                    "partner_id.name",
                    "site_id.name",
                    "customer_level_1",
                    "customer_level_2",
                    "customer_level_3",
                    "site_other_name",
                    "site_category",
                    "capacity_text",
                    "contract_project_no",
                    "province_name",
                    "group_name",
                    "product_line",
                    "project_content",
                    "sale_manager",
                    "sale_contact",
                    "archive_document_type",
                    "exclude_sales_revenue",
                    "exclude_sales_performance",
                    "bond_status",
                    "delivery_department",
                    "project_manager",
                    "start_application_no",
                    "after_sale_no",
                    "change_no",
                    "note",
                ),
                "preview_fields": [
                    ("name", "合同编号"),
                    ("partner_id", "客户"),
                    ("site_id", "场站"),
                    ("sale_manager", "销售经理"),
                    ("amount_total", "合同总额（元）"),
                    ("state", "状态"),
                ],
            },
            "project_start": {
                "label": "开工申请",
                "model": "zfmd.project.start",
                "date_field": "transfer_date",
                "amount_field": "actual_contract_amount",
                "amount_label": "实际合同金额（元）",
                "list_action": "zfmd_pm.action_zfmd_project_start",
                "contract_fields": (
                    "display_contract_no",
                    "source_contract_no",
                    "contract_id.name",
                ),
                "customer_fields": ("contract_id.partner_id.name",),
                "site_fields": ("site_name",),
                "keyword_fields": (
                    "name",
                    "display_contract_no",
                    "source_contract_no",
                    "contract_id.name",
                    "change_request_no",
                    "contract_id.partner_id.name",
                    "site_name",
                    "site_category",
                    "province_name",
                    "group_name",
                    "product_line",
                    "project_content",
                    "sale_manager",
                    "delivery_department",
                    "project_manager",
                    "has_cost",
                    "cost_handling",
                    "note",
                ),
                "preview_fields": [
                    ("name", "开工申请号"),
                    ("display_contract_no", "合同编号"),
                    ("group_name", "集团"),
                    ("site_name", "场站"),
                    ("sale_manager", "销售经理"),
                    ("state", "状态"),
                ],
            },
            "service_record": {
                "label": "服务记录",
                "model": "zfmd.service.record",
                "date_field": "record_date",
                "amount_field": "expected_contract_amount",
                "amount_label": "预计签订服务合同金额（元）",
                "list_action": "zfmd_pm.action_zfmd_service_record",
                "contract_fields": (
                    "display_contract_no",
                    "source_contract_no",
                    "contract_id.name",
                ),
                "customer_fields": ("contract_id.partner_id.name",),
                "site_fields": ("site_name", "site_id.name"),
                "keyword_fields": (
                    "name",
                    "display_contract_no",
                    "source_contract_no",
                    "contract_id.name",
                    "contract_id.partner_id.name",
                    "site_name",
                    "site_id.name",
                    "site_category",
                    "signing_sale_manager",
                    "sale_manager",
                    "province_name",
                    "group_name",
                    "product_line",
                    "service_type",
                    "service_content",
                    "chargeable",
                    "renewal_note",
                    "break_fee_handling",
                    "note",
                ),
                "preview_fields": [
                    ("name", "服务记录号"),
                    ("display_contract_no", "合同编号"),
                    ("site_name", "场站"),
                    ("sale_manager", "销售经理"),
                    ("service_end_date", "服务到期时间"),
                    ("is_overdue", "是否超期"),
                ],
            },
            "invoice_record": {
                "label": "开票登记",
                "model": "zfmd.invoice.record",
                "date_field": "invoice_date",
                "amount_field": "invoice_amount",
                "amount_label": "开票金额（元）",
                "list_action": "zfmd_pm.action_zfmd_invoice_record",
                "contract_fields": (
                    "display_contract_no",
                    "source_contract_no",
                    "contract_id.name",
                ),
                "customer_fields": (
                    "invoice_partner_name",
                    "contract_id.partner_id.name",
                ),
                "site_fields": ("site_name",),
                "keyword_fields": (
                    "name",
                    "display_contract_no",
                    "source_contract_no",
                    "contract_id.name",
                    "invoice_partner_name",
                    "contract_id.partner_id.name",
                    "site_name",
                    "project_content",
                    "sale_manager",
                    "sale_contact",
                    "tax_rate",
                    "promised_payment_note",
                    "actual_payment_date_note",
                    "actual_payment_amount_note",
                    "express_no",
                    "cancel_reason",
                    "note",
                ),
                "preview_fields": [
                    ("display_contract_no", "合同编号"),
                    ("invoice_date", "开票日期"),
                    ("invoice_partner_name", "开票客户"),
                    ("sale_manager", "销售经理"),
                    ("invoice_amount", "开票金额（元）"),
                    ("state", "状态"),
                ],
            },
            "payment_record": {
                "label": "回款登记",
                "model": "zfmd.payment.record",
                "date_field": "payment_date",
                "amount_field": "amount_total",
                "amount_label": "回款金额（元）",
                "list_action": "zfmd_pm.action_zfmd_payment_record",
                "contract_fields": (
                    "display_contract_no",
                    "source_contract_no",
                    "contract_id.name",
                ),
                "customer_fields": ("payer_name", "contract_id.partner_id.name"),
                "site_fields": ("site_name",),
                "keyword_fields": (
                    "name",
                    "display_contract_no",
                    "source_contract_no",
                    "contract_id.name",
                    "payer_name",
                    "contract_id.partner_id.name",
                    "site_name",
                    "project_content",
                    "sale_manager",
                    "sale_contact",
                    "payment_type",
                    "payment_item_name",
                    "payment_ratio_text",
                    "note",
                ),
                "preview_fields": [
                    ("display_contract_no", "合同编号"),
                    ("payment_date", "回款日期"),
                    ("payer_name", "付款单位"),
                    ("sale_manager", "销售经理"),
                    ("amount_total", "回款金额（元）"),
                    ("payment_item_name", "回款项名称"),
                ],
            },
            "receivable_plan": {
                "label": "应收计划",
                "model": "zfmd.receivable.plan",
                "date_field": "receivable_date",
                "amount_field": "receivable_amount",
                "amount_label": "应收金额（元）",
                "list_action": "zfmd_pm.action_zfmd_receivable_plan",
                "contract_fields": (
                    "display_contract_no",
                    "source_contract_no",
                    "contract_id.name",
                ),
                "customer_fields": ("contract_id.partner_id.name",),
                "site_fields": ("site_name",),
                "keyword_fields": (
                    "name",
                    "display_contract_no",
                    "source_contract_no",
                    "contract_id.name",
                    "receivable_item_name",
                    "contract_id.partner_id.name",
                    "site_name",
                    "project_content",
                    "sale_manager",
                    "sale_contact",
                    "payment_category",
                    "payment_term",
                    "pending_progress_date",
                    "source_contract_no",
                    "note",
                ),
                "preview_fields": [
                    ("display_contract_no", "合同编号"),
                    ("receivable_item_name", "应收款项名称"),
                    ("receivable_date", "应收日期"),
                    ("sale_manager", "销售经理"),
                    ("receivable_amount", "应收金额（元）"),
                    ("state", "状态"),
                ],
            },
            "project_management": {
                "label": "项目管理",
                "model": "zfmd.project.management",
                "date_field": "invoice_date",
                "amount_field": "contract_amount",
                "amount_label": "合同总额（元）",
                "list_action": "zfmd_pm.action_zfmd_project_management",
                "contract_fields": ("name", "contract_key", "contract_id.name"),
                "customer_fields": (
                    "customer_name",
                    "customer_level_1",
                    "customer_level_2",
                    "customer_level_3",
                ),
                "site_fields": ("site_name",),
                "keyword_fields": (
                    "name",
                    "contract_key",
                    "contract_id.name",
                    "customer_name",
                    "customer_level_1",
                    "customer_level_2",
                    "customer_level_3",
                    "site_name",
                    "province_name",
                    "group_name",
                    "product_line",
                    "project_content",
                    "contract_sale_manager",
                    "sale_contact",
                    "delivery_department",
                    "project_manager",
                    "contract_execution_status",
                    "invoice_status",
                    "progress_receivable_item_name",
                    "customer_code",
                    "has_bad_debt",
                    "note",
                ),
                "preview_fields": [
                    ("name", "合同编号"),
                    ("contract_match_state", "匹配状态"),
                    ("customer_name", "客户名称"),
                    ("site_name", "场站"),
                    ("contract_sale_manager", "销售经理"),
                    ("contract_amount", "合同总额（元）"),
                    ("paid_amount", "已回款（元）"),
                ],
            },
            "after_sale_service": {
                "label": "售后服务",
                "model": "zfmd.after.sale.service",
                "amount_field": "receivable_amount",
                "amount_label": "应收款（元）",
                "list_action": "zfmd_pm.action_zfmd_after_sale_service",
                "contract_fields": ("contract_no",),
                "customer_fields": (),
                "site_fields": ("site_name",),
                "keyword_fields": (
                    "name",
                    "contract_no",
                    "sale_manager",
                    "province_name",
                    "group_name",
                    "site_name",
                    "product_line",
                    "service_content",
                    "note",
                ),
                "preview_fields": [
                    ("name", "服务收费确认单编号"),
                    ("contract_no", "对应合同编号"),
                    ("site_name", "场站"),
                    ("sale_manager", "销售经理"),
                    ("receivable_amount", "应收款（元）"),
                    ("payable_amount", "应付款（元）"),
                ],
            },
        }

    def _get_config(self):
        self.ensure_one()
        return self._target_configs()[self.query_target]

    def _field_exists(self, model_name, field_name):
        return field_name in self.env[model_name]._fields

    def _selection_values_for_text(self, model_name, field_name, text):
        field = self.env[model_name]._fields.get(field_name)
        if not field or field.type != "selection" or not text:
            return []
        needle = str(text).strip().lower()
        selection = field.selection
        if isinstance(selection, str):
            selection = getattr(self.env[model_name], selection)()
        if callable(selection):
            selection = selection(self.env[model_name])
        values = []
        for value, label in selection or []:
            if needle in str(value).lower() or needle in str(label).lower():
                values.append(value)
        return values

    def _format_amount(self, amount):
        if amount in (False, None):
            return "-"
        return f"{amount:,.2f}"

    def _format_value(self, record, field_name, value):
        if value in (False, None, ""):
            return "-"
        field = record._fields.get(field_name)
        if not field:
            return str(value)
        if field.type == "many2one":
            return value.display_name if value else "-"
        if field.type in ("float", "monetary"):
            return self._format_amount(value)
        if field.type == "boolean":
            return "是" if value else "否"
        if field.type == "date":
            return fields.Date.to_string(value)
        if field.type == "datetime":
            return fields.Datetime.to_string(value)
        return str(value)

    def _or_domain(self, field_names, keyword):
        field_names = [name for name in field_names if name]
        if not field_names or not keyword:
            return []
        domain = []
        for index, field_name in enumerate(field_names):
            if index:
                domain.insert(0, "|")
            domain.append((field_name, "ilike", keyword))
        return domain

    def _field_path_exists(self, model_name, field_path):
        current_model = self.env[model_name]
        parts = field_path.split(".")
        for index, part in enumerate(parts):
            field = current_model._fields.get(part)
            if not field:
                return False
            if index < len(parts) - 1 and field.type != "many2one":
                return False
            if field.type == "many2one":
                current_model = self.env[field.comodel_name]
        return True

    def _existing_field_paths(self, model_name, field_paths):
        return [field_path for field_path in field_paths if self._field_path_exists(model_name, field_path)]

    def _build_query_domain(self):
        self.ensure_one()
        config = self._get_config()
        model_name = config["model"]
        domain = [("entry_state", "=", "confirmed")] if self._field_exists(model_name, "entry_state") else []

        date_field = config.get("date_field")
        if date_field and self._field_exists(model_name, date_field):
            if self.date_from:
                domain.append((date_field, ">=", self.date_from))
            if self.date_to:
                domain.append((date_field, "<=", self.date_to))

        if self.contract_no:
            contract_fields = self._existing_field_paths(
                model_name,
                config.get(
                    "contract_fields",
                    (
                        "contract_no",
                        "display_contract_no",
                        "source_contract_no",
                        "name",
                        "contract_key",
                    ),
                ),
            )
            domain.extend(self._or_domain(contract_fields, self.contract_no))

        if self.keyword:
            keyword_fields = self._existing_field_paths(
                model_name,
                config.get(
                    "keyword_fields",
                    (
                        "contract_name",
                        "project_content",
                        "remark",
                        "invoice_partner_name",
                        "payer_name",
                        "receivable_item_name",
                        "payment_item_name",
                        "name",
                        "customer_name",
                        "site_name",
                        "note",
                    ),
                ),
            )
            domain.extend(self._or_domain(keyword_fields, self.keyword))

        if self.customer_name:
            customer_fields = self._existing_field_paths(
                model_name,
                config.get(
                    "customer_fields",
                    (
                        "customer_name",
                        "invoice_partner_name",
                        "payer_name",
                        "partner_id.name",
                        "customer_level_1",
                        "customer_level_2",
                        "customer_level_3",
                    ),
                ),
            )
            domain.extend(self._or_domain(customer_fields, self.customer_name))

        if self.payer_name and self._field_exists(model_name, "payer_name"):
            domain.append(("payer_name", "ilike", self.payer_name))
        if self.site_name:
            domain.extend(
                self._or_domain(
                    self._existing_field_paths(
                        model_name,
                        config.get(
                            "site_fields",
                            ("site_name", "site_id.name", "site_other_name"),
                        ),
                    ),
                    self.site_name,
                )
            )
        if self.sale_manager and self._field_exists(model_name, "sale_manager"):
            domain.append(("sale_manager", "ilike", self.sale_manager))
        if self.province_name and self._field_exists(model_name, "province_name"):
            domain.append(("province_name", "ilike", self.province_name))
        if self.group_name and self._field_exists(model_name, "group_name"):
            domain.append(("group_name", "ilike", self.group_name))
        if self.product_line and self._field_exists(model_name, "product_line"):
            domain.append(("product_line", "ilike", self.product_line))
        if self.state and self._field_exists(model_name, "state"):
            state_values = self._selection_values_for_text(model_name, "state", self.state)
            if state_values:
                domain.append(("state", "in", state_values))
            else:
                domain.append(("state", "ilike", self.state))

        amount_field = config.get("amount_field")
        if amount_field and self._field_exists(model_name, amount_field):
            if self.amount_min:
                domain.append((amount_field, ">=", self.amount_min))
            if self.amount_max:
                domain.append((amount_field, "<=", self.amount_max))

        return domain

    def _result_ids(self):
        self.ensure_one()
        if not self.result_ids_json:
            return []
        try:
            return json.loads(self.result_ids_json)
        except json.JSONDecodeError:
            return []

    def _result_domain(self):
        self.ensure_one()
        if not self.result_domain_json:
            return []
        try:
            return json.loads(self.result_domain_json)
        except json.JSONDecodeError:
            return []

    def _render_cards(self, cards):
        if not cards:
            return Markup(
                "<div style='padding:20px;border:1px dashed #d0d7e2;border-radius:12px;color:#667085;'>暂无可展示内容。</div>"
            )
        html = ["<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;'>"]
        for title, value, subtitle in cards:
            html.append(
                "<div style='border:1px solid #d9e2ef;border-radius:12px;padding:16px 18px;background:#fff;'>"
                f"<div style='font-size:13px;color:#667085;margin-bottom:8px;'>{escape(title)}</div>"
                f"<div style='font-size:28px;font-weight:700;color:#1d2939;line-height:1.2;'>{escape(value)}</div>"
                f"<div style='font-size:12px;color:#98a2b3;margin-top:8px;line-height:1.6;'>{escape(subtitle)}</div>"
                "</div>"
            )
        html.append("</div>")
        return Markup("".join(html))

    def _render_summary_table(self, title, rows):
        html = [
            "<div style='border:1px solid #d9e2ef;border-radius:12px;background:#fff;overflow:hidden;'>",
            f"<div style='padding:14px 18px;font-size:16px;font-weight:700;color:#1d2939;border-bottom:1px solid #eaecf0;'>{escape(title)}</div>",
            "<table style='width:100%;border-collapse:collapse;'>",
        ]
        for label, value in rows:
            html.append(
                "<tr>"
                f"<th style='width:25%;padding:12px 18px;text-align:left;font-size:13px;color:#475467;border-bottom:1px solid #f2f4f7;background:#fcfcfd;'>{escape(label)}</th>"
                f"<td style='padding:12px 18px;font-size:14px;color:#101828;border-bottom:1px solid #f2f4f7;'>{escape(value)}</td>"
                "</tr>"
            )
        html.append("</table></div>")
        return Markup("".join(html))

    def _render_amount_stat_table(self, title, rows, highlight=False):
        value_bg = "#8fd14f" if highlight else "#fff"
        title_align = "right" if highlight else "right"
        html = [
            "<div style='border:1px solid #1f2937;border-radius:10px;background:#fff;overflow:hidden;'>",
            f"<div style='padding:10px 14px;font-size:16px;font-weight:700;color:#111827;text-align:{title_align};background:#c7eaf1;border-bottom:1px solid #1f2937;'>"
            f"{escape(title)}</div>",
            "<table style='width:100%;border-collapse:collapse;table-layout:fixed;'>",
        ]
        for label, value in rows:
            html.append(
                "<tr>"
                f"<th style='width:74%;padding:10px 14px;text-align:right;font-size:14px;font-weight:700;color:#111827;border-right:1px solid #1f2937;border-bottom:1px solid #1f2937;background:#fff;'>{escape(label)}</th>"
                f"<td style='padding:10px 14px;text-align:right;font-size:15px;font-weight:700;color:#111827;border-bottom:1px solid #1f2937;background:{value_bg};white-space:nowrap;'>{escape(value)}</td>"
                "</tr>"
            )
        html.append("</table></div>")
        return Markup("".join(html))

    def _sales_report_contracts(self, date_from, date_to):
        domain = [
            ("entry_state", "=", "confirmed"),
            ("contract_sign_date", ">=", date_from),
            ("contract_sign_date", "<=", date_to),
        ]
        if self.sale_manager:
            domain.append(("sale_manager", "ilike", self.sale_manager))
        contracts = self.env["zfmd.contract"].search(domain)
        excluded_values = {"×", "是", "yes", "y", "true", "1"}
        return contracts.filtered(
            lambda contract: str(contract.exclude_sales_performance or "").strip().lower() not in excluded_values
        )

    def _aggregate_sales_contracts(self, contracts):
        result = {}
        for contract in contracts:
            manager = (contract.sale_manager or "未填写销售经理").strip() or "未填写销售经理"
            row = result.setdefault(
                manager,
                {
                    "count": 0,
                    "initial_fee": 0.0,
                    "service_fee": 0.0,
                    "total": 0.0,
                },
            )
            row["count"] += 1
            row["initial_fee"] += contract.initial_fee or 0.0
            row["service_fee"] += contract.service_fee or 0.0
            row["total"] += (contract.initial_fee or 0.0) + (contract.service_fee or 0.0)
        return result

    def _format_wan_amount(self, amount):
        return f"{(amount or 0.0) / 10000:,.2f}"

    def _comparison_year_values(self):
        years = []
        for item in (self.comparison_years or "").replace("，", ",").split(","):
            item = item.strip()
            if not item:
                continue
            if not item.isdigit() or len(item) != 4:
                raise UserError("同期对比年份请输入四位年份，并用逗号分隔，例如：2025,2024。")
            year = int(item)
            if year not in years:
                years.append(year)
        return years

    def _date_in_year(self, source_date, year):
        day = min(source_date.day, monthrange(year, source_date.month)[1])
        return source_date.replace(year=year, day=day)

    def _sum_period_metric(self, model_name, date_field, amount_field, date_from, date_to, extra_domain=None):
        domain = [
            ("entry_state", "=", "confirmed"),
            (date_field, ">=", date_from),
            (date_field, "<=", date_to),
        ] + list(extra_domain or [])
        if self.sale_manager and self._field_exists(model_name, "sale_manager"):
            domain.append(("sale_manager", "ilike", self.sale_manager))
        return sum(self.env[model_name].search(domain).mapped(amount_field))

    def _overdue_service_amount_at(self, cutoff):
        domain = [
            ("entry_state", "=", "confirmed"),
            ("service_end_date", "!=", False),
            ("service_end_date", "<", cutoff),
        ]
        if self.sale_manager:
            domain.append(("sale_manager", "ilike", self.sale_manager))
        services = (
            self.env["zfmd.service.record"].search(domain).filtered(lambda record: not record._is_stopped_service())
        )
        return sum(services.mapped("expected_contract_amount"))

    def _management_values(self, date_from, date_to, include_snapshot=False):
        contracts = self._sales_report_contracts(date_from, date_to)
        return {
            "contract": sum(contracts.mapped("amount_total")),
            "start": self._sum_period_metric(
                "zfmd.project.start",
                "transfer_date",
                "estimated_contract_amount",
                date_from,
                date_to,
                [("cancel_date", "=", False)],
            ),
            "service": self._overdue_service_amount_at(date_to) if include_snapshot else None,
            "invoice": self._sum_period_metric(
                "zfmd.invoice.record",
                "invoice_date",
                "invoice_amount",
                date_from,
                date_to,
                [("state", "!=", "cancel")],
            ),
            "payment": self._sum_period_metric(
                "zfmd.payment.record", "payment_date", "amount_total", date_from, date_to
            ),
        }

    def _management_report_row(self, label, values, bold=False):
        weight = "700" if bold else "500"
        cells = []
        for key in ("contract", "start", "service", "invoice", "payment"):
            value = values.get(key)
            display = "/" if value is None else self._format_wan_amount(value)
            cells.append(
                f"<td style='padding:13px 12px;text-align:right;border:1px solid #344054;font-weight:{weight};'>{escape(display)}</td>"
            )
        return (
            "<tr>"
            f"<td style='padding:13px 12px;text-align:center;border:1px solid #344054;font-weight:{weight};white-space:nowrap;'>{escape(label)}</td>"
            f"{''.join(cells)}</tr>"
        )

    def _build_management_report_html(self, date_from, date_to):
        year_start = date_to.replace(month=1, day=1)
        previous_end = date_from - timedelta(days=1)
        current_period = self._management_values(date_from, date_to)
        current_cumulative = self._management_values(year_start, date_to, include_snapshot=True)
        previous_cumulative = (
            self._management_values(year_start, previous_end, include_snapshot=True)
            if previous_end >= year_start
            else {key: 0.0 for key in ("contract", "start", "service", "invoice", "payment")}
        )

        rows = [
            self._management_report_row("上期累计", previous_cumulative, bold=True),
            self._management_report_row(
                f"{date_from.month}月{date_from.day}日至{date_to.month}月{date_to.day}日",
                current_period,
                bold=True,
            ),
        ]
        comparison_cumulative_rows = []
        for year in self._comparison_year_values():
            comparison_from = self._date_in_year(date_from, year)
            comparison_to = self._date_in_year(date_to, year)
            comparison_year_start = comparison_to.replace(month=1, day=1)
            rows.append(
                self._management_report_row(
                    f"{year}年同期",
                    self._management_values(comparison_from, comparison_to),
                )
            )
            comparison_cumulative_rows.append(
                self._management_report_row(
                    f"{year}年同期累计",
                    self._management_values(comparison_year_start, comparison_to, include_snapshot=True),
                )
            )
        rows.append(self._management_report_row(f"{date_to.year}年累计", current_cumulative, bold=True))
        rows.extend(comparison_cumulative_rows)
        return Markup(
            "<div style='border:1px solid #344054;border-radius:10px;background:#fff;overflow:hidden;'>"
            "<div style='padding:18px 16px;text-align:center;background:#f8fafc;'>"
            "<div style='font-size:24px;font-weight:700;color:#101828;'>经营管理周例会销售数据统计表（万元）</div>"
            f"<div style='margin-top:8px;font-size:13px;color:#475467;'>统计区间：{escape(fields.Date.to_string(date_from))} 至 {escape(fields.Date.to_string(date_to))}；销售合同额日期口径：合同签订日期</div>"
            "</div><div style='overflow:auto;'>"
            "<table style='width:100%;min-width:1050px;border-collapse:collapse;table-layout:fixed;'>"
            "<thead><tr style='background:#eaf4f7;'>"
            "<th style='width:180px;padding:13px;border:1px solid #344054;'>时间</th>"
            "<th style='padding:13px;border:1px solid #344054;'>销售合同额</th>"
            "<th style='padding:13px;border:1px solid #344054;'>开工申请预计合同额</th>"
            "<th style='width:250px;padding:13px;border:1px solid #344054;'>待续签预测服务项目预计合同额</th>"
            "<th style='padding:13px;border:1px solid #344054;'>开票额</th>"
            "<th style='padding:13px;border:1px solid #344054;'>回款额</th>"
            f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div></div>"
        )

    def _build_sales_report_html(self, date_from, date_to):
        period_stats = self._aggregate_sales_contracts(self._sales_report_contracts(date_from, date_to))
        year_start = date_to.replace(month=1, day=1)
        year_stats = self._aggregate_sales_contracts(self._sales_report_contracts(year_start, date_to))
        managers = sorted(
            set(period_stats) | set(year_stats),
            key=lambda manager: (-year_stats.get(manager, {}).get("total", 0.0), manager),
        )

        total_period = {"count": 0, "initial_fee": 0.0, "service_fee": 0.0, "total": 0.0}
        total_year = {"count": 0, "initial_fee": 0.0, "service_fee": 0.0, "total": 0.0}
        rows = []
        for manager in managers:
            period = period_stats.get(manager, {})
            year = year_stats.get(manager, {})
            for key in total_period:
                total_period[key] += period.get(key, 0)
                total_year[key] += year.get(key, 0)
            rows.append(
                "<tr>"
                f"<td style='padding:9px 12px;text-align:center;border:1px solid #344054;font-weight:600;white-space:pre-line;'>{escape(manager)}</td>"
                f"<td style='padding:9px 12px;text-align:right;border:1px solid #344054;'>{period.get('count', 0)}</td>"
                f"<td style='padding:9px 12px;text-align:right;border:1px solid #344054;'>{self._format_wan_amount(period.get('initial_fee', 0.0))}</td>"
                f"<td style='padding:9px 12px;text-align:right;border:1px solid #344054;'>{self._format_wan_amount(period.get('service_fee', 0.0))}</td>"
                f"<td style='padding:9px 12px;text-align:right;border:1px solid #344054;font-weight:700;'>{self._format_wan_amount(period.get('total', 0.0))}</td>"
                f"<td style='padding:9px 12px;text-align:right;border:1px solid #344054;'>{year.get('count', 0)}</td>"
                f"<td style='padding:9px 12px;text-align:right;border:1px solid #344054;'>{self._format_wan_amount(year.get('initial_fee', 0.0))}</td>"
                f"<td style='padding:9px 12px;text-align:right;border:1px solid #344054;'>{self._format_wan_amount(year.get('service_fee', 0.0))}</td>"
                f"<td style='padding:9px 12px;text-align:right;border:1px solid #344054;font-weight:700;'>{self._format_wan_amount(year.get('total', 0.0))}</td>"
                "</tr>"
            )

        total_cells = (
            f"<td style='padding:9px 12px;text-align:center;border:1px solid #344054;font-weight:700;'>合计</td>"
            f"<td style='padding:9px 12px;text-align:right;border:1px solid #344054;font-weight:700;'>{total_period['count']}</td>"
            f"<td style='padding:9px 12px;text-align:right;border:1px solid #344054;font-weight:700;'>{self._format_wan_amount(total_period['initial_fee'])}</td>"
            f"<td style='padding:9px 12px;text-align:right;border:1px solid #344054;font-weight:700;'>{self._format_wan_amount(total_period['service_fee'])}</td>"
            f"<td style='padding:9px 12px;text-align:right;border:1px solid #344054;font-weight:700;'>{self._format_wan_amount(total_period['total'])}</td>"
            f"<td style='padding:9px 12px;text-align:right;border:1px solid #344054;font-weight:700;'>{total_year['count']}</td>"
            f"<td style='padding:9px 12px;text-align:right;border:1px solid #344054;font-weight:700;'>{self._format_wan_amount(total_year['initial_fee'])}</td>"
            f"<td style='padding:9px 12px;text-align:right;border:1px solid #344054;font-weight:700;'>{self._format_wan_amount(total_year['service_fee'])}</td>"
            f"<td style='padding:9px 12px;text-align:right;border:1px solid #344054;font-weight:700;'>{self._format_wan_amount(total_year['total'])}</td>"
        )
        period_label = f"{fields.Date.to_string(date_from)} 至 {fields.Date.to_string(date_to)}"
        year_label = f"{date_to.year}年1月1日 至 {fields.Date.to_string(date_to)}"
        return Markup(
            "<div style='border:1px solid #344054;border-radius:10px;background:#fff;overflow:hidden;'>"
            "<div style='padding:18px 16px;text-align:center;border-bottom:1px solid #344054;background:#f8fafc;'>"
            "<div style='font-size:24px;font-weight:700;color:#101828;'>销售合同额统计表</div>"
            f"<div style='margin-top:8px;font-size:13px;color:#475467;'>统计区间：{escape(period_label)}；年度累计：{escape(year_label)}；日期口径：合同签订日期；金额单位：万元</div>"
            "</div>"
            "<div style='overflow:auto;'>"
            "<table style='width:100%;min-width:1180px;border-collapse:collapse;table-layout:fixed;'>"
            "<thead>"
            "<tr style='background:#eaf4f7;'>"
            "<th rowspan='2' style='width:140px;padding:10px;border:1px solid #344054;text-align:center;'>销售经理</th>"
            "<th colspan='4' style='padding:10px;border:1px solid #344054;text-align:center;'>所选统计区间</th>"
            "<th colspan='4' style='padding:10px;border:1px solid #344054;text-align:center;'>当年累计至统计结束日期</th>"
            "</tr>"
            "<tr style='background:#f4f8fa;'>"
            "<th style='padding:10px;border:1px solid #344054;'>新增预测项目个数</th>"
            "<th style='padding:10px;border:1px solid #344054;'>初装</th>"
            "<th style='padding:10px;border:1px solid #344054;'>预测服务</th>"
            "<th style='padding:10px;border:1px solid #344054;'>合计</th>"
            "<th style='padding:10px;border:1px solid #344054;'>累计新增预测项目个数</th>"
            "<th style='padding:10px;border:1px solid #344054;'>累计初装</th>"
            "<th style='padding:10px;border:1px solid #344054;'>累计预测服务</th>"
            "<th style='padding:10px;border:1px solid #344054;'>累计合计</th>"
            "</tr>"
            "</thead>"
            f"<tbody>{''.join(rows)}<tr style='background:#f8fafc;'>{total_cells}</tr></tbody>"
            "</table>"
            "</div>"
            "</div>"
        )

    def _sum_records(self, model_name, field_name, domain=None):
        if not self._field_exists(model_name, field_name):
            return 0.0
        domain = list(domain or [])
        if self._field_exists(model_name, "entry_state"):
            domain.append(("entry_state", "=", "confirmed"))
        return sum(self.env[model_name].search(domain).mapped(field_name))

    def _invoice_status_bucket(self, invoice_status):
        text = str(invoice_status or "").strip()
        if not text:
            return "none"
        if "部分" in text:
            return "partial"
        if "未开" in text:
            return "none"
        if "已开" in text or "全额" in text:
            return "fully"
        return "none"

    def _build_progress_receivable_stats(self):
        project_model = self.env["zfmd.project.management"]
        project_domain = (
            [("entry_state", "=", "confirmed")] if self._field_exists(project_model._name, "entry_state") else []
        )
        projects = project_model.search(project_domain + [("contract_match_state", "=", "matched")])
        progress_amounts = {"fully": 0.0, "partial": 0.0, "none": 0.0}
        for project in projects:
            bucket = self._invoice_status_bucket(project.invoice_status)
            progress_amounts[bucket] += max(project.actual_progress_receivable_amount or 0.0, 0.0)

        start_domain = [
            ("contract_match_state", "=", "empty"),
            ("cancel_date", "=", False),
        ]
        service_domain = [("is_overdue", "=", True)]
        return [
            (
                "①有合同已开具全额发票的实际进度应收款",
                progress_amounts["fully"],
            ),
            (
                "②有合同已开具部分发票的实际进度应收款",
                progress_amounts["partial"],
            ),
            (
                "③有合同未开具发票的实际进度应收款",
                progress_amounts["none"],
            ),
            (
                "④无合同已开工项目的预计进度应收款",
                self._sum_records("zfmd.project.start", "estimated_contract_amount", start_domain),
            ),
            (
                "⑤无服务合同项目的预计合同额",
                self._sum_records("zfmd.service.record", "expected_contract_amount", service_domain),
            ),
        ]

    def _build_other_data_stats(self):
        invoiced_receivable = self._sum_records("zfmd.project.management", "invoiced_receivable_amount")
        invoiced_bad_debt = self._sum_records("zfmd.project.management", "invoiced_bad_debt_amount")
        total_bad_debt = self._sum_records("zfmd.project.management", "bad_debt_amount")
        return [
            ("已开票总应收款", invoiced_receivable),
            ("已开票坏账金额", invoiced_bad_debt),
            ("已开票总应收款-已开票坏账", invoiced_receivable - invoiced_bad_debt),
            ("总坏账", total_bad_debt),
        ]

    def _build_overview_business_stats_html(self):
        progress_rows = [
            (label, self._format_amount(amount)) for label, amount in self._build_progress_receivable_stats()
        ]
        other_rows = [(label, self._format_amount(amount)) for label, amount in self._build_other_data_stats()]
        return Markup(
            "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(480px,1fr));gap:18px;margin-top:18px;'>"
            f"{self._render_amount_stat_table('进度应收款统计（元）', progress_rows, highlight=True)}"
            f"{self._render_amount_stat_table('其他数据统计（元）', other_rows)}"
            "</div>"
        )

    def _build_condition_hint_html(self):
        self.ensure_one()
        config = self._get_config()
        hints = [
            f"当前查询对象：{config['label']}",
            "建议先确定时间范围，再按合同、客户、场站、销售经理等维度逐步缩小范围。",
        ]
        if self.query_target == "contract":
            hints.append("适合统一查询合同数量、合同总额，以及按客户、场站、销售经理、省区、集团、产品线等维度筛选。")
        elif self.query_target == "payment_record":
            hints.append("适合统一查询回款总额、付款单位、销售经理、场站和合同号的回款明细。")
        elif self.query_target == "invoice_record":
            hints.append("适合统一查询开票金额、承诺回款时间、实际回款情况和应收风险。")
        elif self.query_target == "receivable_plan":
            hints.append("适合统一查询应收时间、承诺回款时间、实际回款时间和异常项。")
        else:
            hints.append("适合按合同编号、场站、状态、时间范围等条件进行追踪。")

        html = [
            "<div style='border:1px solid #d9e2ef;border-radius:12px;background:#fff;padding:16px 18px;'>",
            "<div style='font-size:16px;font-weight:700;color:#1d2939;margin-bottom:10px;'>条件联动提示</div>",
            "<ul style='margin:0;padding-left:18px;color:#344054;line-height:1.8;'>",
        ]
        for hint in hints:
            html.append(f"<li>{escape(hint)}</li>")
        html.append("</ul></div>")
        return Markup("".join(html))

    def _build_result_overview_html(self, records):
        self.ensure_one()
        amount_label = self.result_amount_label or "无金额汇总"
        cards = [
            ("结果对象", self.result_object_label or "-", "当前查询对应的业务台账"),
            ("匹配记录数", str(self.result_count or 0), "符合当前筛选条件的记录数"),
            ("金额口径", amount_label, "本次汇总采用的金额字段"),
            (
                "汇总金额",
                self._format_amount(self.result_amount_total or 0.0),
                "按当前结果汇总",
            ),
        ]
        return self._render_cards(cards)

    def _build_result_summary_html(self):
        self.ensure_one()
        rows = [
            ("查询对象", self.result_object_label or "-"),
            (
                "最近查询时间",
                self.result_last_query_at and format_datetime(self.env, self.result_last_query_at) or "-",
            ),
            ("匹配记录数", str(self.result_count or 0)),
            ("金额口径", self.result_amount_label or "-"),
            ("汇总金额", self._format_amount(self.result_amount_total or 0.0)),
        ]
        return self._render_summary_table("结果摘要", rows)

    def _build_preview_html(self, records):
        self.ensure_one()
        config = self._get_config()
        preview_fields = config.get("preview_fields", [])
        if not records:
            return Markup(
                "<div style='padding:20px;border:1px dashed #d0d7e2;border-radius:12px;color:#667085;'>当前条件下暂无结果预览。</div>"
            )

        colgroup = []
        for idx, (_field_name, label) in enumerate(preview_fields):
            if idx == 0:
                width = "240px"
            elif label in ("客户", "开票客户", "付款单位"):
                width = "260px"
            elif label in ("场站",):
                width = "180px"
            elif "金额" in label:
                width = "160px"
            elif label in ("状态", "是否超期"):
                width = "120px"
            else:
                width = "140px"
            colgroup.append(f"<col style='width:{width};'>")

        header = "".join(
            f"<th style='padding:12px 14px;text-align:left;font-size:13px;font-weight:700;color:#344054;border-bottom:1px solid #eaecf0;background:#f8fafc;white-space:nowrap;'>{escape(label)}</th>"
            for _, label in preview_fields
        )
        rows = []
        for record in records[:10]:
            cols = []
            for field_name, label in preview_fields:
                try:
                    raw = record[field_name]
                except KeyError:
                    raw = False
                value = self._format_value(record, field_name, raw)
                align = "right" if "金额" in label else "left"
                cols.append(
                    f"<td style='padding:12px 14px;font-size:13px;color:#101828;border-bottom:1px solid #f2f4f7;text-align:{align};vertical-align:top;line-height:1.7;word-break:break-word;white-space:normal;'>{escape(value)}</td>"
                )
            rows.append("<tr>" + "".join(cols) + "</tr>")
        more = ""
        if len(records) > 10:
            more = (
                f"<div style='padding:12px 14px;font-size:12px;color:#667085;border-top:1px solid #eaecf0;background:#fcfcfd;'>"
                f"当前仅预览前 10 条，共 {len(records)} 条。需要查看全部结果，请点击“查看结果明细”。"
                "</div>"
            )
        return Markup(
            "<div style='border:1px solid #d9e2ef;border-radius:12px;background:#fff;overflow:hidden;'>"
            "<div style='padding:14px 18px;font-size:16px;font-weight:700;color:#1d2939;border-bottom:1px solid #eaecf0;'>结果预览</div>"
            "<div style='overflow:auto;padding:0 0 0 0;'>"
            "<table style='width:100%;min-width:1200px;border-collapse:collapse;table-layout:fixed;'>"
            f"<colgroup>{''.join(colgroup)}</colgroup>"
            f"<thead><tr>{header}</tr></thead>"
            f"<tbody>{''.join(rows)}</tbody>"
            "</table>"
            "</div>"
            f"{more}"
            "</div>"
        )

    def _build_detail_scope_html(self):
        return Markup(
            "<div style='border:1px solid #d9e2ef;border-radius:12px;background:#fff;padding:16px 18px;'>"
            "<div style='font-size:16px;font-weight:700;color:#1d2939;margin-bottom:8px;'>结果明细跳转</div>"
            "<div style='font-size:13px;color:#475467;line-height:1.8;'>点击后会跳转到对应台账列表，并自动带入本次查询结果的记录范围，适合继续做明细核对、补充筛选和批量导出。</div>"
            "</div>"
        )

    def _build_export_scope_html(self):
        return Markup(
            "<div style='border:1px solid #d9e2ef;border-radius:12px;background:#fff;padding:16px 18px;'>"
            "<div style='font-size:16px;font-weight:700;color:#1d2939;margin-bottom:8px;'>导出当前结果</div>"
            "<div style='font-size:13px;color:#475467;line-height:1.8;'>导出的 Excel 仅包含当前查询结果。建议先在结果预览中确认范围，再导出留档、核对或发送给业务人员。</div>"
            "</div>"
        )

    def _build_overview_metrics_html(self):
        self.ensure_one()
        contract_model = self.env["zfmd.contract"]
        project_start_model = self.env["zfmd.project.start"]
        service_model = self.env["zfmd.service.record"]

        no_contract_start_count = project_start_model.search_count(
            [
                ("entry_state", "=", "confirmed"),
                ("contract_match_state", "=", "empty"),
                ("cancel_date", "=", False),
            ]
        )
        overdue_service_count = service_model.search_count(
            [("entry_state", "=", "confirmed"), ("is_overdue", "=", True)]
        )

        cards = [
            (
                "合同数量",
                str(contract_model.search_count([("entry_state", "=", "confirmed")])),
                "当前已确认合同台账总数",
            ),
            (
                "无合同开工申请数量",
                str(no_contract_start_count),
                "无合同号且未取消的有效开工申请",
            ),
            ("服务超期记录", str(overdue_service_count), "按服务合同到期时间判断"),
        ]
        return Markup(f"{self._render_cards(cards)}{self._build_overview_business_stats_html()}")

    def _build_overview_warning_html(self):
        self.ensure_one()
        event_model = self.env["zfmd.warning.event"]

        def _get_href(xmlid):
            try:
                return f"/web#action={self.env.ref(xmlid).id}"
            except Exception:
                return "#"

        href_due = _get_href("zfmd_pm.action_zfmd_warning_event_due")
        href_balance = _get_href("zfmd_pm.action_zfmd_warning_event_balance")
        href_aging = _get_href("zfmd_pm.action_zfmd_warning_event_aging")
        href_danger = _get_href("zfmd_pm.action_zfmd_warning_event_danger")

        def _query(rule_type):
            evts = event_model.search([("rule_type", "=", rule_type), ("state", "in", ACTIVE_WARNING_STATES)])
            return len(evts), sum(evts.mapped("receivable_balance"))

        due_count, due_amount = _query("invoice_payment_due")
        balance_count, balance_amount = _query("invoice_receivable_balance")
        aging_count, aging_amount = _query("invoice_aging")
        danger_count = event_model.search_count(
            [("warning_level", "=", "danger"), ("state", "in", ACTIVE_WARNING_STATES)]
        )
        total_active = due_count + balance_count + aging_count

        level_styles = {
            "danger": ("#dc2626", "#fef2f2"),
            "warning": ("#d97706", "#fffbeb"),
            "aging": ("#ea580c", "#fff7ed"),
            "info": ("#0284c7", "#f0f9ff"),
        }

        cards_data = [
            (
                "回款逾期预警",
                due_count,
                self._format_amount(due_amount) + " 元",
                "danger",
                href_due,
            ),
            (
                "应收余额预警",
                balance_count,
                self._format_amount(balance_amount) + " 元",
                "info",
                href_balance,
            ),
            (
                "账龄超期预警",
                aging_count,
                self._format_amount(aging_amount) + " 元",
                "aging",
                href_aging,
            ),
            ("严重预警（danger）", danger_count, "点击查看明细", "danger", href_danger),
        ]

        html = ["<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;'>"]
        for title, count, subtitle, lk, href in cards_data:
            color, bg = level_styles[lk]
            html.append(
                f"<a href='{href}' style='text-decoration:none;display:block;"
                f"border:2px solid {color}33;border-radius:12px;padding:16px 18px;"
                f"background:{bg};cursor:pointer;transition:border-color 0.15s;' "
                f"onmouseover=\"this.style.borderColor='{color}'\" "
                f"onmouseout=\"this.style.borderColor='{color}33'\">"
                f"<div style='font-size:13px;color:#667085;margin-bottom:8px;'>{escape(title)}</div>"
                f"<div style='font-size:28px;font-weight:700;color:{color};line-height:1.2;'>{escape(str(count))}</div>"
                f"<div style='font-size:12px;color:#98a2b3;margin-top:8px;line-height:1.6;'>{escape(subtitle)}</div>"
                "</a>"
            )
        html.append("</div>")

        if total_active == 0:
            html.append(
                "<div style='margin-top:12px;padding:12px 16px;"
                "border:1px dashed #d0d7e2;border-radius:8px;color:#667085;font-size:13px;'>"
                "当前暂无活跃预警事件。请点击上方【重新计算预警】以更新预警数据。"
                "</div>"
            )

        return Markup("".join(html))

    def _build_overview_shortcuts_html(self):
        shortcuts = [
            (
                "统一查询中心",
                "跨台账统一筛选、预览、导出",
                "适合快速查问题",
                "zfmd_pm.action_zfmd_dashboard_query",
            ),
            (
                "合同台账",
                "查看合同主档与执行情况",
                "适合追合同主线",
                "zfmd_pm.action_zfmd_contract",
            ),
            (
                "回款登记",
                "查看回款轨迹、付款单位与对账明细",
                "适合财务和提成核算",
                "zfmd_pm.action_zfmd_payment_record",
            ),
            (
                "应收计划",
                "查看应收时间、承诺回款与异常项",
                "适合应收预警",
                "zfmd_pm.action_zfmd_receivable_plan",
            ),
        ]
        html = ["<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;'>"]
        for title, desc, subtitle, xmlid in shortcuts:
            try:
                action_id = self.env.ref(xmlid).id
                href = f"/web#action={action_id}"
            except Exception:
                href = "#"
            html.append(
                f"<a href='{href}' style='text-decoration:none;display:block;"
                "border:1px solid #d9e2ef;border-radius:12px;padding:16px 18px;"
                "background:#fff;cursor:pointer;transition:border-color 0.15s,box-shadow 0.15s;' "
                "onmouseover=\"this.style.borderColor='#7c3aed';this.style.boxShadow='0 2px 8px rgba(124,58,237,0.12)'\" "
                "onmouseout=\"this.style.borderColor='#d9e2ef';this.style.boxShadow='none'\">"
                f"<div style='font-size:13px;color:#667085;margin-bottom:8px;'>{escape(title)}</div>"
                f"<div style='font-size:16px;font-weight:700;color:#1d2939;line-height:1.4;margin-bottom:6px;'>{escape(desc)}</div>"
                f"<div style='font-size:12px;color:#98a2b3;line-height:1.6;'>{escape(subtitle)}</div>"
                "</a>"
            )
        html.append("</div>")
        return Markup("".join(html))

    def _refresh_overview_blocks(self):
        for record in self:
            record.overview_metrics_html = record._build_overview_metrics_html()
            record.overview_warning_html = record._build_overview_warning_html()
            record.overview_shortcuts_html = record._build_overview_shortcuts_html()

    def _sync_dashboard_business_state(self):
        self.env["zfmd.invoice.record"].sudo().search([]).action_recompute_state_from_payment()

    def action_generate_management_report(self):
        self.ensure_one()
        if not self.date_from or not self.date_to:
            raise UserError("请先填写经营统计的开始日期和结束日期。")
        date_from = fields.Date.to_date(self.date_from)
        date_to = fields.Date.to_date(self.date_to)
        if date_from > date_to:
            raise UserError("经营统计的开始日期不能晚于结束日期。")
        self.management_report_html = self._build_management_report_html(date_from, date_to)
        return True

    def action_generate_sales_report(self):
        self.ensure_one()
        if not self.date_from or not self.date_to:
            raise UserError("请先填写销售统计的开始日期和结束日期。")
        date_from = fields.Date.to_date(self.date_from)
        date_to = fields.Date.to_date(self.date_to)
        if date_from > date_to:
            raise UserError("销售统计的开始日期不能晚于结束日期。")
        self.sales_report_html = self._build_sales_report_html(date_from, date_to)
        return True

    def _global_query_domain(self, model_name, config):
        domain = [("entry_state", "=", "confirmed")] if self._field_exists(model_name, "entry_state") else []
        date_field = config.get("date_field")
        if date_field:
            if self.date_from:
                domain.append((date_field, ">=", self.date_from))
            if self.date_to:
                domain.append((date_field, "<=", self.date_to))
        if self.keyword:
            domain.extend(
                self._or_domain(
                    self._existing_field_paths(model_name, config.get("keyword_fields", ())),
                    self.keyword,
                )
            )
        if self.contract_no:
            domain.extend(
                self._or_domain(
                    self._existing_field_paths(model_name, config.get("contract_fields", ())),
                    self.contract_no,
                )
            )
        if self.customer_name:
            domain.extend(
                self._or_domain(
                    self._existing_field_paths(model_name, config.get("customer_fields", ())),
                    self.customer_name,
                )
            )
        for value, fields_to_try in (
            (self.site_name, config.get("site_fields", ())),
            (self.sale_manager, ("sale_manager", "contract_sale_manager")),
            (self.province_name, ("province_name",)),
            (self.group_name, ("group_name",)),
            (self.product_line, ("product_line",)),
        ):
            if value:
                domain.extend(self._or_domain(self._existing_field_paths(model_name, fields_to_try), value))
        amount_field = config.get("amount_field")
        if amount_field:
            if self.amount_min:
                domain.append((amount_field, ">=", self.amount_min))
            if self.amount_max:
                domain.append((amount_field, "<=", self.amount_max))
        return domain

    def action_apply_global_query(self):
        self.ensure_one()
        rows = []
        total_count = 0
        for config in self._target_configs().values():
            model_name = config["model"]
            records = self.env[model_name].search(self._global_query_domain(model_name, config))
            amount_field = config.get("amount_field")
            amount = sum(records.mapped(amount_field)) if amount_field else 0.0
            total_count += len(records)
            rows.append((config["label"], len(records), config.get("amount_label") or "-", amount))
        body = "".join(
            "<tr>"
            f"<td style='padding:11px 14px;border-bottom:1px solid #eaecf0;font-weight:600;'>{escape(label)}</td>"
            f"<td style='padding:11px 14px;border-bottom:1px solid #eaecf0;text-align:right;'>{count}</td>"
            f"<td style='padding:11px 14px;border-bottom:1px solid #eaecf0;'>{escape(amount_label)}</td>"
            f"<td style='padding:11px 14px;border-bottom:1px solid #eaecf0;text-align:right;'>{escape(self._format_amount(amount))}</td>"
            "</tr>"
            for label, count, amount_label, amount in rows
        )
        self.global_result_html = Markup(
            "<div style='border:1px solid #d9e2ef;border-radius:10px;background:#fff;overflow:hidden;'>"
            f"<div style='padding:14px 18px;font-size:16px;font-weight:700;background:#f8fafc;'>全局筛选结果，共匹配 {total_count} 条业务记录</div>"
            "<table style='width:100%;border-collapse:collapse;'>"
            "<thead><tr><th style='padding:11px 14px;text-align:left;'>业务模块</th><th style='padding:11px 14px;text-align:right;'>记录数</th><th style='padding:11px 14px;text-align:left;'>金额口径</th><th style='padding:11px 14px;text-align:right;'>金额合计（元）</th></tr></thead>"
            f"<tbody>{body}</tbody></table></div>"
        )
        return True

    def _template_filter_values(self):
        return {
            field_name: self[field_name]
            for field_name in (
                "date_from",
                "date_to",
                "keyword",
                "contract_no",
                "customer_name",
                "site_name",
                "sale_manager",
                "province_name",
                "group_name",
                "product_line",
                "amount_min",
                "amount_max",
                "comparison_years",
            )
        }

    def action_save_global_template(self):
        self.ensure_one()
        if not self.template_name:
            raise UserError("请先填写统计模板名称。")
        values = {
            "name": self.template_name,
            "filter_json": json.dumps(self._template_filter_values(), default=str),
        }
        template = self.selected_template_id
        if template:
            template.write(values)
        else:
            template = self.env["zfmd.dashboard.template"].create(values)
            self.selected_template_id = template
        return True

    def action_load_global_template(self):
        self.ensure_one()
        if not self.selected_template_id:
            raise UserError("请先选择一个已保存统计模板。")
        values = json.loads(self.selected_template_id.filter_json or "{}")
        allowed = self._template_filter_values().keys()
        self.write({key: value or False for key, value in values.items() if key in allowed})
        self.template_name = self.selected_template_id.name
        return True

    def action_apply_query(self):
        for record in self:
            config = record._get_config()
            model = self.env[config["model"]]
            domain = record._build_query_domain()
            records = model.search(domain)
            amount_field = config.get("amount_field")
            amount_total = 0.0
            if amount_field and record._field_exists(config["model"], amount_field):
                amount_total = sum(records.mapped(amount_field))

            record.write(
                {
                    "result_object_label": config["label"],
                    "result_count": len(records),
                    "result_amount_label": config.get("amount_label", ""),
                    "result_amount_total": amount_total,
                    "result_last_query_at": fields.Datetime.now(),
                    "result_ids_json": json.dumps(records.ids),
                    "result_domain_json": json.dumps(domain),
                    "condition_hint_html": record._build_condition_hint_html(),
                    "result_overview_html": record._build_result_overview_html(records),
                    "result_summary_html": record._build_result_summary_html(),
                    "result_preview_html": record._build_preview_html(records),
                    "detail_scope_html": record._build_detail_scope_html(),
                    "export_scope_html": record._build_export_scope_html(),
                }
            )
        return True

    def action_reset_query(self):
        self.write(
            {
                "query_target": "contract",
                "date_from": False,
                "date_to": False,
                "keyword": False,
                "contract_no": False,
                "customer_name": False,
                "payer_name": False,
                "site_name": False,
                "sale_manager": False,
                "province_name": False,
                "group_name": False,
                "product_line": False,
                "state": False,
                "amount_min": 0.0,
                "amount_max": 0.0,
                "result_object_label": False,
                "result_count": 0,
                "result_amount_label": False,
                "result_amount_total": 0.0,
                "result_last_query_at": False,
                "result_ids_json": False,
                "result_domain_json": False,
                "condition_hint_html": False,
                "result_overview_html": False,
                "result_summary_html": False,
                "result_preview_html": False,
                "detail_scope_html": False,
                "export_scope_html": False,
                "sales_report_html": False,
                "management_report_html": False,
                "global_result_html": False,
            }
        )
        return True

    def action_open_result_list(self):
        self.ensure_one()
        action = self.env.ref(self._get_config()["list_action"]).sudo().read()[0]
        action["domain"] = self._result_domain() or [("id", "in", self._result_ids())]
        return action

    def action_recompute_warnings(self):
        self.ensure_one()
        self.env["zfmd.warning.event"].recompute_warning_events()
        self.with_context(_skip_overview_refresh=True)._refresh_overview_blocks()
        return True

    def action_refresh_overview(self):
        self.ensure_one()
        self.env["zfmd.warning.event"].recompute_warning_events()
        self.with_context(_skip_overview_refresh=True)._refresh_overview_blocks()
        return True

    def action_export_result_excel(self):
        self.ensure_one()
        result_ids = self._result_ids()
        result_domain = self._result_domain()
        if not result_ids and not result_domain:
            return False
        model_name = self._get_config()["model"]
        if result_domain:
            url = f"/zfmd_pm/export_xlsx?model={model_name}&domain={quote(json.dumps(result_domain))}"
        else:
            url = f"/zfmd_pm/export_xlsx?model={model_name}&ids={','.join(map(str, result_ids))}"
        return {
            "type": "ir.actions.act_url",
            "url": url,
            "target": "download",
        }

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        overview = records.filtered(lambda r: r.page_mode == "overview")
        if overview:
            overview.with_context(_skip_overview_refresh=True)._refresh_overview_blocks()
        return records

    def write(self, vals):
        if {"date_from", "date_to", "comparison_years", "sale_manager"} & set(vals):
            vals = dict(vals)
            vals.setdefault("sales_report_html", False)
            vals.setdefault("management_report_html", False)
        result = super().write(vals)
        if not self.env.context.get("_skip_overview_refresh"):
            overview = self.filtered(lambda r: r.page_mode == "overview")
            if overview:
                overview.with_context(_skip_overview_refresh=True)._refresh_overview_blocks()
        return result


class ZfmdDashboardTemplate(models.Model):
    _name = "zfmd.dashboard.template"
    _description = "统一查询统计模板"
    _order = "name, id"

    name = fields.Char(string="模板名称", required=True)
    filter_json = fields.Text(string="筛选条件 JSON", required=True, default="{}")
    owner_id = fields.Many2one("res.users", string="创建人", default=lambda self: self.env.user, required=True)

import json

from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.tools import format_datetime


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

    show_customer_filter = fields.Boolean(compute="_compute_filter_visibility", string="显示客户过滤")
    show_payer_filter = fields.Boolean(compute="_compute_filter_visibility", string="显示付款单位过滤")
    show_state_filter = fields.Boolean(compute="_compute_filter_visibility", string="显示状态过滤")

    result_object_label = fields.Char(string="结果对象")
    result_count = fields.Integer(string="匹配记录数")
    result_amount_label = fields.Char(string="金额口径")
    result_amount_total = fields.Float(string="汇总金额")
    result_last_query_at = fields.Datetime(string="最近查询时间")
    result_ids_json = fields.Text(string="结果ID JSON")

    condition_hint_html = fields.Html(string="条件提示", sanitize=False)
    result_overview_html = fields.Html(string="结果概览", sanitize=False)
    result_summary_html = fields.Html(string="结果摘要", sanitize=False)
    result_preview_html = fields.Html(string="结果预览", sanitize=False)
    detail_scope_html = fields.Html(string="明细说明", sanitize=False)
    export_scope_html = fields.Html(string="导出说明", sanitize=False)
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
                "date_field": "contract_date",
                "amount_field": "amount_total",
                "amount_label": "合同总额（元）",
                "list_action": "zfmd_pm.action_zfmd_contract",
                "preview_fields": [
                    ("contract_no", "合同编号"),
                    ("customer_name", "客户"),
                    ("site_name", "场站"),
                    ("sale_manager", "销售经理"),
                    ("amount_total", "合同总额（元）"),
                    ("state", "状态"),
                ],
            },
            "project_start": {
                "label": "开工申请",
                "model": "zfmd.project.start",
                "date_field": "flow_date",
                "amount_field": "actual_contract_amount",
                "amount_label": "实际合同金额（元）",
                "list_action": "zfmd_pm.action_zfmd_project_start",
                "preview_fields": [
                    ("name", "开工申请号"),
                    ("display_contract_no", "合同编号"),
                    ("customer_name", "客户"),
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
                "preview_fields": [
                    ("name", "服务记录号"),
                    ("display_contract_no", "合同编号"),
                    ("site_name", "场站"),
                    ("sale_manager", "销售经理"),
                    ("service_expire_date", "服务到期时间"),
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
                "preview_fields": [
                    ("display_contract_no", "合同编号"),
                    ("receivable_item_name", "应收款项名称"),
                    ("receivable_date", "应收日期"),
                    ("sale_manager", "销售经理"),
                    ("receivable_amount", "应收金额（元）"),
                    ("state", "状态"),
                ],
            },
        }

    def _get_config(self):
        self.ensure_one()
        return self._target_configs()[self.query_target]

    def _field_exists(self, model_name, field_name):
        return field_name in self.env[model_name]._fields

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

    def _build_query_domain(self):
        self.ensure_one()
        config = self._get_config()
        model_name = config["model"]
        domain = []

        date_field = config.get("date_field")
        if date_field and self._field_exists(model_name, date_field):
            if self.date_from:
                domain.append((date_field, ">=", self.date_from))
            if self.date_to:
                domain.append((date_field, "<=", self.date_to))

        if self.contract_no:
            contract_fields = []
            for field_name in ("contract_no", "display_contract_no", "source_contract_no"):
                if self._field_exists(model_name, field_name):
                    contract_fields.append(field_name)
            domain.extend(self._or_domain(contract_fields, self.contract_no))

        keyword_fields = []
        for field_name in (
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
        ):
            if self._field_exists(model_name, field_name):
                keyword_fields.append(field_name)
        if self.keyword:
            domain.extend(self._or_domain(keyword_fields, self.keyword))

        if self.customer_name:
            customer_fields = []
            for field_name in ("customer_name", "invoice_partner_name", "payer_name"):
                if self._field_exists(model_name, field_name):
                    customer_fields.append(field_name)
            domain.extend(self._or_domain(customer_fields, self.customer_name))

        if self.payer_name and self._field_exists(model_name, "payer_name"):
            domain.append(("payer_name", "ilike", self.payer_name))
        if self.site_name and self._field_exists(model_name, "site_name"):
            domain.append(("site_name", "ilike", self.site_name))
        if self.sale_manager and self._field_exists(model_name, "sale_manager"):
            domain.append(("sale_manager", "ilike", self.sale_manager))
        if self.province_name and self._field_exists(model_name, "province_name"):
            domain.append(("province_name", "ilike", self.province_name))
        if self.group_name and self._field_exists(model_name, "group_name"):
            domain.append(("group_name", "ilike", self.group_name))
        if self.product_line and self._field_exists(model_name, "product_line"):
            domain.append(("product_line", "ilike", self.product_line))
        if self.state and self._field_exists(model_name, "state"):
            domain.append(("state", "ilike", self.state))

        return domain

    def _result_ids(self):
        self.ensure_one()
        if not self.result_ids_json:
            return []
        try:
            return json.loads(self.result_ids_json)
        except json.JSONDecodeError:
            return []

    def _render_cards(self, cards):
        if not cards:
            return Markup(
                "<div style='padding:20px;border:1px dashed #d0d7e2;border-radius:12px;color:#667085;'>暂无可展示内容。</div>"
            )
        html = [
            "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;'>"
        ]
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
                f"<th style='width:220px;padding:12px 18px;text-align:left;font-size:13px;color:#475467;border-bottom:1px solid #f2f4f7;background:#fcfcfd;'>{escape(label)}</th>"
                f"<td style='padding:12px 18px;font-size:14px;color:#101828;border-bottom:1px solid #f2f4f7;'>{escape(value)}</td>"
                "</tr>"
            )
        html.append("</table></div>")
        return Markup("".join(html))

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
            ("汇总金额", self._format_amount(self.result_amount_total or 0.0), "按当前结果汇总"),
        ]
        return self._render_cards(cards)

    def _build_result_summary_html(self):
        self.ensure_one()
        rows = [
            ("查询对象", self.result_object_label or "-"),
            ("最近查询时间", self.result_last_query_at and format_datetime(self.env, self.result_last_query_at) or "-"),
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
                value = self._format_value(record, field_name, record[field_name])
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
        invoice_model = self.env["zfmd.invoice.record"]
        payment_model = self.env["zfmd.payment.record"]
        receivable_model = self.env["zfmd.receivable.plan"]
        cards = [
            ("合同数量", str(contract_model.search_count([])), "当前合同台账总数"),
            ("开票总额", self._format_amount(sum(invoice_model.search([]).mapped("invoice_amount"))), "按开票登记汇总"),
            ("回款总额", self._format_amount(sum(payment_model.search([]).mapped("amount_total"))), "按回款登记汇总"),
            ("应收总额", self._format_amount(sum(receivable_model.search([]).mapped("receivable_amount"))), "按应收计划汇总"),
        ]
        return self._render_cards(cards)

    def _build_overview_warning_html(self):
        self.ensure_one()
        invoice_model = self.env["zfmd.invoice.record"]
        receivable_model = self.env["zfmd.receivable.plan"]
        service_model = self.env["zfmd.service.record"]
        cards = [
            ("已开票未回款", str(invoice_model.search_count([("state", "=", "unpaid")])), "开票登记"),
            ("已到期应收", str(receivable_model.search_count([("state", "=", "due")])), "应收计划"),
            ("已超期服务", str(service_model.search_count([("is_overdue", "=", True)])), "服务记录"),
        ]
        return self._render_cards(cards)

    def _build_overview_shortcuts_html(self):
        cards = [
            ("统一查询中心", "跨台账统一筛选、预览、导出", "适合快速查问题"),
            ("合同台账", "查看合同主档与执行情况", "适合追合同主线"),
            ("回款登记", "查看回款轨迹、付款单位与对账明细", "适合财务和提成核算"),
            ("应收计划", "查看应收时间、承诺回款与异常项", "适合应收预警"),
        ]
        return self._render_cards(cards)

    def _refresh_overview_blocks(self):
        for record in self:
            record.overview_metrics_html = record._build_overview_metrics_html()
            record.overview_warning_html = record._build_overview_warning_html()
            record.overview_shortcuts_html = record._build_overview_shortcuts_html()

    def action_apply_query(self):
        for record in self:
            config = record._get_config()
            model = self.env[config["model"]]
            domain = record._build_query_domain()
            records = model.search(domain, limit=200)
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
                "result_object_label": False,
                "result_count": 0,
                "result_amount_label": False,
                "result_amount_total": 0.0,
                "result_last_query_at": False,
                "result_ids_json": False,
                "condition_hint_html": False,
                "result_overview_html": False,
                "result_summary_html": False,
                "result_preview_html": False,
                "detail_scope_html": False,
                "export_scope_html": False,
            }
        )
        return True

    def action_open_result_list(self):
        self.ensure_one()
        action = self.env.ref(self._get_config()["list_action"]).read()[0]
        action["domain"] = [("id", "in", self._result_ids())]
        return action

    def action_export_result_excel(self):
        self.ensure_one()
        result_ids = self._result_ids()
        if not result_ids:
            return False
        model_name = self._get_config()["model"]
        return {
            "type": "ir.actions.act_url",
            "url": f"/zfmd_pm/export_xlsx?model={model_name}&ids={','.join(map(str, result_ids))}",
            "target": "self",
        }

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.with_context(_skip_overview_refresh=True)._refresh_overview_blocks()
        return records

    def write(self, vals):
        result = super().write(vals)
        if not self.env.context.get('_skip_overview_refresh'):
            self.with_context(_skip_overview_refresh=True)._refresh_overview_blocks()
        return result

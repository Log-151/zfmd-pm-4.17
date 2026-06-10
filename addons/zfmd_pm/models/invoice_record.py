import re

from odoo.tools import float_compare, float_is_zero

from odoo import api, fields, models


class ZfmdInvoiceRecord(models.Model):
    _name = "zfmd.invoice.record"
    _description = "开票登记"
    _inherit = [
        "mail.thread",
        "zfmd.soft.delete.mixin",
        "zfmd.entry.confirmation.mixin",
    ]
    _order = "invoice_date desc, id desc"

    name = fields.Char(string="开票记录编号", required=True, copy=False, default="New")
    contract_id = fields.Many2one("zfmd.contract", string="关联合同", tracking=True)
    source_contract_no = fields.Char(string="来源合同号", tracking=True)
    display_contract_no = fields.Char(string="合同编号", compute="_compute_display_contract_no", store=True)
    contract_match_state = fields.Selection(
        [
            ("matched", "已匹配合同"),
            ("unmatched", "未匹配合同"),
            ("empty", "无合同号"),
        ],
        string="合同匹配状态",
        compute="_compute_contract_match_state",
        store=True,
        index=True,
    )

    invoice_date = fields.Date(string="开票日期", tracking=True)
    invoice_request_date = fields.Date(string="申请开票日期")
    invoice_partner_name = fields.Char(string="开票客户")
    province_name = fields.Char(string="省区")
    group_name = fields.Char(string="集团")
    site_name = fields.Char(string="场站")
    product_line = fields.Char(string="产品线")
    project_content = fields.Text(string="项目内容")
    sale_manager = fields.Char(string="销售经理")
    sale_contact = fields.Char(string="销售联系人")
    contract_amount = fields.Float(string="合同金额（元）")
    invoice_amount = fields.Float(string="开票金额（元）", tracking=True)
    invoice_situation = fields.Selection(
        [
            ("fully", "已开"),
            ("partial", "部分未开"),
            ("none", "未开"),
        ],
        string="开票情况",
        tracking=True,
    )
    tax_rate = fields.Char(string="税率")
    amount_untaxed = fields.Float(string="不含税金额（元）")
    amount_untaxed_manual = fields.Boolean(string="手动维护不含税金额")
    tax_amount = fields.Float(string="税额（元）", compute="_compute_tax_amount", store=True)
    tax_amount_warning = fields.Boolean(string="税额关系异常", compute="_compute_tax_amount", store=True)
    promised_payment_date = fields.Date(string="承诺回款日期")
    promised_payment_note = fields.Char(string="承诺回款说明")
    promised_payment_amount = fields.Float(string="承诺回款金额（元）")
    actual_payment_date = fields.Date(string="实际回款日期")
    actual_payment_date_note = fields.Text(string="实际回款日期说明")
    actual_payment_amount = fields.Float(string="实际回款金额（元）")
    actual_payment_amount_note = fields.Text(string="实际回款金额说明")
    actual_payment_manual = fields.Boolean(string="手动维护实际回款")
    express_no = fields.Char(string="发票快递单号")
    cancel_date = fields.Date(string="作废发票时间")
    cancel_reason = fields.Char(string="作废原因")
    state = fields.Selection(
        [
            ("draft", "草稿"),
            ("open", "未回款"),
            ("paid", "已回款"),
            ("cancel", "已作废"),
        ],
        string="状态",
        default="draft",
        tracking=True,
    )
    state_manual_override = fields.Boolean(string="手动锁定状态", tracking=True)
    import_source_file = fields.Char(string="导入来源文件")
    import_source_sheet = fields.Char(string="导入来源工作表")
    import_source_row = fields.Integer(string="导入来源行号")
    note = fields.Text(string="备注")

    invoice_year = fields.Char(string="开票年度", compute="_compute_period_labels", store=True, index=True)
    invoice_quarter = fields.Char(string="开票季度", compute="_compute_period_labels", store=True, index=True)
    invoice_month = fields.Char(string="开票月份", compute="_compute_period_labels", store=True, index=True)
    receivable_balance = fields.Float(string="应收余额（元）", compute="_compute_receivable_balance", store=True)
    is_payment_overdue = fields.Boolean(
        string="回款逾期预警",
        compute="_compute_payment_warning",
        store=True,
        index=True,
    )
    warning_info = fields.Char(string="预警信息", compute="_compute_warning_info")
    message_has_sms_error = fields.Boolean(groups="base.group_no_one")

    @api.model
    def _parse_tax_rate(self, value):
        text = str(value or "").strip()
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        if not match:
            return 0.13
        rate = float(match.group())
        return rate / 100.0 if "%" in text or rate > 1 else rate

    @api.model
    def _automatic_amount_untaxed(self, invoice_amount, tax_rate):
        rate = self._parse_tax_rate(tax_rate)
        return invoice_amount / (1 + rate) if invoice_amount else 0.0

    @api.depends("invoice_amount", "amount_untaxed", "tax_rate")
    def _compute_tax_amount(self):
        for record in self:
            record.tax_amount = (record.amount_untaxed or 0.0) * record._parse_tax_rate(record.tax_rate)
            record.tax_amount_warning = not float_is_zero(
                (record.amount_untaxed or 0.0) + record.tax_amount - (record.invoice_amount or 0.0),
                precision_digits=2,
            )

    @api.onchange("invoice_amount", "tax_rate")
    def _onchange_invoice_tax(self):
        for record in self.filtered(lambda item: not item.amount_untaxed_manual):
            record.amount_untaxed = record._automatic_amount_untaxed(record.invoice_amount, record.tax_rate)

    @api.onchange("amount_untaxed")
    def _onchange_amount_untaxed(self):
        for record in self:
            record.amount_untaxed_manual = True

    @api.depends("contract_id", "source_contract_no")
    def _compute_display_contract_no(self):
        for record in self:
            record.display_contract_no = record.contract_id.name or record.source_contract_no or False

    @api.depends("contract_id", "source_contract_no")
    def _compute_contract_match_state(self):
        for record in self:
            if record.contract_id:
                record.contract_match_state = "matched"
            elif record.source_contract_no:
                record.contract_match_state = "unmatched"
            else:
                record.contract_match_state = "empty"

    @api.depends("invoice_date")
    def _compute_period_labels(self):
        for record in self:
            if not record.invoice_date:
                record.invoice_year = False
                record.invoice_quarter = False
                record.invoice_month = False
                continue
            year = record.invoice_date.year
            month = record.invoice_date.month
            quarter = ((month - 1) // 3) + 1
            record.invoice_year = str(year)
            record.invoice_quarter = f"{year}年Q{quarter}"
            record.invoice_month = f"{year}-{month:02d}"

    @api.depends("invoice_amount", "actual_payment_amount")
    def _compute_receivable_balance(self):
        for record in self:
            balance = (record.invoice_amount or 0.0) - (record.actual_payment_amount or 0.0)
            record.receivable_balance = balance if balance > 0 else 0.0

    @api.depends("promised_payment_date", "receivable_balance", "state")
    def _compute_payment_warning(self):
        today = fields.Date.context_today(self)
        for record in self:
            record.is_payment_overdue = bool(
                record.promised_payment_date
                and record.promised_payment_date < today
                and (record.receivable_balance or 0.0) > 0
                and record.state not in ("paid", "cancel")
            )

    @api.depends("state", "is_payment_overdue")
    def _compute_warning_info(self):
        for record in self:
            if record.state == "paid":
                record.warning_info = "已回款"
            elif record.state == "cancel":
                record.warning_info = "已作废"
            elif record.state == "open" and record.is_payment_overdue:
                record.warning_info = "回款逾期"
            elif record.state == "open":
                record.warning_info = "未回款"
            else:
                record.warning_info = "草稿"

    def _prepare_contract_sync_vals(self, contract):
        return {
            "province_name": contract.province_name or False,
            "group_name": contract.group_name or False,
            "site_name": contract.site_id.name or False,
            "product_line": contract.product_line or False,
            "project_content": contract.project_content or False,
            "sale_manager": contract.sale_manager or False,
            "sale_contact": contract.sale_contact or False,
            "contract_amount": contract.amount_total or 0.0,
            "invoice_partner_name": contract.partner_id.name or False,
        }

    @api.onchange("contract_id")
    def _onchange_contract_id(self):
        for record in self:
            if record.contract_id:
                for key, value in record._prepare_contract_sync_vals(record.contract_id).items():
                    setattr(record, key, value)
                record.source_contract_no = record.contract_id.name

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals.get("name") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("zfmd.invoice.record") or "New"
            if vals.get("contract_id"):
                contract = self.env["zfmd.contract"].browse(vals["contract_id"])
                for key, value in self._prepare_contract_sync_vals(contract).items():
                    if not vals.get(key):
                        vals[key] = value
                vals["source_contract_no"] = contract.name
            vals["amount_untaxed_manual"] = bool(vals.get("amount_untaxed"))
            vals["actual_payment_manual"] = bool(vals.get("actual_payment_date") or vals.get("actual_payment_amount"))
            if not vals["amount_untaxed_manual"]:
                vals["amount_untaxed"] = self._automatic_amount_untaxed(
                    vals.get("invoice_amount") or 0.0, vals.get("tax_rate")
                )
        records = super().create(vals_list)
        if not self.env.context.get("skip_state_auto"):
            records.action_recompute_state_from_payment()
        if not self.env.context.get("skip_zfmd_sync"):
            self.env["zfmd.sync.engine"].refresh_from_invoices(self.env["zfmd.sync.engine"]._contract_numbers(records))
        return records

    def write(self, vals):
        old_contract_numbers = self.env["zfmd.sync.engine"]._contract_numbers(self)
        vals = dict(vals)
        state_fields = {
            "invoice_date",
            "invoice_amount",
            "actual_payment_amount",
            "cancel_date",
            "cancel_reason",
        }
        if vals.get("contract_id"):
            contract = self.env["zfmd.contract"].browse(vals["contract_id"])
            for key, value in self._prepare_contract_sync_vals(contract).items():
                if not vals.get(key):
                    vals[key] = value
            vals["source_contract_no"] = contract.name
        if "amount_untaxed" in vals and not self.env.context.get("auto_amount_untaxed"):
            vals["amount_untaxed_manual"] = True
        if {"actual_payment_date", "actual_payment_amount"} & set(vals) and not self.env.context.get("auto_link_sync"):
            vals["actual_payment_manual"] = True
        if {"invoice_amount", "tax_rate"} & set(vals):
            for record in self:
                manual = vals.get("amount_untaxed_manual", record.amount_untaxed_manual)
                if not manual and "amount_untaxed" not in vals:
                    vals["amount_untaxed"] = self._automatic_amount_untaxed(
                        vals.get("invoice_amount", record.invoice_amount),
                        vals.get("tax_rate", record.tax_rate),
                    )
        result = super().write(vals)
        if state_fields.intersection(vals) and not self.env.context.get("skip_state_auto"):
            self.action_recompute_state_from_payment()
        if not self.env.context.get("skip_zfmd_sync"):
            contract_numbers = old_contract_numbers | self.env["zfmd.sync.engine"]._contract_numbers(self)
            self.env["zfmd.sync.engine"].refresh_from_invoices(contract_numbers)
        return result

    def action_recompute_state_from_payment(self):
        precision = self.env["decimal.precision"].precision_get("Account") or 2
        for record in self:
            if record.state_manual_override and not self.env.context.get("force_state_auto"):
                continue
            if record.cancel_date or record.cancel_reason or record.state == "cancel":
                record.state = "cancel"
                continue
            invoice_amount = record.invoice_amount or 0.0
            actual_amount = record.actual_payment_amount or 0.0
            if actual_amount and (
                not invoice_amount or float_compare(actual_amount, invoice_amount, precision_digits=precision) >= 0
            ):
                record.state = "paid"
            elif record.invoice_date or invoice_amount:
                record.state = "open"
            else:
                record.state = "draft"
        return True

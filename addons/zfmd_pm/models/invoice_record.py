from odoo import api, fields, models


class ZfmdInvoiceRecord(models.Model):
    _name = "zfmd.invoice.record"
    _description = "开票登记"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "invoice_date desc, id desc"

    name = fields.Char(string="开票记录编号", required=True, copy=False, default="New")
    contract_id = fields.Many2one("zfmd.contract", string="关联合同", tracking=True)
    source_contract_no = fields.Char(string="来源合同号", tracking=True)
    display_contract_no = fields.Char(
        string="合同编号", compute="_compute_display_contract_no", store=True
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
    contract_amount = fields.Float(string="合同金额（万元）")
    invoice_amount = fields.Float(string="开票金额（万元）", tracking=True)
    tax_rate = fields.Char(string="税率")
    amount_untaxed = fields.Float(string="不含税金额（万元）")
    promised_payment_date = fields.Date(string="承诺回款日期")
    promised_payment_amount = fields.Float(string="承诺回款金额（万元）")
    actual_payment_date = fields.Date(string="实际回款日期")
    actual_payment_amount = fields.Float(string="实际回款金额（万元）")
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
    note = fields.Text(string="备注")

    invoice_year = fields.Char(
        string="开票年度", compute="_compute_period_labels", store=True, index=True
    )
    invoice_quarter = fields.Char(
        string="开票季度", compute="_compute_period_labels", store=True, index=True
    )
    invoice_month = fields.Char(
        string="开票月份", compute="_compute_period_labels", store=True, index=True
    )
    receivable_balance = fields.Float(
        string="应收余额（万元）", compute="_compute_receivable_balance", store=True
    )
    is_payment_overdue = fields.Boolean(
        string="回款逾期预警", compute="_compute_payment_warning", store=True, index=True
    )

    @api.depends("contract_id", "source_contract_no")
    def _compute_display_contract_no(self):
        for record in self:
            record.display_contract_no = record.contract_id.name or record.source_contract_no or False

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
                vals.update(self._prepare_contract_sync_vals(contract))
                vals["source_contract_no"] = contract.name
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("contract_id"):
            vals = dict(vals)
            contract = self.env["zfmd.contract"].browse(vals["contract_id"])
            vals.update(self._prepare_contract_sync_vals(contract))
            vals["source_contract_no"] = contract.name
        return super().write(vals)

from odoo import api, fields, models


class ZfmdReceivablePlan(models.Model):
    _name = "zfmd.receivable.plan"
    _description = "应收计划"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "receivable_date desc, name desc"

    name = fields.Char(string="应收计划编号", required=True, copy=False, default="New")
    contract_id = fields.Many2one("zfmd.contract", string="合同", tracking=True)
    sale_manager = fields.Char(string="销售经理")
    sale_contact = fields.Char(string="销售联系人")
    province_name = fields.Char(string="省（区）")
    group_name = fields.Char(string="集团")
    site_name = fields.Char(string="场站名称")
    product_line = fields.Char(string="产品线")
    project_content = fields.Text(string="合同项目内容")
    contract_amount = fields.Float(string="合同金额（万元）")
    receivable_item_name = fields.Char(string="应收款项名称")
    is_summary_line = fields.Boolean(string="是否汇总行", compute="_compute_is_summary_line", store=True)
    receivable_amount = fields.Float(string="应收款金额")
    receivable_date = fields.Date(string="应收时间", tracking=True)
    pending_progress_date = fields.Char(string="待工程实施进展确定回款时间")
    promised_entry_date = fields.Date(string="销售经理承诺进入回款期时间")
    promised_payment_date = fields.Date(string="销售经理承诺回款时间")
    promised_payment_amount = fields.Float(string="销售经理承诺回款金额")
    actual_payment_date = fields.Date(string="实际回款时间")
    actual_payment_amount = fields.Float(string="实际回款金额")
    overdue_months = fields.Integer(string="超期时间（月）")
    actual_invoice_date = fields.Date(string="实际开票时间")
    actual_arrival_date = fields.Date(string="实际到货时间")
    actual_acceptance_date = fields.Date(string="实际验收时间")
    payment_term = fields.Text(string="合同约定付款条件")
    state = fields.Selection(
        [
            ("draft", "草稿"),
            ("pending", "未到期"),
            ("due", "已到期"),
            ("partial", "部分回款"),
            ("paid", "已回款"),
            ("bad", "坏账/扣款"),
        ],
        string="状态",
        compute="_compute_state",
        store=True,
        readonly=False,
        tracking=True,
    )
    note = fields.Text(string="备注")

    def _prepare_contract_sync_vals(self, contract):
        return {
            "sale_manager": contract.sale_manager or False,
            "sale_contact": contract.sale_contact or False,
            "province_name": contract.province_name or False,
            "group_name": contract.group_name or False,
            "site_name": contract.site_id.name or False,
            "product_line": contract.product_line or False,
            "project_content": contract.project_content or False,
            "contract_amount": contract.amount_total or 0.0,
        }

    @api.onchange("contract_id")
    def _onchange_contract_id(self):
        for record in self:
            if record.contract_id:
                for key, value in record._prepare_contract_sync_vals(record.contract_id).items():
                    setattr(record, key, value)

    @api.depends("receivable_item_name")
    def _compute_is_summary_line(self):
        for record in self:
            item_name = (record.receivable_item_name or "").replace(" ", "").replace("\u3000", "")
            record.is_summary_line = item_name in {"合计", "总计", "汇总", "小计"}

    @api.depends("receivable_date", "receivable_amount", "actual_payment_amount", "note")
    def _compute_state(self):
        today = fields.Date.today()
        for record in self:
            note_text = (record.note or "").lower()
            if any(keyword in note_text for keyword in ["坏账", "扣款", "作废"]):
                record.state = "bad"
            elif record.actual_payment_amount and record.receivable_amount and record.actual_payment_amount >= record.receivable_amount:
                record.state = "paid"
            elif record.actual_payment_amount and record.actual_payment_amount > 0:
                record.state = "partial"
            elif record.receivable_date and record.receivable_date < today:
                record.state = "due"
            elif record.receivable_date:
                record.state = "pending"
            else:
                record.state = "draft"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals.get("name") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("zfmd.receivable.plan") or "New"
            if vals.get("receivable_item_name"):
                vals["receivable_item_name"] = str(vals["receivable_item_name"]).strip()
            if vals.get("contract_id"):
                vals.update(self._prepare_contract_sync_vals(self.env["zfmd.contract"].browse(vals["contract_id"])))
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        if vals.get("receivable_item_name"):
            vals["receivable_item_name"] = str(vals["receivable_item_name"]).strip()
        if vals.get("contract_id"):
            vals.update(self._prepare_contract_sync_vals(self.env["zfmd.contract"].browse(vals["contract_id"])))
        return super().write(vals)

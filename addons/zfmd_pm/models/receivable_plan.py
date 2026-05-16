from odoo import api, fields, models


class ZfmdReceivablePlan(models.Model):
    _name = "zfmd.receivable.plan"
    _description = "应收计划"
    _inherit = ["mail.thread"]
    _order = "display_order asc, id asc"

    name = fields.Char(string="应收记录编号", required=True, copy=False, default="New")
    display_order = fields.Integer(string="序号", default=0, index=True)
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

    sale_manager = fields.Char(string="销售经理")
    sale_contact = fields.Char(string="销售联系人")
    province_name = fields.Char(string="省区")
    group_name = fields.Char(string="集团")
    site_name = fields.Char(string="场站名称")
    product_line = fields.Char(string="产品线")
    project_content = fields.Text(string="合同项目内容")

    contract_amount = fields.Float(string="合同金额（元）")
    receivable_item_name = fields.Char(string="应收款项名称")
    is_summary_line = fields.Boolean(string="是否汇总行", compute="_compute_is_summary_line", store=True)
    receivable_amount = fields.Float(string="应收款项金额（元）")
    receivable_date = fields.Date(string="应收时间", tracking=True)
    receivable_date_text = fields.Char(string="应收时间原值", groups="base.group_no_one")

    pending_progress_date = fields.Char(string="待工程实施进展确定回款时间")
    promised_entry_date = fields.Date(string="销售经理承诺进入回款期时间")
    promised_entry_date_text = fields.Char(string="进入回款期时间原值", groups="base.group_no_one")
    promised_payment_date = fields.Date(string="销售经理承诺回款时间")
    promised_payment_date_text = fields.Char(string="承诺回款时间原值", groups="base.group_no_one")
    promised_payment_amount = fields.Float(string="销售经理承诺回款金额（元）")

    actual_payment_date = fields.Date(string="实际回款时间")
    actual_payment_date_text = fields.Char(string="实际回款时间原值", groups="base.group_no_one")
    actual_payment_amount = fields.Float(string="实际回款金额（元）")
    overdue_months = fields.Integer(string="超期时间（月）")

    actual_invoice_date = fields.Date(string="实际开票时间")
    actual_invoice_date_text = fields.Char(string="实际开票时间原值", groups="base.group_no_one")
    actual_arrival_date = fields.Date(string="实际到货时间")
    actual_arrival_date_text = fields.Char(string="实际到货时间原值", groups="base.group_no_one")
    arrival_voucher = fields.Selection([("yes", "有"), ("no", "无")], string="到货单")
    actual_acceptance_date = fields.Date(string="实际验收时间")
    actual_acceptance_date_text = fields.Char(string="实际验收时间原值", groups="base.group_no_one")
    acceptance_voucher = fields.Selection([("yes", "有"), ("no", "无")], string="验收单")

    late_payment_months = fields.Integer(string="迟后回款的月数", compute="_compute_late_payment_months", store=True)

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

    message_has_sms_error = fields.Boolean(groups="base.group_no_one")

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

    def _prepare_contract_sync_vals(self, contract):
        return {
            "source_contract_no": contract.name or False,
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

    @api.depends("receivable_date", "actual_payment_date")
    def _compute_late_payment_months(self):
        for record in self:
            if record.actual_payment_date and record.receivable_date:
                months = (record.actual_payment_date.year - record.receivable_date.year) * 12 + (
                    record.actual_payment_date.month - record.receivable_date.month
                )
                record.late_payment_months = months if months > 0 else 0
            else:
                record.late_payment_months = 0

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
            elif (
                record.actual_payment_amount
                and record.receivable_amount
                and record.actual_payment_amount >= record.receivable_amount
            ):
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
                contract = self.env["zfmd.contract"].browse(vals["contract_id"])
                vals.update(self._prepare_contract_sync_vals(contract))
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        if vals.get("receivable_item_name"):
            vals["receivable_item_name"] = str(vals["receivable_item_name"]).strip()
        if vals.get("contract_id"):
            contract = self.env["zfmd.contract"].browse(vals["contract_id"])
            vals.update(self._prepare_contract_sync_vals(contract))
        return super().write(vals)

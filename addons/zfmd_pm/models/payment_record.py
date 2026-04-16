from odoo import api, fields, models


class ZfmdPaymentRecord(models.Model):
    _name = "zfmd.payment.record"
    _description = "回款记录"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "payment_date desc, name desc"

    name = fields.Char(string="回款记录编号", required=True, copy=False, default="New")
    contract_id = fields.Many2one("zfmd.contract", string="合同", tracking=True)
    payment_date = fields.Date(string="回款日期", tracking=True)
    payer_name = fields.Char(string="付款单位")
    province_name = fields.Char(string="省（区）")
    group_name = fields.Char(string="集团")
    site_name = fields.Char(string="场站名称")
    product_line = fields.Char(string="产品线")
    project_content = fields.Text(string="合同项目内容")
    bill_amount = fields.Float(string="汇票回款(元)")
    cash_amount = fields.Float(string="现金回款(元)")
    amount_total = fields.Float(string="回款总额", compute="_compute_amount_total", store=True)
    payment_ratio_text = fields.Char(string="回款比例")
    payment_item_name = fields.Char(string="款项名称")
    sale_manager = fields.Char(string="销售经理")
    sale_contact = fields.Char(string="销售联系人")
    note = fields.Text(string="备注")

    def _prepare_contract_sync_vals(self, contract):
        return {
            "payer_name": contract.partner_id.name or False,
            "province_name": contract.province_name or False,
            "group_name": contract.group_name or False,
            "site_name": contract.site_id.name or False,
            "product_line": contract.product_line or False,
            "project_content": contract.project_content or False,
            "sale_manager": contract.sale_manager or False,
            "sale_contact": contract.sale_contact or False,
        }

    @api.onchange("contract_id")
    def _onchange_contract_id(self):
        for record in self:
            if record.contract_id:
                for key, value in record._prepare_contract_sync_vals(record.contract_id).items():
                    setattr(record, key, value)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals.get("name") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("zfmd.payment.record") or "New"
            if vals.get("contract_id"):
                vals.update(self._prepare_contract_sync_vals(self.env["zfmd.contract"].browse(vals["contract_id"])))
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("contract_id"):
            vals = dict(vals)
            vals.update(self._prepare_contract_sync_vals(self.env["zfmd.contract"].browse(vals["contract_id"])))
        return super().write(vals)

    @api.depends("bill_amount", "cash_amount")
    def _compute_amount_total(self):
        for record in self:
            record.amount_total = (record.bill_amount or 0.0) + (record.cash_amount or 0.0)

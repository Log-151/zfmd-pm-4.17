from odoo import api, fields, models


class ZfmdInvoiceRecord(models.Model):
    _name = "zfmd.invoice.record"
    _description = "开票记录"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "invoice_date desc, name desc"

    name = fields.Char(string="开票记录编号", required=True, copy=False, default="New")
    contract_id = fields.Many2one("zfmd.contract", string="合同", tracking=True)
    invoice_date = fields.Date(string="开票日期", tracking=True)
    invoice_request_date = fields.Date(string="申请开票日期")
    invoice_partner_name = fields.Char(string="开票单位")
    province_name = fields.Char(string="省（区）")
    group_name = fields.Char(string="集团")
    site_name = fields.Char(string="场站名称")
    product_line = fields.Char(string="产品线")
    project_content = fields.Text(string="合同项目内容")
    sale_manager = fields.Char(string="销售经理")
    sale_contact = fields.Char(string="销售联系人")
    contract_amount = fields.Float(string="合同金额")
    invoice_amount = fields.Float(string="发票金额", tracking=True)
    tax_rate = fields.Char(string="税率")
    amount_untaxed = fields.Float(string="不含税金额")
    promised_payment_date = fields.Date(string="承诺回款日期")
    promised_payment_amount = fields.Float(string="承诺回款金额")
    actual_payment_date = fields.Date(string="实际回款日期")
    actual_payment_amount = fields.Float(string="实际回款金额")
    express_no = fields.Char(string="发票快递单号")
    cancel_date = fields.Date(string="作废时间")
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

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals.get("name") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("zfmd.invoice.record") or "New"
            if vals.get("contract_id"):
                vals.update(self._prepare_contract_sync_vals(self.env["zfmd.contract"].browse(vals["contract_id"])))
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("contract_id"):
            vals = dict(vals)
            vals.update(self._prepare_contract_sync_vals(self.env["zfmd.contract"].browse(vals["contract_id"])))
        return super().write(vals)

from odoo import fields, models


class ZfmdAfterSaleService(models.Model):
    _name = "zfmd.after.sale.service"
    _description = "售后服务"
    _inherit = ["mail.thread", "zfmd.soft.delete.mixin"]
    _rec_name = "name"
    _order = "name desc, id desc"

    name = fields.Char(string="服务收费确认单编号", required=True, index=True, tracking=True)
    contract_no = fields.Char(string="对应合同编号", index=True, tracking=True)
    sale_manager = fields.Char(string="销售经理", index=True)
    province_name = fields.Char(string="省（区）", index=True)
    group_name = fields.Char(string="集团", index=True)
    site_name = fields.Char(string="场站名称", index=True)
    product_line = fields.Char(string="产品线", index=True)
    service_content = fields.Text(string="服务项目内容")
    chargeable = fields.Selection([("yes", "是"), ("no", "否")], string="是否收费", index=True)
    expected_contract_amount = fields.Float(string="预计合同金额")
    receivable_amount = fields.Float(string="应收款")
    hardware_cost_budget = fields.Float(string="硬件成本预算")
    met_tower_cost_budget = fields.Float(string="测风塔成本预算")
    technical_service_fee_budget = fields.Float(string="技术服务费预算")
    payable_amount = fields.Float(string="应付款")
    note = fields.Text(string="备注")

    message_has_sms_error = fields.Boolean(groups="base.group_no_one")

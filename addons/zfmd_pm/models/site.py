from odoo import fields, models


class ZfmdSite(models.Model):
    _name = "zfmd.site"
    _description = "场站"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"

    name = fields.Char(string="场站名称", required=True, tracking=True)
    partner_id = fields.Many2one("res.partner", string="客户", tracking=True)
    province_name = fields.Char(string="省（区）", tracking=True)
    group_name = fields.Char(string="集团", tracking=True)
    site_category = fields.Char(string="场站类别")
    other_name = fields.Char(string="其他名称")
    capacity_text = fields.Char(string="场站容量")
    note = fields.Text(string="备注")
    contract_ids = fields.One2many("zfmd.contract", "site_id", string="合同")


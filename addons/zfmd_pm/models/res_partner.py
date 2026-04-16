from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_zfmd_customer = fields.Boolean(string="兆方美迪客户")
    customer_code = fields.Char(string="客户编码")
    customer_level_1 = fields.Char(string="一级客户")
    customer_level_2 = fields.Char(string="二级客户")
    customer_level_3 = fields.Char(string="三级客户")
    province_name = fields.Char(string="省（区）")
    group_name = fields.Char(string="集团")
    zfmd_site_ids = fields.One2many("zfmd.site", "partner_id", string="场站")


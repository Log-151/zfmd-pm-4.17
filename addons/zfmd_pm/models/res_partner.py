from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_zfmd_customer = fields.Boolean(
        string="兆方美迪客户",
        compute="_compute_is_zfmd_customer",
        inverse="_inverse_is_zfmd_customer",
        store=True,
    )
    zfmd_customer_manual = fields.Boolean(string="手动标记为兆方美迪客户")
    customer_code = fields.Char(string="客户编码")
    customer_level_1 = fields.Char(string="一级客户")
    customer_level_2 = fields.Char(string="二级客户")
    customer_level_3 = fields.Char(string="三级客户")
    province_name = fields.Char(string="省（区）")
    group_name = fields.Char(string="集团")
    zfmd_site_ids = fields.One2many("zfmd.site", "partner_id", string="场站")
    zfmd_contract_ids = fields.One2many("zfmd.contract", "partner_id", string="合同")

    @api.depends("zfmd_customer_manual", "zfmd_contract_ids", "zfmd_contract_ids.is_deleted")
    def _compute_is_zfmd_customer(self):
        for partner in self:
            partner.is_zfmd_customer = bool(
                partner.zfmd_customer_manual
                or partner.zfmd_contract_ids.filtered(lambda contract: not contract.is_deleted)
            )

    def _inverse_is_zfmd_customer(self):
        for partner in self:
            partner.zfmd_customer_manual = partner.is_zfmd_customer

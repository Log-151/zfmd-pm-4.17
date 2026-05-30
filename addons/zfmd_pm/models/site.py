from odoo.exceptions import ValidationError

from odoo import api, fields, models


class ZfmdSite(models.Model):
    _name = "zfmd.site"
    _description = "场站"
    _inherit = ["mail.thread", "mail.activity.mixin", "zfmd.soft.delete.mixin"]
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

    @api.constrains("name", "partner_id", "is_deleted")
    def _check_duplicate_site_name_per_partner(self):
        for record in self:
            if not record.name or record.is_deleted:
                continue
            domain = [
                ("id", "!=", record.id),
                ("name", "=", record.name),
                ("partner_id", "=", record.partner_id.id or False),
                ("is_deleted", "=", False),
            ]
            if self.search_count(domain):
                raise ValidationError("同一客户下不能存在重复的场站名称。")

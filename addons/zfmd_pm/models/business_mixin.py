from odoo import fields, models


class ZfmdBusinessMixin(models.AbstractModel):
    _name = "zfmd.business.mixin"
    _description = "ZFMD 公共业务字段"

    province_name = fields.Char(string="省区", index=True)
    group_name = fields.Char(string="集团", index=True)
    site_name = fields.Char(string="场站名称", index=True)
    product_line = fields.Char(string="产品线", index=True)
    project_content = fields.Text(string="项目内容")
    sale_manager = fields.Char(string="销售经理", index=True)
    sale_contact = fields.Char(string="销售联系人")
    note = fields.Text(string="备注")

    def _prepare_business_vals_from_contract(self, contract):
        if not contract:
            return {}
        return {
            "province_name": contract.province_name or False,
            "group_name": contract.group_name or False,
            "site_name": contract.site_id.name or False,
            "product_line": contract.product_line or False,
            "project_content": contract.project_content or False,
            "sale_manager": contract.sale_manager or False,
            "sale_contact": contract.sale_contact or False,
        }

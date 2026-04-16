from odoo import api, fields, models


class ZfmdServiceRecord(models.Model):
    _name = "zfmd.service.record"
    _description = "服务记录"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "service_end_date desc, name desc"

    name = fields.Char(string="服务记录编号", required=True, tracking=True)
    contract_id = fields.Many2one("zfmd.contract", string="对应合同", tracking=True)
    site_id = fields.Many2one("zfmd.site", string="场站")
    sale_manager = fields.Char(string="销售经理", tracking=True)
    province_name = fields.Char(string="省（区）")
    group_name = fields.Char(string="集团")
    product_line = fields.Char(string="产品线")
    service_content = fields.Text(string="服务项目内容")
    chargeable = fields.Selection([("yes", "是"), ("no", "否")], string="是否收费")
    start_forecast_date = fields.Date(string="开始预报时间")
    formal_forecast_date = fields.Date(string="正式预报时间")
    service_end_date = fields.Date(string="服务合同到期时间", tracking=True)
    expired_months = fields.Integer(string="超期时间（月）", compute="_compute_overdue_info", store=True)
    is_overdue = fields.Boolean(string="是否超期", compute="_compute_overdue_info", store=True)
    expected_contract_amount = fields.Float(string="预计签订服务合同金额")
    expected_contract_sign_date = fields.Date(string="预计签订服务合同时间")
    stop_forecast_date = fields.Date(string="停止预报时间")
    break_months = fields.Integer(string="断档月份")
    renewal_note = fields.Text(string="续签服务合同情况说明")

    def _prepare_contract_sync_vals(self, contract):
        return {
            "site_id": contract.site_id.id or False,
            "sale_manager": contract.sale_manager or False,
            "province_name": contract.province_name or False,
            "group_name": contract.group_name or False,
            "product_line": contract.product_line or False,
            "service_content": contract.project_content or False,
            "service_end_date": contract.service_end_date or False,
            "expected_contract_amount": contract.amount_total or 0.0,
        }

    @api.onchange("contract_id")
    def _onchange_contract_id(self):
        for record in self:
            if record.contract_id:
                for key, value in record._prepare_contract_sync_vals(record.contract_id).items():
                    setattr(record, key, value)

    @api.depends("service_end_date")
    def _compute_overdue_info(self):
        today = fields.Date.today()
        for record in self:
            if not record.service_end_date or record.service_end_date >= today:
                record.is_overdue = False
                record.expired_months = 0
                continue
            months = (today.year - record.service_end_date.year) * 12 + (today.month - record.service_end_date.month)
            if today.day < record.service_end_date.day:
                months -= 1
            record.is_overdue = True
            record.expired_months = max(months, 0)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals.get("name") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("zfmd.service.record") or "New"
            if vals.get("contract_id"):
                vals.update(self._prepare_contract_sync_vals(self.env["zfmd.contract"].browse(vals["contract_id"])))
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("contract_id"):
            vals = dict(vals)
            vals.update(self._prepare_contract_sync_vals(self.env["zfmd.contract"].browse(vals["contract_id"])))
        return super().write(vals)

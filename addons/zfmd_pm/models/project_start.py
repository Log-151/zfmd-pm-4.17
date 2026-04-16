from odoo import api, fields, models


class ZfmdProjectStart(models.Model):
    _name = "zfmd.project.start"
    _description = "开工申请"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "transfer_date desc, name desc"

    name = fields.Char(string="开工申请编号", required=True, tracking=True)
    contract_id = fields.Many2one("zfmd.contract", string="对应合同", tracking=True)
    change_request_no = fields.Char(string="开工变更申请表编号")
    cancel_date = fields.Date(string="开工申请取消时间")
    has_cost = fields.Selection([("yes", "是"), ("no", "否")], string="是否发生成本费用")
    cost_handling = fields.Char(string="成本费用处理")
    transfer_date = fields.Date(string="开工申请流转时间", tracking=True)
    province_name = fields.Char(string="省（区）")
    group_name = fields.Char(string="集团")
    site_name = fields.Char(string="场站名称")
    site_category = fields.Char(string="场站类型")
    product_line = fields.Char(string="产品线")
    project_content = fields.Text(string="开工项目内容")
    sale_manager = fields.Char(string="销售经理", tracking=True)
    handover_meeting_date = fields.Date(string="项目交底会时间")
    estimated_contract_amount = fields.Float(string="预计合同金额")
    estimated_cost_amount = fields.Float(string="预计成本")
    actual_contract_amount = fields.Float(string="实际合同金额")
    delivery_department = fields.Char(string="交付部门")
    project_manager = fields.Char(string="项目经理")
    arrival_date = fields.Date(string="到货时间")
    acceptance_date = fields.Date(string="验收时间")
    state = fields.Selection(
        [
            ("draft", "草稿"),
            ("running", "进行中"),
            ("done", "完成"),
            ("cancel", "取消"),
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
            "actual_contract_amount": contract.amount_total or 0.0,
            "delivery_department": contract.delivery_department or False,
            "project_manager": contract.project_manager or False,
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
                vals["name"] = self.env["ir.sequence"].next_by_code("zfmd.project.start") or "New"
            if vals.get("contract_id"):
                vals.update(self._prepare_contract_sync_vals(self.env["zfmd.contract"].browse(vals["contract_id"])))
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("contract_id"):
            vals = dict(vals)
            vals.update(self._prepare_contract_sync_vals(self.env["zfmd.contract"].browse(vals["contract_id"])))
        return super().write(vals)

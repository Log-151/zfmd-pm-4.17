from odoo import api, fields, models


class ZfmdProjectManagement(models.Model):
    _name = "zfmd.project.management"
    _description = "项目管理"
    _inherit = ["mail.thread", "zfmd.soft.delete.mixin"]
    _rec_name = "name"
    _order = "name asc, id asc"

    name = fields.Char(string="合同编号", required=True, index=True, tracking=True)
    contract_id = fields.Many2one(
        "zfmd.contract",
        string="关联合同",
        index=True,
        tracking=True,
    )
    contract_key = fields.Char(
        string="合同核心号",
        index=True,
    )
    contract_match_state = fields.Selection(
        [
            ("matched", "已匹配合同"),
            ("unmatched", "未匹配合同"),
            ("empty", "无合同号"),
        ],
        string="合同匹配状态",
        index=True,
        default="empty",
    )
    customer_level_1 = fields.Char(string="一级客户")
    customer_level_2 = fields.Char(string="二级客户")
    customer_level_3 = fields.Char(string="三级客户")
    customer_name = fields.Char(string="客户名称", index=True)
    province_name = fields.Char(string="省（区）", index=True)
    group_name = fields.Char(string="集团", index=True)
    site_name = fields.Char(string="场站名称", index=True)
    product_line = fields.Char(string="产品线", index=True)
    project_content = fields.Text(string="合同项目内容")
    contract_sale_manager = fields.Char(string="签订合同销售经理", index=True)
    sale_contact = fields.Char(string="销售联系人")
    service_start_date = fields.Date(string="服务收费起始时间")
    service_start_date_note = fields.Char(string="服务收费起始时间说明")
    service_end_date = fields.Date(string="服务收费终止时间")
    service_end_date_note = fields.Char(string="服务收费终止时间说明")
    delivery_department = fields.Char(string="交付部门", index=True)
    project_manager = fields.Char(string="项目经理", index=True)
    contract_execution_status = fields.Char(string="合同执行情况", index=True)
    arrival_voucher = fields.Char(string="到货单")
    acceptance_voucher = fields.Char(string="验收单")
    initial_fee = fields.Float(string="初装费（元）")
    forecast_service_fee = fields.Float(string="预测服务费（元）")
    contract_amount = fields.Float(string="合同总额（元）")
    invoice_status = fields.Char(string="发票开具情况", index=True)
    paid_amount = fields.Float(string="已回款（元）")
    total_receivable_amount = fields.Float(string="总应收款（元）")
    actual_total_receivable_amount = fields.Float(string="实际总应收款（元）")
    invoiced_receivable_amount = fields.Float(string="已开票应收款（元）")
    progress_receivable_amount = fields.Float(string="进度应收款（元）")
    actual_progress_receivable_amount = fields.Float(string="实际进度应收款（元）")
    progress_receivable_item_name = fields.Char(string="进度应收款项名称")
    invoice_date = fields.Date(string="开票时间")
    invoice_date_note = fields.Char(string="开票时间（说明）")
    customer_code = fields.Char(string="客户编码")
    has_bad_debt = fields.Char(string="是否有坏账")
    bad_debt_amount = fields.Float(string="坏账金额（元）")
    invoiced_bad_debt_amount = fields.Float(string="已开票坏账金额（元）")
    note = fields.Text(string="备注")

    message_has_sms_error = fields.Boolean(groups="base.group_no_one")

    @api.model
    def _prepare_contract_link_vals(self, vals):
        vals = dict(vals)
        contract_model = self.env["zfmd.contract"].sudo()
        contract = self.env["zfmd.contract"].browse()
        if vals.get("contract_id"):
            contract = contract_model.browse(vals["contract_id"])
        elif "name" in vals:
            contract = contract_model.find_by_contract_no(vals.get("name"))

        if contract:
            vals["contract_id"] = contract.id
            vals["contract_key"] = contract.contract_key or contract_model._extract_contract_key(contract.name)
            vals["contract_match_state"] = "matched"
        elif "name" in vals:
            vals["contract_key"] = contract_model._extract_contract_key(vals.get("name"))
            vals["contract_match_state"] = "unmatched" if vals.get("name") else "empty"
        elif "contract_id" in vals and not vals.get("contract_id"):
            vals["contract_match_state"] = "unmatched" if vals.get("name") else "empty"
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._prepare_contract_link_vals(vals) for vals in vals_list]
        return super().create(vals_list)

    def write(self, vals):
        if {"name", "contract_id"} & set(vals):
            vals = self._prepare_contract_link_vals(vals)
        return super().write(vals)

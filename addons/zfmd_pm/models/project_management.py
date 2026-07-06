from odoo import api, fields, models


class ZfmdProjectManagement(models.Model):
    _name = "zfmd.project.management"
    _description = "项目管理"
    _inherit = [
        "mail.thread",
        "zfmd.soft.delete.mixin",
        "zfmd.entry.confirmation.mixin",
    ]
    _rec_name = "name"
    _order = "name desc, id desc"

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
    contract_project_no = fields.Char(string="项目编号", index=True)
    contract_sign_date = fields.Date(string="签约日期", index=True)
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
    execution_status_manual = fields.Boolean(string="手动维护合同执行情况", default=False)
    arrival_voucher = fields.Char(string="到货单")
    arrival_voucher_manual = fields.Boolean(string="手动维护到货单", default=False)
    acceptance_voucher = fields.Char(string="验收单")
    acceptance_voucher_manual = fields.Boolean(string="手动维护验收单", default=False)
    initial_fee = fields.Float(string="初装费（元）")
    forecast_service_fee = fields.Float(string="预测服务费（元）")
    contract_amount = fields.Float(string="合同总额（元）")
    invoice_status = fields.Char(string="发票开具情况", index=True)
    invoice_status_manual = fields.Boolean(string="手动维护发票开具情况", default=False)
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
            if not vals.get("customer_code"):
                vals["customer_code"] = contract.customer_code or contract.partner_id.customer_code or False
        elif "name" in vals:
            vals["contract_key"] = contract_model._extract_contract_key(vals.get("name"))
            vals["contract_match_state"] = "unmatched" if vals.get("name") else "empty"
        elif "contract_id" in vals and not vals.get("contract_id"):
            vals["contract_match_state"] = "unmatched" if vals.get("name") else "empty"
        return vals

    @api.onchange("site_name")
    def _onchange_site_name(self):
        for record in self:
            site_name = (record.site_name or "").strip()
            if not site_name:
                continue
            site = self.env["zfmd.site"].search(
                ["|", ("name", "=", site_name), ("other_name", "=", site_name)],
                limit=2,
            )
            if len(site) != 1:
                continue
            site = site[:1]
            record.province_name = site.province_name or record.province_name
            record.group_name = site.group_name or record.group_name
            if site.partner_id:
                record.customer_name = site.partner_id.name or record.customer_name
                record.customer_code = site.partner_id.customer_code or record.customer_code
                record.customer_level_1 = site.partner_id.customer_level_1 or record.customer_level_1
                record.customer_level_2 = site.partner_id.customer_level_2 or record.customer_level_2
                record.customer_level_3 = site.partner_id.customer_level_3 or record.customer_level_3
            reference = self.env["zfmd.contract"].search(
                [("site_id", "=", site.id)],
                order="archive_date desc, id desc",
                limit=1,
            )
            if reference:
                record.product_line = reference.product_line or record.product_line
                record.project_content = reference.project_content or record.project_content
                record.contract_sale_manager = reference.sale_manager or record.contract_sale_manager
                record.sale_contact = reference.sale_contact or record.sale_contact
                record.delivery_department = reference.delivery_department or record.delivery_department
                record.project_manager = reference.project_manager or record.project_manager

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._prepare_contract_link_vals(vals) for vals in vals_list]
        records = super().create(vals_list)
        if not self.env.context.get("skip_zfmd_sync"):
            self.env["zfmd.sync.engine"].sync_projects_to_contracts(
                records, set().union(*(vals.keys() for vals in vals_list))
            )
            self.env["zfmd.sync.engine"].refresh_projects({record.name for record in records})
        return records

    def write(self, vals):
        changed_fields = set(vals)
        old_contract_numbers = {record.contract_id.name or record.name for record in self}
        vals = dict(vals)
        if not self.env.context.get("skip_manual_override"):
            if "contract_execution_status" in vals and "execution_status_manual" not in vals:
                vals["execution_status_manual"] = bool(vals.get("contract_execution_status"))
            if "arrival_voucher" in vals and "arrival_voucher_manual" not in vals:
                vals["arrival_voucher_manual"] = bool(vals.get("arrival_voucher"))
            if "acceptance_voucher" in vals and "acceptance_voucher_manual" not in vals:
                vals["acceptance_voucher_manual"] = bool(vals.get("acceptance_voucher"))
            if "invoice_status" in vals and "invoice_status_manual" not in vals:
                vals["invoice_status_manual"] = bool(vals.get("invoice_status"))
        if {"name", "contract_id"} & set(vals):
            vals = self._prepare_contract_link_vals(vals)
        result = super().write(vals)
        if not self.env.context.get("skip_zfmd_sync"):
            self.env["zfmd.sync.engine"].sync_projects_to_contracts(self, changed_fields)
            self.env["zfmd.sync.engine"].refresh_projects(
                old_contract_numbers | {record.contract_id.name or record.name for record in self}
            )
        return result

    @api.model
    def action_refresh_all_projects(self):
        contract_numbers = {
            record.contract_id.name or record.name
            for record in self.search([])
            if record.contract_id.name or record.name
        }
        self.env["zfmd.sync.engine"].refresh_projects(contract_numbers)
        return True

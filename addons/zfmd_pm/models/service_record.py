from dateutil.relativedelta import relativedelta

from odoo import api, fields, models

_G = "base.group_no_one"


class ZfmdServiceRecord(models.Model):
    _name = "zfmd.service.record"
    _description = "气象服务记录"
    _inherit = ["mail.thread"]
    _order = "service_end_date desc, name desc"

    name = fields.Char(string="服务记录编号", required=True, tracking=True)
    contract_id = fields.Many2one("zfmd.contract", string="关联合同", tracking=True)
    source_contract_no = fields.Char(string="来源合同号", tracking=True)
    display_contract_no = fields.Char(string="合同编号", compute="_compute_display_contract_no", store=True)
    contract_match_state = fields.Selection(
        [
            ("matched", "已匹配合同"),
            ("unmatched", "未匹配合同"),
            ("empty", "无合同号"),
        ],
        string="合同匹配状态",
        compute="_compute_contract_match_state",
        store=True,
        index=True,
    )
    raw_import_data = fields.Text(string="原始导入数据", groups=_G)

    record_date = fields.Date(string="记录日期")
    record_date_text = fields.Char(string="记录日期原文", groups=_G)

    site_id = fields.Many2one("zfmd.site", string="场站档案")
    site_name = fields.Char(string="场站名称")
    site_category = fields.Char(string="场站类别")
    signing_sale_manager = fields.Char(string="签订合同销售经理")
    sale_manager = fields.Char(string="销售经理", tracking=True)
    province_name = fields.Char(string="省区")
    group_name = fields.Char(string="集团")
    product_line = fields.Char(string="产品线")
    service_content = fields.Text(string="服务项目内容")
    chargeable = fields.Selection([("yes", "是"), ("no", "否")], string="是否收费")
    chargeable_text = fields.Char(string="是否收费原文", groups=_G)

    start_forecast_date = fields.Date(string="开始预报时间")
    start_forecast_date_text = fields.Char(string="开始预报时间原文", groups=_G)
    formal_forecast_date = fields.Date(string="正式预报时间")
    formal_forecast_date_text = fields.Char(string="正式预报时间原文", groups=_G)
    service_end_date = fields.Date(string="服务合同到期时间", tracking=True)
    service_end_date_text = fields.Char(string="服务合同到期信息原文", groups=_G)
    expired_months = fields.Integer(string="超期时间（月）")
    expired_months_text = fields.Char(string="超期时间原文", groups=_G)
    is_overdue = fields.Boolean(string="是否超期")
    is_overdue_text = fields.Char(string="是否超期原文", groups=_G)

    expected_contract_amount = fields.Float(string="预计签订服务合同金额（元）")
    expected_contract_amount_text = fields.Char(string="预计签订服务合同金额原文", groups=_G)
    expected_contract_sign_date = fields.Date(string="预计签订服务合同时间")
    expected_contract_sign_date_text = fields.Char(string="预计签订服务合同时间原文", groups=_G)
    stop_forecast_date = fields.Date(string="停止预报时间")
    stop_forecast_date_text = fields.Char(string="停止预报时间原文", groups=_G)
    break_months = fields.Integer(
        string="中断时间（月）",
        compute="_compute_time_fields",
        search="_search_break_months",
    )
    break_months_text = fields.Char(string="中断时间原文", groups=_G)
    expiry_warning = fields.Char(string="到期时间预警", compute="_compute_time_fields")

    renewal_before_end_date = fields.Date(string="续签前服务到期时间")
    renewal_before_end_date_text = fields.Char(string="续签前服务到期时间原文", groups=_G)
    renewal_after_start_date = fields.Date(string="续签后服务开始时间")
    renewal_after_start_date_text = fields.Char(string="续签后服务开始时间原文", groups=_G)
    break_fee_handling = fields.Text(string="中断期间服务费如何处理")
    renewal_note = fields.Text(string="续签服务合同情况说明")
    note = fields.Text(string="备注")

    # 屏蔽 mail.thread 带入的 SMS 字段
    message_has_sms_error = fields.Boolean(groups=_G)

    @api.depends("service_end_date")
    def _compute_time_fields(self):
        today = fields.Date.today()
        for record in self:
            if not record.service_end_date:
                record.break_months = 0
                record.expiry_warning = ""
                continue
            months = (today.year - record.service_end_date.year) * 12 + (today.month - record.service_end_date.month)
            record.break_months = months
            if record.service_end_date < today:
                record.expiry_warning = "已到期"
            elif months >= -3:
                record.expiry_warning = f"{-months}个月后到期"
            else:
                record.expiry_warning = ""

    def _search_break_months(self, operator, value):
        today = fields.Date.today()
        # break_months = today - service_end_date（月）
        # break_months op value  ↔  service_end_date op (today - value 月)，方向取反
        op_map = {">": "<", ">=": "<=", "<": ">", "<=": ">=", "=": "=", "!=": "!="}
        target = today - relativedelta(months=int(value))
        return [("service_end_date", op_map.get(operator, operator), target)]

    @api.depends("contract_id", "source_contract_no")
    def _compute_display_contract_no(self):
        for record in self:
            record.display_contract_no = record.contract_id.name or record.source_contract_no or False

    @api.depends("contract_id", "source_contract_no", "raw_import_data")
    def _compute_contract_match_state(self):
        for record in self:
            if record.contract_id:
                record.contract_match_state = "matched"
            elif record.source_contract_no or record.raw_import_data:
                record.contract_match_state = "unmatched"
            else:
                record.contract_match_state = "empty"

    def _prepare_contract_sync_vals(self, contract):
        return {
            "source_contract_no": contract.name or False,
            "site_id": contract.site_id.id or False,
            "site_name": contract.site_id.name or False,
            "sale_manager": contract.sale_manager or False,
            "province_name": contract.province_name or False,
            "group_name": contract.group_name or False,
            "product_line": contract.product_line or False,
            "service_content": contract.project_content or False,
            "expected_contract_amount": contract.amount_total or 0.0,
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
                vals["name"] = self.env["ir.sequence"].next_by_code("zfmd.service.record") or "New"
            if vals.get("contract_id"):
                contract = self.env["zfmd.contract"].browse(vals["contract_id"])
                vals.update(self._prepare_contract_sync_vals(contract))
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("contract_id"):
            vals = dict(vals)
            contract = self.env["zfmd.contract"].browse(vals["contract_id"])
            vals.update(self._prepare_contract_sync_vals(contract))
        return super().write(vals)

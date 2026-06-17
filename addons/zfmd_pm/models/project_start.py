from odoo import api, fields, models

_G = "base.group_no_one"


class ZfmdProjectStart(models.Model):
    _name = "zfmd.project.start"
    _description = "开工申请"
    _inherit = [
        "mail.thread",
        "zfmd.soft.delete.mixin",
        "zfmd.entry.confirmation.mixin",
    ]
    _order = "display_contract_no desc, id desc"

    name = fields.Char(string="开工申请编号", required=True, tracking=True)
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
    raw_import_data = fields.Text(string="原始导入数据")

    change_request_no = fields.Char(string="开工变更申请表编号")
    cancel_date = fields.Date(string="开工申请取消时间")
    cancel_date_text = fields.Char(string="开工申请取消时间原文")
    has_cost = fields.Selection([("yes", "是"), ("no", "否")], string="是否发生成本费用")
    has_cost_text = fields.Char(string="是否发生成本费用原文")
    cost_handling = fields.Char(string="成本费用处理")
    transfer_date = fields.Date(string="开工申请流转时间", tracking=True)
    transfer_date_text = fields.Char(string="开工申请流转时间原文")

    province_name = fields.Char(string="省（区）")
    group_name = fields.Char(string="集团")
    site_name = fields.Char(string="场站名称")
    site_category = fields.Char(string="场站类型")
    product_line = fields.Char(string="产品线")
    project_content = fields.Text(string="开工项目内容")
    sale_manager = fields.Char(string="销售经理", tracking=True)

    handover_meeting_date = fields.Date(string="项目交底会时间")
    handover_meeting_date_text = fields.Char(string="项目交底会时间原文")
    estimated_contract_amount = fields.Float(string="预计合同金额（元）")
    estimated_contract_amount_text = fields.Char(string="预计合同金额原文")
    estimated_receivable = fields.Float(
        string="预计应收款（元）",
        compute="_compute_estimated_receivable",
        store=True,
    )
    estimated_contract_amount_band = fields.Selection(
        selection="_amount_band_selection",
        string="预计合同金额区间",
        compute="_compute_amount_bands",
        store=True,
        index=True,
    )
    estimated_cost_amount = fields.Float(string="预计成本（元）")
    estimated_cost_amount_text = fields.Char(string="预计成本原文")
    estimated_cost_amount_band = fields.Selection(
        selection="_amount_band_selection",
        string="预计成本区间",
        compute="_compute_amount_bands",
        store=True,
        index=True,
    )
    actual_contract_amount = fields.Float(string="实际合同金额（元）")
    actual_contract_amount_text = fields.Char(string="实际合同金额原文")
    actual_contract_amount_band = fields.Selection(
        selection="_amount_band_selection",
        string="实际合同金额区间",
        compute="_compute_amount_bands",
        store=True,
        index=True,
    )
    delivery_department = fields.Char(string="交付部门")
    project_manager = fields.Char(string="项目经理")
    arrival_date = fields.Date(string="到货时间")
    arrival_date_text = fields.Char(string="到货时间原文")
    acceptance_date = fields.Date(string="验收时间")
    acceptance_date_text = fields.Char(string="验收时间原文")

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

    message_has_sms_error = fields.Boolean(groups=_G)

    @api.depends("contract_id", "source_contract_no")
    def _compute_display_contract_no(self):
        for record in self:
            record.display_contract_no = record.contract_id.name or record.source_contract_no or False

    @api.depends("contract_id", "source_contract_no")
    def _compute_contract_match_state(self):
        for record in self:
            if record.contract_id:
                record.contract_match_state = "matched"
            elif record.source_contract_no:
                record.contract_match_state = "unmatched"
            else:
                record.contract_match_state = "empty"

    def _amount_band_selection(self):
        return [
            ("zero", "0 或未填写"),
            ("lt_50k", "5万以内"),
            ("50k_100k", "5万-10万"),
            ("100k_300k", "10万-30万"),
            ("300k_500k", "30万-50万"),
            ("500k_1m", "50万-100万"),
            ("gte_1m", "100万以上"),
        ]

    def _get_amount_band(self, amount):
        amount = amount or 0.0
        if amount <= 0:
            return "zero"
        if amount < 50000:
            return "lt_50k"
        if amount < 100000:
            return "50k_100k"
        if amount < 300000:
            return "100k_300k"
        if amount < 500000:
            return "300k_500k"
        if amount < 1000000:
            return "500k_1m"
        return "gte_1m"

    @api.depends("estimated_contract_amount", "estimated_cost_amount", "actual_contract_amount")
    def _compute_amount_bands(self):
        for record in self:
            record.estimated_contract_amount_band = record._get_amount_band(record.estimated_contract_amount)
            record.estimated_cost_amount_band = record._get_amount_band(record.estimated_cost_amount)
            record.actual_contract_amount_band = record._get_amount_band(record.actual_contract_amount)

    @api.depends("estimated_contract_amount")
    def _compute_estimated_receivable(self):
        for record in self:
            record.estimated_receivable = (record.estimated_contract_amount or 0.0) * 0.3

    def _prepare_contract_sync_vals(self, contract):
        return {
            "source_contract_no": contract.name or False,
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
            record.site_category = site.site_category or record.site_category
            reference = self.env["zfmd.contract"].search(
                [("site_id", "=", site.id)],
                order="archive_date desc, id desc",
                limit=1,
            )
            if reference:
                record.product_line = reference.product_line or record.product_line
                record.project_content = reference.project_content or record.project_content
                record.sale_manager = reference.sale_manager or record.sale_manager
                record.delivery_department = reference.delivery_department or record.delivery_department
                record.project_manager = reference.project_manager or record.project_manager

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals.get("name") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("zfmd.project.start") or "New"
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

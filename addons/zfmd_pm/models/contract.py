from odoo import api, fields, models


class ZfmdContract(models.Model):
    _name = "zfmd.contract"
    _description = "销售合同"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "name"
    _order = "contract_sign_date desc, name desc"

    name = fields.Char(string="合同编号", required=True, tracking=True)
    contract_key = fields.Char(string="合同识别码", tracking=True)
    contract_name = fields.Char(string="合同名称", tracking=True)
    partner_id = fields.Many2one("res.partner", string="客户", tracking=True)
    site_id = fields.Many2one("zfmd.site", string="场站", tracking=True)
    province_name = fields.Char(string="省区", tracking=True)
    group_name = fields.Char(string="集团", tracking=True)
    product_line = fields.Char(string="产品线", tracking=True)
    project_content = fields.Text(string="项目内容")
    sale_manager = fields.Char(string="销售经理", tracking=True)
    sale_contact = fields.Char(string="销售联系人")
    contract_sign_date = fields.Date(string="合同签订日期", tracking=True)
    archive_date = fields.Date(string="合同存档日期")
    service_start_date = fields.Date(string="服务开始日期")
    service_end_date = fields.Date(string="服务结束日期")
    initial_fee = fields.Float(string="初装费")
    service_fee = fields.Float(string="服务费")
    amount_total = fields.Float(string="合同总额", tracking=True)
    amount_untaxed = fields.Float(string="不含税金额")
    special_contract = fields.Boolean(string="特殊合同")
    delivery_department = fields.Char(string="交付部门")
    project_manager = fields.Char(string="项目经理")
    start_application_no = fields.Char(string="开工申请编号")
    after_sale_no = fields.Char(string="售后服务编号")
    change_no = fields.Char(string="合同变更号")
    state = fields.Selection(
        [
            ("draft", "草稿"),
            ("running", "执行中"),
            ("done", "已完工"),
            ("closed", "已关闭"),
        ],
        string="状态",
        default="draft",
        tracking=True,
    )
    note = fields.Text(string="备注")

    project_start_ids = fields.One2many("zfmd.project.start", "contract_id", string="开工申请")
    service_record_ids = fields.One2many("zfmd.service.record", "contract_id", string="服务记录")
    invoice_record_ids = fields.One2many("zfmd.invoice.record", "contract_id", string="开票记录")
    payment_record_ids = fields.One2many("zfmd.payment.record", "contract_id", string="回款记录")
    receivable_plan_ids = fields.One2many("zfmd.receivable.plan", "contract_id", string="应收计划")

    project_start_count = fields.Integer(string="开工数", compute="_compute_dashboard_stats")
    service_record_count = fields.Integer(string="服务数", compute="_compute_dashboard_stats")
    invoice_record_count = fields.Integer(string="开票数", compute="_compute_dashboard_stats")
    payment_record_count = fields.Integer(string="回款数", compute="_compute_dashboard_stats")
    receivable_plan_count = fields.Integer(string="应收数", compute="_compute_dashboard_stats")
    invoice_total_amount = fields.Float(string="累计开票", compute="_compute_dashboard_stats")
    payment_total_amount = fields.Float(string="累计回款", compute="_compute_dashboard_stats")
    receivable_total_amount = fields.Float(string="应收合计", compute="_compute_dashboard_stats")
    receivable_paid_amount = fields.Float(string="已回款合计", compute="_compute_dashboard_stats")
    receivable_unpaid_amount = fields.Float(string="未回款合计", compute="_compute_dashboard_stats")
    collection_rate = fields.Float(string="回款率", compute="_compute_dashboard_stats")

    @api.depends(
        "project_start_ids",
        "service_record_ids",
        "invoice_record_ids.invoice_amount",
        "invoice_record_ids.state",
        "payment_record_ids.amount_total",
        "receivable_plan_ids.receivable_amount",
        "receivable_plan_ids.actual_payment_amount",
    )
    def _compute_dashboard_stats(self):
        for record in self:
            record.project_start_count = len(record.project_start_ids)
            record.service_record_count = len(record.service_record_ids)
            record.invoice_record_count = len(record.invoice_record_ids)
            record.payment_record_count = len(record.payment_record_ids)
            record.receivable_plan_count = len(record.receivable_plan_ids)
            record.invoice_total_amount = sum(
                line.invoice_amount for line in record.invoice_record_ids if line.state != "cancel"
            )
            record.payment_total_amount = sum(line.amount_total for line in record.payment_record_ids)
            record.receivable_total_amount = sum(line.receivable_amount for line in record.receivable_plan_ids)
            record.receivable_paid_amount = sum(line.actual_payment_amount for line in record.receivable_plan_ids)
            record.receivable_unpaid_amount = max(record.receivable_total_amount - record.receivable_paid_amount, 0.0)
            record.collection_rate = (
                (record.receivable_paid_amount / record.receivable_total_amount) * 100.0
                if record.receivable_total_amount
                else 0.0
            )

    def _open_related_records(self, action_xmlid):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(action_xmlid)
        action["domain"] = [("contract_id", "=", self.id)]
        action["context"] = {"default_contract_id": self.id}
        return action

    def action_open_project_starts(self):
        return self._open_related_records("zfmd_pm.action_zfmd_project_start")

    def action_open_service_records(self):
        return self._open_related_records("zfmd_pm.action_zfmd_service_record")

    def action_open_invoice_records(self):
        return self._open_related_records("zfmd_pm.action_zfmd_invoice_record")

    def action_open_payment_records(self):
        return self._open_related_records("zfmd_pm.action_zfmd_payment_record")

    def action_open_receivable_plans(self):
        return self._open_related_records("zfmd_pm.action_zfmd_receivable_plan")

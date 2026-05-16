import re

from odoo import api, fields, models


class ZfmdContract(models.Model):
    _name = "zfmd.contract"
    _description = "销售合同"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "name"
    _order = "contract_sort_key desc, name asc, id asc"

    display_order = fields.Integer(string="排序", default=10, tracking=True, index=True)
    display_order_text = fields.Integer(string="序号", compute="_compute_display_order_text")
    contract_sort_key = fields.Char(
        string="存档排序键",
        compute="_compute_contract_sort_key",
        store=True,
        index=True,
    )
    record_count_helper = fields.Integer(string="数量", compute="_compute_record_count_helper")

    name = fields.Char(string="合同编号", required=True, tracking=True)
    contract_key = fields.Char(string="合同核心号", tracking=True, index=True)
    contract_name = fields.Char(string="合同名称", tracking=True)
    customer_level_1 = fields.Char(string="一级公司")
    customer_level_2 = fields.Char(string="二级公司")
    customer_level_3 = fields.Char(string="三级公司")
    partner_id = fields.Many2one("res.partner", string="客户", tracking=True)
    site_id = fields.Many2one("zfmd.site", string="场站", tracking=True)
    site_other_name = fields.Char(string="其他名称")
    site_category = fields.Char(string="场站类别")
    capacity_text = fields.Char(string="场站容量")
    contract_project_no = fields.Char(string="项目编号")
    province_name = fields.Char(string="省区", tracking=True)
    group_name = fields.Char(string="集团", tracking=True)
    product_line = fields.Char(string="产品线", tracking=True)
    project_content = fields.Text(string="项目内容")
    sale_manager = fields.Char(string="销售经理", tracking=True)
    sale_contact = fields.Char(string="销售联系人")
    contract_sign_date = fields.Date(string="合同签订日期", tracking=True)
    contract_sign_date_text = fields.Char(string="合同签订日期原文", groups="base.group_no_one")
    archive_date = fields.Date(string="合同存档日期")
    archive_date_text = fields.Char(string="合同存档日期原文", groups="base.group_no_one")
    archive_document_type = fields.Char(string="合同存档原件/复印件")
    archive_copy_count = fields.Integer(string="合同存档份数")
    service_start_date = fields.Date(string="服务开始日期")
    service_start_date_text = fields.Char(string="服务开始说明")
    service_end_date = fields.Date(string="服务结束日期")
    service_end_date_text = fields.Char(string="服务结束日期原文", groups="base.group_no_one")
    initial_fee = fields.Float(string="初装费")
    service_fee = fields.Float(string="预测服务费")
    amount_total = fields.Float(string="合同总额", tracking=True)
    amount_untaxed = fields.Float(string="不含税金额")
    exclude_sales_revenue = fields.Char(string="不算销售收入")
    exclude_sales_performance = fields.Char(string="不算销售业绩")
    bond_status = fields.Char(string="保函开具情况")
    special_contract = fields.Boolean(string="特殊合同")
    delivery_department = fields.Char(string="交付部门")
    project_manager = fields.Char(string="项目经理")
    handover_meeting_date = fields.Date(string="合同交底会时间")
    handover_meeting_date_text = fields.Char(string="合同交底会时间原文", groups="base.group_no_one")
    third_party_interface_fee = fields.Float(string="第三方接口费")
    start_application_no = fields.Char(string="开工申请编号")
    after_sale_no = fields.Char(string="售后服务编号")
    change_no = fields.Char(string="合同变更号")
    note = fields.Text(string="备注")
    state = fields.Selection(
        [
            ("draft", "草稿"),
            ("running", "执行中"),
            ("done", "已完成"),
            ("closed", "已关闭"),
        ],
        string="状态",
        default="draft",
        tracking=True,
    )

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

    _sql_constraints = [
        ("zfmd_contract_name_unique", "unique(name)", "合同编号必须唯一。"),
    ]

    def init(self):
        self.env.cr.execute(
            """
            UPDATE zfmd_contract
               SET contract_sort_key = COALESCE(archive_date::text, '0000-00-00')
             WHERE contract_sort_key IS DISTINCT FROM COALESCE(archive_date::text, '0000-00-00')
            """
        )

    @api.depends("archive_date", "contract_sort_key", "name")
    def _compute_display_order_text(self):
        ordered_ids = self.search([], order=self._order).ids
        sequence_by_id = {record_id: index for index, record_id in enumerate(ordered_ids, start=1)}
        for record in self:
            record.display_order_text = sequence_by_id.get(record.id, 0)

    @api.depends("archive_date")
    def _compute_contract_sort_key(self):
        for record in self:
            if record.archive_date:
                record.contract_sort_key = fields.Date.to_string(record.archive_date)
            else:
                record.contract_sort_key = "0000-00-00"

    def _compute_record_count_helper(self):
        for record in self:
            record.record_count_helper = 1

    @api.model
    def _extract_contract_key(self, contract_no):
        text = (contract_no or "").strip()
        if not text:
            return False
        match = re.search(r"(\d{5}(?:-\d+)?)", text)
        return match.group(1) if match else text

    @api.model
    def _normalize_contract_name(self, contract_no):
        text = (contract_no or "").strip()
        if not text:
            return False
        if "/" in text and text.upper().startswith("ZFMD/"):
            return text
        contract_key = self._extract_contract_key(text)
        if not contract_key:
            return text
        return f"ZFMD/SD-{contract_key}-SH"

    @api.model
    def find_by_contract_no(self, contract_no):
        text = (contract_no or "").strip()
        if not text:
            return self.browse()
        normalized_name = self._normalize_contract_name(text)
        contract = self.search([("name", "=", normalized_name)], limit=1)
        if contract:
            return contract
        contract_key = self._extract_contract_key(text)
        if contract_key:
            contract = self.search([("contract_key", "=", contract_key)], limit=1)
        return contract

    @api.model
    def ensure_by_contract_no(self, contract_no, extra_vals=None, allow_auto_create=False):
        text = (contract_no or "").strip()
        if not text:
            return self.browse()
        contract = self.find_by_contract_no(text)
        if contract:
            if extra_vals:
                update_vals = {}
                for key, value in extra_vals.items():
                    if value and not contract[key]:
                        update_vals[key] = value
                if update_vals:
                    contract.write(update_vals)
            return contract

        if not allow_auto_create:
            return self.browse()

        normalized_name = self._normalize_contract_name(text)
        contract_key = self._extract_contract_key(text)
        next_order = (self.search([], order="display_order desc", limit=1).display_order or 0) + 1
        vals = {
            "name": normalized_name,
            "contract_key": contract_key,
            "display_order": next_order,
            "contract_name": "导入自动创建合同主档",
            "state": "draft",
            "note": f"由业务台账导入自动创建，来源合同号：{text}",
        }
        if extra_vals:
            vals.update({key: value for key, value in extra_vals.items() if value})
        return self.create(vals)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name") and not vals.get("contract_key"):
                vals["contract_key"] = self._extract_contract_key(vals["name"])
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("name") and not vals.get("contract_key"):
            vals["contract_key"] = self._extract_contract_key(vals["name"])
        return super().write(vals)

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

import re

from odoo import api, fields, models


class ZfmdContract(models.Model):
    _name = "zfmd.contract"
    _description = "销售合同"
    _inherit = [
        "mail.thread",
        "mail.activity.mixin",
        "zfmd.soft.delete.mixin",
        "zfmd.entry.confirmation.mixin",
    ]
    _rec_name = "name"
    _order = "contract_key desc, id desc"

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
    contract_name = fields.Char(string="合同名称", required=True, tracking=True)
    customer_level_1 = fields.Char(string="一级公司")
    customer_level_2 = fields.Char(string="二级公司")
    customer_level_3 = fields.Char(string="三级公司")
    partner_id = fields.Many2one("res.partner", string="客户", tracking=True)
    customer_code = fields.Char(string="客户编码", tracking=True)
    customer_code_manual = fields.Boolean(string="手动维护客户编码")
    site_id = fields.Many2one("zfmd.site", string="场站", required=True, tracking=True)
    site_other_name = fields.Char(string="其他名称")
    site_category = fields.Selection(
        [
            ("wind", "风电场"),
            ("solar", "光伏电站"),
        ],
        string="场站类别",
    )
    capacity_text = fields.Char(string="场站容量")
    contract_project_no = fields.Char(string="项目编号")
    province_name = fields.Char(string="省区", required=True, tracking=True)
    group_name = fields.Char(string="集团", required=True, tracking=True)
    product_line = fields.Char(string="产品线", required=True, tracking=True)
    project_content = fields.Text(string="项目内容", required=True)
    sale_manager = fields.Char(string="销售经理", required=True, tracking=True)
    sale_contact = fields.Char(string="销售联系人", required=True)
    contract_sign_date = fields.Date(string="合同签订日期", tracking=True)
    contract_sign_date_text = fields.Char(string="合同签订日期原文")
    archive_date = fields.Date(string="合同存档日期", required=True)
    archive_date_text = fields.Char(string="合同存档日期原文")
    archive_document_type = fields.Selection(
        [
            ("original", "原件"),
            ("copy", "复印件"),
        ],
        string="合同存档原件/复印件",
    )
    archive_copy_count = fields.Integer(string="合同存档份数")
    service_start_date = fields.Date(string="服务开始日期")
    service_start_date_text = fields.Char(string="服务开始说明")
    service_end_date = fields.Date(string="服务结束日期")
    service_end_date_text = fields.Char(string="服务结束日期原文")
    initial_fee = fields.Float(string="初装费", required=True)
    service_fee = fields.Float(string="预测服务费", required=True)
    amount_total = fields.Float(string="合同总额", required=True, tracking=True)
    amount_untaxed = fields.Float(string="不含税金额", required=True)
    exclude_sales_revenue = fields.Char(string="不算销售收入")
    exclude_sales_performance = fields.Char(string="不算销售业绩")
    bond_status = fields.Char(string="保函开具情况")
    special_contract = fields.Boolean(string="特殊合同")
    delivery_department = fields.Char(string="交付部门", required=True)
    project_manager = fields.Char(string="项目经理")
    handover_meeting_date = fields.Date(string="合同交底会时间")
    handover_meeting_date_text = fields.Char(string="合同交底会时间原文")
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
    project_management_ids = fields.One2many("zfmd.project.management", "contract_id", string="项目管理")

    project_start_count = fields.Integer(string="开工数", compute="_compute_dashboard_stats")
    service_record_count = fields.Integer(string="服务数", compute="_compute_dashboard_stats")
    invoice_record_count = fields.Integer(string="开票数", compute="_compute_dashboard_stats")
    payment_record_count = fields.Integer(string="回款数", compute="_compute_dashboard_stats")
    receivable_plan_count = fields.Integer(string="应收数", compute="_compute_dashboard_stats")
    project_management_count = fields.Integer(string="项目管理数", compute="_compute_dashboard_stats")
    invoice_total_amount = fields.Float(string="累计开票", compute="_compute_dashboard_stats")
    payment_total_amount = fields.Float(string="累计回款", compute="_compute_dashboard_stats")
    receivable_total_amount = fields.Float(string="应收余额", compute="_compute_dashboard_stats")
    receivable_paid_amount = fields.Float(string="已回款合计", compute="_compute_dashboard_stats")
    receivable_unpaid_amount = fields.Float(string="未回款合计", compute="_compute_dashboard_stats")
    collection_rate = fields.Float(string="回款率", compute="_compute_dashboard_stats")

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        for record in self:
            record._apply_partner_info(record.partner_id)
            record._apply_reference_contract_info(partner=record.partner_id)
            if not record._origin or not record._origin.customer_code:
                record.customer_code_manual = False
                if record.partner_id and record.partner_id.customer_code:
                    record.customer_code = record.partner_id.customer_code

    @api.onchange("contract_key")
    def _onchange_contract_key(self):
        for record in self:
            if record.contract_key:
                record.name = self._normalize_contract_name(record.contract_key)

    @api.onchange("customer_code")
    def _onchange_customer_code(self):
        for record in self:
            if record.customer_code != record._origin.customer_code:
                record.customer_code_manual = True

    @api.onchange("site_id")
    def _onchange_site_id(self):
        for record in self:
            site = record.site_id
            if not site:
                continue
            if site.partner_id:
                record.partner_id = site.partner_id
                record._apply_partner_info(site.partner_id)
            record.site_other_name = site.other_name or False
            record.site_category = self._normalize_site_category(site.site_category) or False
            record.capacity_text = site.capacity_text or False
            record.province_name = site.province_name or record.province_name
            record.group_name = site.group_name or record.group_name
            record._apply_reference_contract_info(site=site, partner=record.partner_id)

    def _apply_partner_info(self, partner):
        if not partner:
            return
        if not self.customer_code_manual:
            self.customer_code = partner.customer_code or False
        self.customer_level_1 = partner.customer_level_1 or False
        self.customer_level_2 = partner.customer_level_2 or False
        self.customer_level_3 = partner.customer_level_3 or False
        self.province_name = partner.province_name or self.province_name
        self.group_name = partner.group_name or self.group_name

    @api.model
    def _normalize_site_category(self, value):
        text = str(value or "").strip()
        if not text:
            return False
        if text in {"wind", "solar"}:
            return text
        if "风电" in text:
            return "wind"
        if "光伏" in text:
            return "solar"
        return False

    def _apply_reference_contract_info(self, site=None, partner=None):
        domain = []
        if site:
            domain = [("site_id", "=", site.id)]
        elif partner:
            domain = [("partner_id", "=", partner.id)]
        if not domain:
            return
        reference = self.search(domain, order="archive_date desc, id desc", limit=1)
        if not reference:
            return
        fill_fields = (
            "customer_level_1",
            "customer_level_2",
            "customer_level_3",
            "province_name",
            "group_name",
            "product_line",
            "sale_manager",
            "sale_contact",
        )
        for field_name in fill_fields:
            if not self[field_name] and reference[field_name]:
                self[field_name] = reference[field_name]

    _sql_constraints = [
        ("zfmd_contract_name_unique", "unique(name)", "合同编号必须唯一。"),
    ]

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
        match = re.search(r"(\d{5}(?:-\d+)*)", text)
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
    def _normalize_archive_document_type(self, value):
        text = str(value or "").strip()
        if not text:
            return False
        if text in {"original", "copy"}:
            return text
        if "原件" in text:
            return "original"
        if "复印" in text:
            return "copy"
        return False

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
            "contract_name": f"自动创建合同主档：{normalized_name}",
            "province_name": "待补充",
            "group_name": "待补充",
            "product_line": "待补充",
            "project_content": "自动创建合同主档",
            "sale_manager": "待补充",
            "sale_contact": "待补充",
            "archive_date": fields.Date.context_today(self),
            "initial_fee": 0.0,
            "service_fee": 0.0,
            "amount_total": 0.0,
            "amount_untaxed": 0.0,
            "delivery_department": "待补充",
            "state": "draft",
            "note": f"由业务台账导入自动创建，来源合同号：{text}",
        }
        if extra_vals:
            vals.update({key: value for key, value in extra_vals.items() if value})
        if not vals.get("site_id"):
            site = self.env["zfmd.site"].search([("name", "=", "待补充场站")], limit=1)
            if not site:
                site = self.env["zfmd.site"].create({"name": "待补充场站"})
            vals["site_id"] = site.id
        return self.create(vals)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name"):
                vals["name"] = self._normalize_contract_name(vals["name"])
                vals["contract_key"] = self._extract_contract_key(vals["name"])
            elif vals.get("contract_key"):
                vals["name"] = self._normalize_contract_name(vals["contract_key"])
            if "archive_document_type" in vals:
                vals["archive_document_type"] = self._normalize_archive_document_type(vals.get("archive_document_type"))
            if "site_category" in vals:
                vals["site_category"] = self._normalize_site_category(vals.get("site_category"))
            partner = self.env["res.partner"].browse(vals.get("partner_id"))
            vals["customer_code_manual"] = bool(
                vals.get("customer_code") and vals.get("customer_code") != partner.customer_code
            )
            if vals.get("partner_id") and not vals["customer_code_manual"]:
                vals["customer_code"] = partner.customer_code or False
        records = super().create(vals_list)
        if not self.env.context.get("skip_zfmd_sync"):
            self.env["zfmd.sync.engine"].sync_contracts(records)
        return records

    def write(self, vals):
        previous_service_keys = {
            (record.site_id.name, record.province_name)
            for record in self
            if record.site_id.name and record.province_name
        }
        vals = dict(vals)
        if vals.get("name"):
            vals["name"] = self._normalize_contract_name(vals["name"])
            vals["contract_key"] = self._extract_contract_key(vals["name"])
        elif vals.get("contract_key"):
            vals["name"] = self._normalize_contract_name(vals["contract_key"])
        if "archive_document_type" in vals:
            vals["archive_document_type"] = self._normalize_archive_document_type(vals.get("archive_document_type"))
        if "site_category" in vals:
            vals["site_category"] = self._normalize_site_category(vals.get("site_category"))
        if "customer_code" in vals and not self.env.context.get("auto_customer_code"):
            partner = (
                self.env["res.partner"].browse(vals.get("partner_id"))
                if vals.get("partner_id")
                else self[:1].partner_id
            )
            vals["customer_code_manual"] = bool(
                vals.get("customer_code") and vals.get("customer_code") != partner.customer_code
            )
        if vals.get("partner_id") and "customer_code" not in vals and not any(self.mapped("customer_code_manual")):
            vals["customer_code"] = self.env["res.partner"].browse(vals["partner_id"]).customer_code or False
        result = super().write(vals)
        if not self.env.context.get("skip_zfmd_sync"):
            self.env["zfmd.sync.engine"].sync_contracts(self, previous_service_keys=previous_service_keys)
        return result

    def unlink(self):
        service_keys = {
            (record.site_id.name, record.province_name)
            for record in self
            if record.site_id.name and record.province_name
        }
        if not self.env.context.get("force_unlink"):
            projects = (
                self.env["zfmd.project.management"]
                .with_context(include_deleted=True)
                .search(
                    [
                        ("contract_id", "in", self.ids),
                        ("is_deleted", "=", False),
                    ]
                )
            )
            projects.with_context(skip_zfmd_sync=True).unlink()
        result = super().unlink()
        self.env["zfmd.sync.engine"].refresh_service_records_by_keys(service_keys)
        return result

    def action_restore(self):
        result = super().action_restore()
        self.env["zfmd.sync.engine"].sync_contracts(self)
        return result

    @api.depends(
        "project_start_ids",
        "project_start_ids.is_deleted",
        "project_start_ids.entry_state",
        "service_record_ids",
        "service_record_ids.is_deleted",
        "service_record_ids.entry_state",
        "invoice_record_ids.invoice_amount",
        "invoice_record_ids.state",
        "invoice_record_ids.is_deleted",
        "invoice_record_ids.entry_state",
        "amount_total",
        "payment_record_ids.amount_total",
        "payment_record_ids.is_deleted",
        "payment_record_ids.entry_state",
        "receivable_plan_ids.receivable_amount",
        "receivable_plan_ids.is_deleted",
        "receivable_plan_ids.entry_state",
        "project_management_ids",
        "project_management_ids.is_deleted",
        "project_management_ids.entry_state",
    )
    def _compute_dashboard_stats(self):
        for record in self:
            project_starts = record.project_start_ids.filtered(
                lambda line: not line.is_deleted and line.entry_state == "confirmed"
            )
            service_records = record.service_record_ids.filtered(
                lambda line: not line.is_deleted and line.entry_state == "confirmed"
            )
            invoice_records = record.invoice_record_ids.filtered(
                lambda line: not line.is_deleted and line.entry_state == "confirmed"
            )
            payment_records = record.payment_record_ids.filtered(
                lambda line: not line.is_deleted and line.entry_state == "confirmed"
            )
            receivable_plans = record.receivable_plan_ids.filtered(
                lambda line: not line.is_deleted and line.entry_state == "confirmed"
            )
            project_management = record.project_management_ids.filtered(
                lambda line: not line.is_deleted and line.entry_state == "confirmed"
            )

            record.project_start_count = len(project_starts)
            record.service_record_count = len(service_records)
            record.invoice_record_count = len(invoice_records)
            record.payment_record_count = len(payment_records)
            record.receivable_plan_count = len(receivable_plans)
            record.project_management_count = len(project_management)
            record.invoice_total_amount = sum(line.invoice_amount for line in invoice_records if line.state != "cancel")
            payment_total = sum(line.amount_total for line in payment_records)
            paid_total = payment_total
            receivable_plan_total = sum(line.receivable_amount for line in receivable_plans)
            receivable_base = max(record.amount_total or 0.0, receivable_plan_total or 0.0)
            receivable_balance = max(receivable_base - paid_total, 0.0)
            record.payment_total_amount = payment_total
            record.receivable_total_amount = receivable_balance
            record.receivable_paid_amount = paid_total
            record.receivable_unpaid_amount = receivable_balance
            record.collection_rate = paid_total / receivable_base if receivable_base else 0.0

    @api.model
    def _related_record_models(self):
        return {
            "project_start": {
                "model": "zfmd.project.start",
                "action_xmlid": "zfmd_pm.action_zfmd_project_start",
                "field": "project_start_ids",
                "label": "开工申请",
            },
            "service_record": {
                "model": "zfmd.service.record",
                "action_xmlid": "zfmd_pm.action_zfmd_service_record",
                "field": "service_record_ids",
                "label": "服务记录",
            },
            "invoice_record": {
                "model": "zfmd.invoice.record",
                "action_xmlid": "zfmd_pm.action_zfmd_invoice_record",
                "field": "invoice_record_ids",
                "label": "开票记录",
            },
            "payment_record": {
                "model": "zfmd.payment.record",
                "action_xmlid": "zfmd_pm.action_zfmd_payment_record",
                "field": "payment_record_ids",
                "label": "回款记录",
            },
            "receivable_plan": {
                "model": "zfmd.receivable.plan",
                "action_xmlid": "zfmd_pm.action_zfmd_receivable_plan",
                "field": "receivable_plan_ids",
                "label": "应收计划",
            },
            "project_management": {
                "model": "zfmd.project.management",
                "action_xmlid": "zfmd_pm.action_zfmd_project_management",
                "field": "project_management_ids",
                "label": "项目管理",
            },
        }

    def _open_related_records(self, action_xmlid):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(action_xmlid)
        action["domain"] = [("contract_id", "=", self.id)]
        action["context"] = {"default_contract_id": self.id}
        return action

    def _open_related_record_kind(self, kind):
        config = self._related_record_models()[kind]
        return self._open_related_records(config["action_xmlid"])

    def action_open_project_starts(self):
        return self._open_related_record_kind("project_start")

    def action_open_service_records(self):
        return self._open_related_record_kind("service_record")

    def action_open_invoice_records(self):
        return self._open_related_record_kind("invoice_record")

    def action_open_payment_records(self):
        return self._open_related_record_kind("payment_record")

    def action_open_receivable_plans(self):
        return self._open_related_record_kind("receivable_plan")

    def action_open_project_management(self):
        return self._open_related_record_kind("project_management")

from odoo import api, fields, models


class ZfmdDashboard(models.Model):
    _name = "zfmd.dashboard"
    _description = "Project Management Dashboard"

    name = fields.Char(string="名称", default="项目管理看板", required=True)
    contract_total_count = fields.Integer(string="合同总数", compute="_compute_metrics")
    contract_running_count = fields.Integer(string="执行中合同数", compute="_compute_metrics")
    project_start_total_count = fields.Integer(string="开工申请数", compute="_compute_metrics")
    service_total_count = fields.Integer(string="服务记录数", compute="_compute_metrics")
    service_overdue_count = fields.Integer(string="超期服务数", compute="_compute_metrics")
    invoice_total_amount = fields.Float(string="累计开票金额", compute="_compute_metrics")
    payment_total_amount = fields.Float(string="累计回款金额", compute="_compute_metrics")
    receivable_total_amount = fields.Float(string="应收总额", compute="_compute_metrics")
    receivable_due_amount = fields.Float(string="到期应收余额", compute="_compute_metrics")
    receivable_unpaid_amount = fields.Float(string="未回款余额", compute="_compute_metrics")
    collection_rate = fields.Float(string="回款率", compute="_compute_metrics")

    running_contract_ids = fields.Many2many(
        "zfmd.contract", compute="_compute_relations", string="执行中合同明细"
    )
    overdue_service_ids = fields.Many2many(
        "zfmd.service.record", compute="_compute_relations", string="超期服务列表"
    )
    due_receivable_ids = fields.Many2many(
        "zfmd.receivable.plan", compute="_compute_relations", string="到期应收列表"
    )
    recent_invoice_ids = fields.Many2many(
        "zfmd.invoice.record", compute="_compute_relations", string="最近开票列表"
    )
    recent_payment_ids = fields.Many2many(
        "zfmd.payment.record", compute="_compute_relations", string="最近回款列表"
    )

    @api.depends("name")
    def _compute_metrics(self):
        contract_model = self.env["zfmd.contract"]
        start_model = self.env["zfmd.project.start"]
        service_model = self.env["zfmd.service.record"]
        invoice_model = self.env["zfmd.invoice.record"]
        payment_model = self.env["zfmd.payment.record"]
        receivable_model = self.env["zfmd.receivable.plan"]

        contract_total_count = contract_model.search_count([])
        contract_running_count = contract_model.search_count([("state", "=", "running")])
        project_start_total_count = start_model.search_count([])
        service_total_count = service_model.search_count([])
        service_overdue_count = service_model.search_count([("is_overdue", "=", True)])

        invoices = invoice_model.search([("state", "!=", "cancel")])
        payments = payment_model.search([])
        receivables = receivable_model.search([("is_summary_line", "=", False)])
        due_receivables = receivable_model.search(
            [("state", "in", ["due", "partial"]), ("is_summary_line", "=", False)]
        )

        invoice_total_amount = sum(invoices.mapped("invoice_amount"))
        payment_total_amount = sum(payments.mapped("amount_total"))
        receivable_total_amount = sum(receivables.mapped("receivable_amount"))
        receivable_due_amount = sum(due_receivables.mapped("receivable_amount")) - sum(
            due_receivables.mapped("actual_payment_amount")
        )
        receivable_unpaid_amount = receivable_total_amount - sum(
            receivables.mapped("actual_payment_amount")
        )
        collection_rate = (
            payment_total_amount / receivable_total_amount * 100.0
            if receivable_total_amount
            else 0.0
        )

        for record in self:
            record.contract_total_count = contract_total_count
            record.contract_running_count = contract_running_count
            record.project_start_total_count = project_start_total_count
            record.service_total_count = service_total_count
            record.service_overdue_count = service_overdue_count
            record.invoice_total_amount = invoice_total_amount
            record.payment_total_amount = payment_total_amount
            record.receivable_total_amount = receivable_total_amount
            record.receivable_due_amount = max(receivable_due_amount, 0.0)
            record.receivable_unpaid_amount = max(receivable_unpaid_amount, 0.0)
            record.collection_rate = collection_rate

    @api.depends("name")
    def _compute_relations(self):
        running_contracts = self.env["zfmd.contract"].search(
            [("state", "=", "running")], limit=10
        )
        overdue_services = self.env["zfmd.service.record"].search(
            [("is_overdue", "=", True)], order="service_end_date asc", limit=10
        )
        due_receivables = self.env["zfmd.receivable.plan"].search(
            [("state", "in", ["due", "partial"]), ("is_summary_line", "=", False)],
            order="receivable_date asc",
            limit=10,
        )
        recent_invoices = self.env["zfmd.invoice.record"].search(
            [], order="invoice_date desc, id desc", limit=10
        )
        recent_payments = self.env["zfmd.payment.record"].search(
            [], order="payment_date desc, id desc", limit=10
        )
        for record in self:
            record.running_contract_ids = running_contracts
            record.overdue_service_ids = overdue_services
            record.due_receivable_ids = due_receivables
            record.recent_invoice_ids = recent_invoices
            record.recent_payment_ids = recent_payments

    def action_open_running_contracts(self):
        action = self.env["ir.actions.actions"]._for_xml_id("zfmd_pm.action_zfmd_contract")
        action["domain"] = [("state", "=", "running")]
        return action

    def action_open_project_starts(self):
        return self.env["ir.actions.actions"]._for_xml_id("zfmd_pm.action_zfmd_project_start")

    def action_open_overdue_services(self):
        action = self.env["ir.actions.actions"]._for_xml_id("zfmd_pm.action_zfmd_service_record")
        action["domain"] = [("is_overdue", "=", True)]
        return action

    def action_open_invoices(self):
        return self.env["ir.actions.actions"]._for_xml_id("zfmd_pm.action_zfmd_invoice_record")

    def action_open_payments(self):
        return self.env["ir.actions.actions"]._for_xml_id("zfmd_pm.action_zfmd_payment_record")

    def action_open_due_receivables(self):
        action = self.env["ir.actions.actions"]._for_xml_id("zfmd_pm.action_zfmd_receivable_plan")
        action["domain"] = [("state", "in", ["due", "partial"]), ("is_summary_line", "=", False)]
        return action

from odoo import api, fields, models


class ZfmdWarningEvent(models.Model):
    _name = "zfmd.warning.event"
    _description = "预警事件"
    _inherit = ["zfmd.soft.delete.mixin"]
    _order = "warning_level desc, generated_at desc, id desc"

    name = fields.Char(string="预警标题", required=True)
    rule_id = fields.Many2one("zfmd.warning.rule", string="预警规则", ondelete="set null")
    rule_type = fields.Selection(
        [
            ("invoice_payment_due", "预计回款逾期"),
            ("invoice_receivable_balance", "开票应收余额"),
            ("invoice_aging", "账龄超期"),
        ],
        string="规则类型",
    )
    warning_level = fields.Selection(
        [
            ("info", "提示"),
            ("warning", "一般"),
            ("danger", "严重"),
        ],
        string="预警等级",
        default="warning",
    )
    state = fields.Selection(
        [
            ("open", "未处理"),
            ("processing", "跟进中"),
            ("postponed", "已确认延期"),
            ("done", "已处理"),
            ("ignored", "无需处理"),
        ],
        string="处理状态",
        default="open",
    )
    invoice_id = fields.Many2one("zfmd.invoice.record", string="关联开票记录", ondelete="set null")
    contract_id = fields.Many2one("zfmd.contract", string="关联合同", ondelete="set null")
    partner_name = fields.Char(string="客户/付款单位")
    sale_manager = fields.Char(string="销售经理")
    invoice_date = fields.Date(string="开票日期")
    invoice_amount = fields.Float(string="开票金额（元）")
    promised_payment_date = fields.Date(string="预计回款日期")
    promised_payment_amount = fields.Float(string="预计回款金额（元）")
    actual_payment_amount = fields.Float(string="实际回款金额（元）")
    receivable_balance = fields.Float(string="应收余额（元）")
    aging_days = fields.Integer(string="账龄天数")
    message = fields.Text(string="预警说明")
    generated_at = fields.Datetime(string="生成时间", default=fields.Datetime.now)

    def action_set_processing(self):
        self.write({"state": "processing"})

    def action_set_postponed(self):
        self.write({"state": "postponed"})

    def action_set_done(self):
        self.write({"state": "done"})

    def action_set_ignored(self):
        self.write({"state": "ignored"})

    def action_reopen(self):
        self.write({"state": "open"})

    @api.model
    def recompute_warning_events(self):
        today = fields.Date.today()
        active_states = ["open", "processing", "postponed"]
        self.env["zfmd.invoice.record"].sudo().search([("entry_state", "=", "confirmed")]).with_context(
            force_state_auto=True
        ).action_recompute_state_from_payment()

        # 清理孤立预警：关联开票记录已被删除（invoice_id 被置 null）
        self.sudo().search([("invoice_id", "=", False)]).with_context(force_unlink=True).unlink()

        # 自动关闭已回款或已作废开票对应的活跃预警
        paid_invoice_ids = (
            self.env["zfmd.invoice.record"]
            .search(
                [
                    ("entry_state", "=", "confirmed"),
                    ("state", "in", ["paid", "cancel"]),
                ]
            )
            .ids
        )
        if paid_invoice_ids:
            self.sudo().search(
                [
                    ("invoice_id", "in", paid_invoice_ids),
                    ("state", "in", active_states),
                ]
            ).write({"state": "done"})

        rules = self.env["zfmd.warning.rule"].search([("active", "=", True)])
        invoices = self.env["zfmd.invoice.record"].search(
            [
                ("entry_state", "=", "confirmed"),
                ("state", "not in", ["paid", "cancel"]),
            ]
        )
        for rule in rules:
            if rule.rule_type == "invoice_payment_due":
                self._process_payment_due(rule, invoices, today)
            elif rule.rule_type == "invoice_receivable_balance":
                self._process_receivable_balance(rule, invoices, today)
            elif rule.rule_type == "invoice_aging":
                self._process_aging(rule, invoices, today)
        return True

    def _upsert(self, rule, invoice, vals):
        all_existing = self.search([("rule_id", "=", rule.id), ("invoice_id", "=", invoice.id)])
        if all_existing:
            active = all_existing.filtered(lambda e: e.state not in ("done", "ignored"))
            if active:
                active.write(vals)
        else:
            self.create(vals)

    def _base_vals(self, rule, invoice):
        balance = invoice.receivable_balance or 0.0
        return {
            "rule_id": rule.id,
            "rule_type": rule.rule_type,
            "warning_level": rule.warning_level,
            "invoice_id": invoice.id,
            "contract_id": invoice.contract_id.id or False,
            "partner_name": invoice.invoice_partner_name or False,
            "sale_manager": invoice.sale_manager or False,
            "invoice_date": invoice.invoice_date or False,
            "invoice_amount": invoice.invoice_amount or 0.0,
            "promised_payment_date": invoice.promised_payment_date or False,
            "promised_payment_amount": invoice.promised_payment_amount or 0.0,
            "actual_payment_amount": invoice.actual_payment_amount or 0.0,
            "receivable_balance": balance,
            "generated_at": fields.Datetime.now(),
        }

    def _process_payment_due(self, rule, invoices, today):
        threshold_days = rule.threshold_days or 0
        for invoice in invoices:
            if not invoice.promised_payment_date:
                continue
            if invoice.promised_payment_date >= today:
                continue
            actual = invoice.actual_payment_amount or 0.0
            promised = invoice.promised_payment_amount or 0.0
            if promised and actual >= promised and (invoice.receivable_balance or 0.0) <= 0:
                continue
            balance = invoice.receivable_balance or 0.0
            if balance <= 0:
                continue
            aging = (today - invoice.promised_payment_date).days
            if aging < threshold_days:
                continue
            vals = self._base_vals(rule, invoice)
            vals["name"] = f"回款逾期预警：{invoice.name}"
            vals["aging_days"] = aging
            vals["message"] = f"预计回款已逾期 {aging} 天，未回款金额 {balance:,.2f} 元。"
            self._upsert(rule, invoice, vals)

    def _process_receivable_balance(self, rule, invoices, today):
        threshold = rule.threshold_amount or 0.0
        for invoice in invoices:
            balance = invoice.receivable_balance or 0.0
            if balance <= threshold:
                continue
            vals = self._base_vals(rule, invoice)
            vals["name"] = f"应收余额预警：{invoice.name}"
            vals["message"] = f"当前应收余额 {balance:,.2f} 元。"
            self._upsert(rule, invoice, vals)

    def _process_aging(self, rule, invoices, today):
        threshold_days = rule.threshold_days or 0
        for invoice in invoices:
            if not invoice.invoice_date:
                continue
            balance = invoice.receivable_balance or 0.0
            if balance <= 0:
                continue
            aging = (today - invoice.invoice_date).days
            if aging < threshold_days:
                continue
            vals = self._base_vals(rule, invoice)
            vals["name"] = f"账龄超期预警：{invoice.name}"
            vals["aging_days"] = aging
            vals["message"] = f"开票后 {aging} 天仍未结清，应收余额 {balance:,.2f} 元。"
            self._upsert(rule, invoice, vals)

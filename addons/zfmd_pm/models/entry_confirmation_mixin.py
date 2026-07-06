from odoo import fields, models

_ENTRY_CONFIRMATION_FIELDS = {"entry_state", "confirmed_at", "confirmed_by"}
_TECHNICAL_FIELDS = {
    "message_follower_ids",
    "message_ids",
    "activity_ids",
    "message_main_attachment_id",
    "access_token",
}


class ZfmdEntryConfirmationMixin(models.AbstractModel):
    _name = "zfmd.entry.confirmation.mixin"
    _description = "ZFMD 录入确认接口"

    entry_state = fields.Selection(
        [("draft", "待确认"), ("confirmed", "已确认")],
        string="录入状态",
        default="confirmed",
        required=True,
        index=True,
        tracking=True,
        copy=False,
    )
    confirmed_at = fields.Datetime(string="确认时间", readonly=True, copy=False)
    confirmed_by = fields.Many2one("res.users", string="确认人", readonly=True, copy=False)

    def _is_manual_confirmation_write(self, vals):
        if self.env.context.get("skip_zfmd_sync") or self.env.context.get("skip_entry_confirmation_stage"):
            return False
        changed_fields = set(vals) - _ENTRY_CONFIRMATION_FIELDS - _TECHNICAL_FIELDS
        if not changed_fields:
            return False
        return any(record.entry_state == "confirmed" for record in self)

    def write(self, vals):
        vals = dict(vals)
        if self._is_manual_confirmation_write(vals):
            vals.update(
                {
                    "entry_state": "draft",
                    "confirmed_at": False,
                    "confirmed_by": False,
                }
            )
        return super().write(vals)

    def action_confirm_entry(self):
        drafts = self.filtered(lambda record: record.entry_state != "confirmed")
        if not drafts:
            return self._confirmation_notification("无需重复确认", "当前记录已经是已确认状态。", "warning")
        drafts.with_context(skip_zfmd_sync=True).write(
            {
                "entry_state": "confirmed",
                "confirmed_at": fields.Datetime.now(),
                "confirmed_by": self.env.user.id,
            }
        )
        drafts._apply_confirmed_entry()
        return self._confirmation_notification("确认成功", f"已确认生效 {len(drafts)} 条记录。", "success")

    def _confirmation_notification(self, title, message, notification_type):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": title,
                "message": message,
                "type": notification_type,
                "sticky": False,
                "next": {"type": "ir.actions.client", "tag": "reload"},
            },
        }

    def _apply_confirmed_entry(self):
        engine = self.env["zfmd.sync.engine"]
        if self._name == "zfmd.contract":
            engine.sync_contracts(self)
        elif self._name == "zfmd.project.management":
            engine.sync_projects_to_contracts(self, set(self._fields))
            engine.refresh_projects({record.contract_id.name or record.name for record in self})
        elif self._name == "zfmd.invoice.record":
            engine.refresh_from_invoices(engine._contract_numbers(self))
        elif self._name == "zfmd.payment.record":
            engine.refresh_from_payments(engine._contract_numbers(self))
        elif self._name == "zfmd.receivable.plan":
            engine.refresh_from_receivables(engine._contract_numbers(self))
        elif self._name == "zfmd.site":
            engine.sync_contracts(self.contract_ids)
        return True

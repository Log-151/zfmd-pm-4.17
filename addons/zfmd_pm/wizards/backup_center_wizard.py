from datetime import timedelta

from odoo.exceptions import AccessError, ValidationError

from odoo import _, fields, models


class ZfmdBackupCenterWizard(models.TransientModel):
    _name = "zfmd.backup.center.wizard"
    _description = "ZFMD 备份中心"

    database_name = fields.Char(string="当前数据库", readonly=True)
    storage_path = fields.Char(string="备份保存位置", readonly=True)
    last_backup_id = fields.Many2one("zfmd.backup.record", string="最近一次备份", readonly=True)
    last_backup_state = fields.Selection(related="last_backup_id.state", string="最近状态", readonly=True)
    last_backup_at = fields.Datetime(related="last_backup_id.completed_at", string="完成时间", readonly=True)
    last_backup_size = fields.Char(related="last_backup_id.file_size_display", string="文件大小", readonly=True)
    last_error = fields.Text(related="last_backup_id.error_message", string="失败原因", readonly=True)
    last_system_backup_id = fields.Many2one("zfmd.backup.record", string="最近系统备份", readonly=True)
    last_system_state = fields.Selection(related="last_system_backup_id.state", string="系统备份状态", readonly=True)
    last_system_at = fields.Datetime(
        related="last_system_backup_id.completed_at",
        string="系统备份时间",
        readonly=True,
    )
    last_system_size = fields.Char(
        related="last_system_backup_id.file_size_display",
        string="系统备份大小",
        readonly=True,
    )
    last_excel_backup_id = fields.Many2one("zfmd.backup.record", string="最近 Excel 备份", readonly=True)
    last_excel_state = fields.Selection(related="last_excel_backup_id.state", string="Excel 备份状态", readonly=True)
    last_excel_at = fields.Datetime(
        related="last_excel_backup_id.completed_at",
        string="Excel 备份时间",
        readonly=True,
    )
    last_excel_size = fields.Char(
        related="last_excel_backup_id.file_size_display",
        string="Excel 备份大小",
        readonly=True,
    )
    backup_ids = fields.Many2many("zfmd.backup.record", string="最近备份", readonly=True)
    excel_total_count = fields.Integer(string="Excel 业务记录总数", readonly=True)
    contract_count = fields.Integer(string="合同台账", readonly=True)
    project_start_count = fields.Integer(string="开工申请", readonly=True)
    service_record_count = fields.Integer(string="服务记录", readonly=True)
    invoice_record_count = fields.Integer(string="开票登记", readonly=True)
    payment_record_count = fields.Integer(string="回款登记", readonly=True)
    receivable_plan_count = fields.Integer(string="应收计划", readonly=True)
    project_management_count = fields.Integer(string="项目管理", readonly=True)
    after_sale_service_count = fields.Integer(string="售后服务", readonly=True)

    schedule_enabled = fields.Boolean(string="启用定期备份")
    schedule_mode = fields.Selection(
        [
            ("system_zip", "仅系统恢复包"),
            ("business_xlsx", "仅 Excel 业务快照"),
            ("both", "系统恢复包 + Excel"),
        ],
        string="定时备份内容",
        default="both",
        required=True,
    )
    interval_number = fields.Integer(string="每隔", default=1, required=True)
    interval_type = fields.Selection(
        [
            ("hours", "小时"),
            ("days", "天"),
            ("weeks", "周"),
            ("months", "月"),
        ],
        string="周期单位",
        default="days",
        required=True,
    )
    next_run = fields.Datetime(string="下次执行时间")
    retention_count = fields.Integer(string="保留最近备份", default=7, required=True)

    def _check_backup_manager(self):
        if not (
            self.env.is_superuser()
            or self.env.user.has_group("base.group_system")
            or self.env.user.has_group("zfmd_pm.group_zfmd_backup_manager")
        ):
            raise AccessError(_("您没有访问备份中心的权限，请联系管理员开通备份管理权限。"))

    def default_get(self, fields_list):
        self._check_backup_manager()
        values = super().default_get(fields_list)
        backup_model = self.env["zfmd.backup.record"]
        backups = backup_model.search([], order="started_at desc, id desc", limit=10)
        last_backup = backups[:1]
        last_system_backup = backup_model.search(
            [("backup_format", "=", "system_zip")],
            order="started_at desc, id desc",
            limit=1,
        )
        last_excel_backup = backup_model.search(
            [("backup_format", "=", "business_xlsx")],
            order="started_at desc, id desc",
            limit=1,
        )
        cron = self.env.ref("zfmd_pm.ir_cron_zfmd_system_backup", raise_if_not_found=False)
        if cron:
            cron = cron.sudo()
        retention_count = backup_model._retention_count()
        next_run = cron.nextcall if cron else False
        if not next_run or next_run <= fields.Datetime.now():
            next_run = fields.Datetime.now() + timedelta(days=1)
        count_fields = {
            "zfmd.contract": "contract_count",
            "zfmd.project.start": "project_start_count",
            "zfmd.service.record": "service_record_count",
            "zfmd.invoice.record": "invoice_record_count",
            "zfmd.payment.record": "payment_record_count",
            "zfmd.receivable.plan": "receivable_plan_count",
            "zfmd.project.management": "project_management_count",
            "zfmd.after.sale.service": "after_sale_service_count",
        }
        business_counts = {}
        for model_name, field_name in count_fields.items():
            business_counts[field_name] = (
                self.env[model_name].sudo().with_context(include_deleted=True, active_test=False).search_count([])
            )
        values.update(
            {
                "database_name": self.env.cr.dbname,
                "storage_path": backup_model._backup_root(),
                "last_backup_id": last_backup.id if last_backup else False,
                "last_system_backup_id": (last_system_backup.id if last_system_backup else False),
                "last_excel_backup_id": (last_excel_backup.id if last_excel_backup else False),
                "backup_ids": [(6, 0, backups.ids)],
                "schedule_enabled": bool(cron and cron.active),
                "schedule_mode": backup_model._scheduled_mode(),
                "interval_number": cron.interval_number if cron else 1,
                "interval_type": cron.interval_type if cron else "days",
                "next_run": next_run,
                "retention_count": retention_count,
                "excel_total_count": sum(business_counts.values()),
                **business_counts,
            }
        )
        return values

    def _reopen_action(self):
        action = self.env.ref("zfmd_pm.action_zfmd_backup_center_wizard").sudo().read()[0]
        action.pop("res_id", None)
        return action

    def action_backup_now(self):
        self._check_backup_manager()
        self.ensure_one()
        backup = self.env["zfmd.backup.record"].create_backup(backup_type="manual")
        if backup.state == "done":
            message = _("备份已完成：%s（%s）") % (
                backup.file_name,
                backup.file_size_display,
            )
            notification_type = "success"
        else:
            message = _("备份失败：%s") % (backup.error_message or _("请查看服务器日志。"))
            notification_type = "danger"
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("系统备份"),
                "message": message,
                "type": notification_type,
                "sticky": backup.state != "done",
                "next": self._reopen_action(),
            },
        }

    def action_excel_backup_now(self):
        self._check_backup_manager()
        self.ensure_one()
        backup = self.env["zfmd.backup.record"].create_excel_backup(backup_type="manual")
        if backup.state == "done":
            message = _("Excel 快照已生成：%s（%s，共 %s 条业务记录）") % (
                backup.file_name,
                backup.file_size_display,
                backup.record_count,
            )
            notification_type = "success"
        else:
            message = _("Excel 快照失败：%s") % (backup.error_message or _("请查看服务器日志。"))
            notification_type = "danger"
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Excel 业务备份"),
                "message": message,
                "type": notification_type,
                "sticky": backup.state != "done",
                "next": self._reopen_action(),
            },
        }

    def action_save_schedule(self):
        self._check_backup_manager()
        self.ensure_one()
        if self.interval_number < 1:
            raise ValidationError(_("备份周期必须大于或等于 1。"))
        if not 1 <= self.retention_count <= 100:
            raise ValidationError(_("备份保留份数必须在 1 到 100 之间。"))
        if self.schedule_enabled:
            if not self.next_run:
                raise ValidationError(_("启用定期备份时必须设置下次执行时间。"))
            if self.next_run <= fields.Datetime.now():
                raise ValidationError(_("下次执行时间必须晚于当前时间。"))

        cron = self.env.ref("zfmd_pm.ir_cron_zfmd_system_backup").sudo()
        cron_values = {
            "active": self.schedule_enabled,
            "interval_number": self.interval_number,
            "interval_type": self.interval_type,
        }
        if self.next_run:
            cron_values["nextcall"] = self.next_run
        cron.write(cron_values)
        (self.env["ir.config_parameter"].sudo().set_param("zfmd_pm.backup_retention_count", self.retention_count))
        (self.env["ir.config_parameter"].sudo().set_param("zfmd_pm.backup_schedule_mode", self.schedule_mode))
        self.env["zfmd.backup.record"]._cleanup_old_backups()
        message = (
            _("定期备份已启用，下次执行时间为 %s。") % fields.Datetime.to_string(self.next_run)
            if self.schedule_enabled
            else _("定期备份已关闭，保留策略已保存。")
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("备份设置"),
                "message": message,
                "type": "success",
                "next": self._reopen_action(),
            },
        }

    def action_open_backup_history(self):
        self._check_backup_manager()
        return self.env.ref("zfmd_pm.action_zfmd_backup_record").sudo().read()[0]

    def _open_action(self, xmlid):
        return self.env.ref(xmlid).sudo().read()[0]

    def action_open_contracts(self):
        self._check_backup_manager()
        return self._open_action("zfmd_pm.action_zfmd_contract")

    def action_open_project_starts(self):
        self._check_backup_manager()
        return self._open_action("zfmd_pm.action_zfmd_project_start")

    def action_open_service_records(self):
        self._check_backup_manager()
        return self._open_action("zfmd_pm.action_zfmd_service_record")

    def action_open_invoices(self):
        self._check_backup_manager()
        return self._open_action("zfmd_pm.action_zfmd_invoice_record")

    def action_open_payments(self):
        self._check_backup_manager()
        return self._open_action("zfmd_pm.action_zfmd_payment_record")

    def action_open_receivables(self):
        self._check_backup_manager()
        return self._open_action("zfmd_pm.action_zfmd_receivable_plan")

import base64
from datetime import date

from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.osv import expression


class ZfmdPaymentPeriodExportWizard(models.TransientModel):
    _name = "zfmd.payment.period.export.wizard"
    _description = "回款月/季度导出"

    period_type = fields.Selection(
        [("month", "按月导出"), ("quarter", "按季度导出")],
        string="导出类型",
        default="month",
        required=True,
    )
    year = fields.Integer(string="年份", required=True, default=lambda self: fields.Date.today().year)
    month = fields.Selection(
        [(str(i), f"{i}月") for i in range(1, 13)],
        string="月份",
        default=lambda self: str(fields.Date.today().month),
    )
    quarter = fields.Selection(
        [("1", "第一季度"), ("2", "第二季度"), ("3", "第三季度"), ("4", "第四季度")],
        string="季度",
        default=lambda self: str(((fields.Date.today().month - 1) // 3) + 1),
    )
    matched_count = fields.Integer(string="匹配记录数", readonly=True, compute="_compute_matched_count")
    period_label = fields.Char(string="导出区间", readonly=True, compute="_compute_period_label")
    export_note = fields.Html(string="导出说明", readonly=True, sanitize=False, compute="_compute_export_note")

    def _get_period_range(self):
        self.ensure_one()
        if not self.year or self.year < 2000:
            raise UserError(_("请填写正确的年份。"))

        if self.period_type == "month":
            month = int(self.month or 0)
            if month < 1 or month > 12:
                raise UserError(_("请选择正确的月份。"))
            start_date = date(self.year, month, 1)
            if month == 12:
                end_date = date(self.year + 1, 1, 1)
            else:
                end_date = date(self.year, month + 1, 1)
            label = f"{self.year}年{month}月"
            return start_date, end_date, label

        quarter = int(self.quarter or 0)
        if quarter < 1 or quarter > 4:
            raise UserError(_("请选择正确的季度。"))
        start_month = (quarter - 1) * 3 + 1
        start_date = date(self.year, start_month, 1)
        if quarter == 4:
            end_date = date(self.year + 1, 1, 1)
        else:
            end_date = date(self.year, start_month + 3, 1)
        label = f"{self.year}年Q{quarter}"
        return start_date, end_date, label

    def _get_domain(self):
        start_date, end_date, _label = self._get_period_range()
        period_domain = [
            ("payment_date", ">=", start_date),
            ("payment_date", "<", end_date),
        ]
        active_domain = self.env.context.get("active_domain") or self.env.context.get("domain") or []
        return expression.AND([active_domain, period_domain])

    def _get_records(self):
        return self.env["zfmd.payment.record"].search(self._get_domain(), order="payment_date asc, id asc")

    def _compute_matched_count(self):
        for wizard in self:
            wizard.matched_count = len(wizard._get_records()) if wizard.year else 0

    def _compute_period_label(self):
        for wizard in self:
            if wizard.year:
                _start, _end, label = wizard._get_period_range()
                wizard.period_label = label
            else:
                wizard.period_label = False

    def _compute_export_note(self):
        for wizard in self:
            wizard.export_note = "\n".join(
                [
                    "<div>",
                    "<p><strong>导出内容：</strong>按所选月份或季度导出当前区间内的全部回款明细。</p>",
                    "<p><strong>用途建议：</strong>月度导出用于财务对账，季度导出用于提成核算。</p>",
                    “<p><strong>金额单位：</strong>所有金额字段统一按”元”导出。</p>”,
                    "</div>",
                ]
            )

    def action_export(self):
        self.ensure_one()
        records = self._get_records()
        if not records:
            raise UserError(_("当前所选区间没有回款记录，无法导出。"))

        file_content, default_name = records._build_export_xlsx(records)
        _start, _end, label = self._get_period_range()
        file_name = f"回款登记_{label}.xlsx"
        attachment = self.env["ir.attachment"].create(
            {
                "name": file_name or default_name,
                "type": "binary",
                "datas": base64.b64encode(file_content),
                "res_model": self._name,
                "res_id": self.id,
                "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            }
        )
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download=1",
            "target": "self",
        }

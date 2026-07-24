import json

from odoo.http import content_disposition, request

from odoo import http


class ZfmdExportController(http.Controller):
    _ALLOWED_MODELS = {
        "zfmd.contract",
        "zfmd.project.start",
        "zfmd.service.record",
        "zfmd.invoice.record",
        "zfmd.payment.record",
        "zfmd.receivable.plan",
        "zfmd.project.management",
        "zfmd.after.sale.service",
    }

    @http.route("/zfmd_pm/export_xlsx", type="http", auth="user")
    def export_xlsx(self, model=None, ids=None, domain=None, **kwargs):
        if model not in self._ALLOWED_MODELS:
            return request.not_found()

        records = request.env[model]
        records.check_access_rights("read")
        if not hasattr(records, "_build_export_xlsx"):
            return request.not_found()

        if ids:
            try:
                record_ids = [int(item) for item in ids.split(",") if item.strip()]
            except ValueError:
                return request.not_found()
            records = records.browse(record_ids).exists()
            records.check_access_rule("read")
        elif domain:
            try:
                parsed_domain = json.loads(domain)
            except Exception:
                return request.not_found()
            if not isinstance(parsed_domain, list):
                return request.not_found()
            records = records.search(parsed_domain)
        else:
            records = records.search([])

        content, filename = records._build_export_xlsx(records)
        return request.make_response(
            content,
            headers=[
                ("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
                ("Content-Disposition", content_disposition(filename)),
                ("Cache-Control", "no-store"),
                ("X-Content-Type-Options", "nosniff"),
            ],
        )

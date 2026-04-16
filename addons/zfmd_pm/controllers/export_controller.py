from odoo import http
from odoo.http import request, content_disposition


class ZfmdExportController(http.Controller):
    @http.route("/zfmd_pm/export_xlsx", type="http", auth="user")
    def export_xlsx(self, model=None, ids=None, **kwargs):
        if not model:
            return request.not_found()

        records = request.env[model]
        if not hasattr(records, "_build_export_xlsx"):
            return request.not_found()

        if ids:
            record_ids = [int(item) for item in ids.split(",") if item.strip()]
            records = records.browse(record_ids).exists()
        else:
            records = records.search([])

        content, filename = records._build_export_xlsx(records)
        return request.make_response(
            content,
            headers=[
                ("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
                ("Content-Disposition", content_disposition(filename)),
            ],
        )

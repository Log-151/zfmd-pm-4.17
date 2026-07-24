import os

from odoo.http import Response, content_disposition, request

from odoo import http


class ZfmdBackupController(http.Controller):
    @http.route(
        "/zfmd_pm/backup/<int:backup_id>/download",
        type="http",
        auth="user",
        methods=["GET"],
    )
    def download_backup(self, backup_id, **kwargs):
        if not (
            request.env.user.has_group("base.group_system")
            or request.env.user.has_group("zfmd_pm.group_zfmd_backup_manager")
        ):
            return request.not_found()

        backup_model = request.env["zfmd.backup.record"]
        backup = backup_model.sudo().browse(backup_id).exists()
        backup_root = os.path.realpath(backup_model._backup_root())
        real_path = os.path.realpath(backup.file_path) if backup and backup.file_path else ""
        if (
            not backup
            or backup.database_name != request.env.cr.dbname
            or backup.state != "done"
            or not backup.file_path
            or os.path.commonpath([backup_root, real_path]) != backup_root
            or not os.path.isfile(real_path)
        ):
            return request.not_found()

        stream = open(real_path, "rb")
        content_type = (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            if backup.backup_format == "business_xlsx"
            else "application/zip"
        )
        response = Response(
            stream,
            headers=[
                ("Content-Type", content_type),
                ("Content-Disposition", content_disposition(backup.file_name)),
                ("Content-Length", str(os.path.getsize(real_path))),
                ("Cache-Control", "no-store"),
                ("X-Content-Type-Options", "nosniff"),
            ],
            direct_passthrough=True,
        )
        response.call_on_close(stream.close)
        return response

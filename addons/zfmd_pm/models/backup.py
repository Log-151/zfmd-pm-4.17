import json
import logging
import os
import re
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone

import xlsxwriter
from odoo.exceptions import AccessError, UserError
from odoo.service.db import dump_db_manifest, exec_pg_environ, find_pg_tool
from odoo.tools import config

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)
_BACKUP_LOCK_ID = 6041701


class ZfmdBackupRecord(models.Model):
    _name = "zfmd.backup.record"
    _description = "ZFMD 系统备份"
    _order = "started_at desc, id desc"

    name = fields.Char(string="备份名称", required=True, readonly=True)
    backup_type = fields.Selection(
        [("manual", "手动备份"), ("scheduled", "定时备份")],
        string="备份方式",
        required=True,
        readonly=True,
    )
    backup_format = fields.Selection(
        [
            ("system_zip", "系统恢复包"),
            ("business_xlsx", "Excel 业务快照"),
        ],
        string="备份内容",
        required=True,
        default="system_zip",
        readonly=True,
    )
    state = fields.Selection(
        [
            ("running", "进行中"),
            ("done", "成功"),
            ("failed", "失败"),
        ],
        string="状态",
        required=True,
        default="running",
        readonly=True,
    )
    database_name = fields.Char(string="数据库", required=True, readonly=True)
    started_at = fields.Datetime(string="开始时间", required=True, readonly=True)
    completed_at = fields.Datetime(string="完成时间", readonly=True)
    file_name = fields.Char(string="文件名", readonly=True)
    file_path = fields.Char(string="服务器路径", readonly=True, groups="base.group_system")
    file_size = fields.Integer(string="文件大小（字节）", readonly=True)
    file_size_display = fields.Char(string="文件大小", compute="_compute_file_size_display")
    record_count = fields.Integer(string="业务记录数", readonly=True)
    error_message = fields.Text(string="错误信息", readonly=True)

    @api.depends("file_size")
    def _compute_file_size_display(self):
        for record in self:
            record.file_size_display = record._format_size(record.file_size)

    @api.model
    def _format_size(self, size):
        value = float(size or 0)
        units = ["B", "KB", "MB", "GB", "TB"]
        for unit in units:
            if value < 1024 or unit == units[-1]:
                return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
            value /= 1024
        return "0 B"

    @api.model
    def _backup_root(self):
        safe_db_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", self.env.cr.dbname)
        return os.path.join(config["data_dir"], "backups", "zfmd_pm", safe_db_name)

    @api.model
    def _check_backup_manager(self):
        if not (
            self.env.is_superuser()
            or self.env.user.has_group("base.group_system")
            or self.env.user.has_group("zfmd_pm.group_zfmd_backup_manager")
        ):
            raise AccessError(_("您没有执行备份操作的权限。"))

    @api.model
    def _retention_count(self):
        value = self.env["ir.config_parameter"].sudo().get_param("zfmd_pm.backup_retention_count", "7")
        try:
            return max(1, min(int(value), 100))
        except (TypeError, ValueError):
            return 7

    @api.model
    def _scheduled_mode(self):
        mode = self.env["ir.config_parameter"].sudo().get_param("zfmd_pm.backup_schedule_mode", "both")
        return mode if mode in ("system_zip", "business_xlsx", "both") else "both"

    @api.model
    def _acquire_backup_lock(self):
        self.env.cr.execute("SELECT pg_try_advisory_xact_lock(%s)", [_BACKUP_LOCK_ID])
        if not self.env.cr.fetchone()[0]:
            raise UserError(_("已有备份任务正在执行，请稍后再试。"))

    @api.model
    def _archive_database(self, target_path):
        backup_root = os.path.dirname(target_path)
        os.makedirs(backup_root, mode=0o700, exist_ok=True)

        sql_fd, sql_path = tempfile.mkstemp(prefix="zfmd-backup-", suffix=".sql", dir=backup_root)
        os.close(sql_fd)
        partial_path = f"{target_path}.part"
        try:
            command = [
                find_pg_tool("pg_dump"),
                "--no-owner",
                f"--file={sql_path}",
                self.env.cr.dbname,
            ]
            result = subprocess.run(
                command,
                env=exec_pg_environ(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                check=False,
                text=True,
            )
            if result.returncode:
                error = (result.stderr or "").strip()
                raise UserError(_("PostgreSQL 数据库备份失败：%s") % (error[-1500:] or _("pg_dump 返回非零状态。")))
            self._remove_unsupported_dump_settings(sql_path)

            manifest = dump_db_manifest(self.env.cr)
            manifest.update(
                {
                    "backup_format": "zfmd_odoo_zip_v1",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "contents": ["dump.sql", "filestore/", "manifest.json"],
                }
            )
            filestore = config.filestore(self.env.cr.dbname)
            with zipfile.ZipFile(
                partial_path,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
                allowZip64=True,
            ) as archive:
                archive.write(sql_path, "dump.sql")
                archive.writestr(
                    "manifest.json",
                    json.dumps(manifest, ensure_ascii=False, indent=2),
                )
                if os.path.isdir(filestore):
                    for root, directories, filenames in os.walk(filestore, followlinks=False):
                        directories[:] = [item for item in directories if not os.path.islink(os.path.join(root, item))]
                        for filename in filenames:
                            source_path = os.path.join(root, filename)
                            if os.path.islink(source_path):
                                continue
                            relative_path = os.path.relpath(source_path, filestore)
                            archive.write(
                                source_path,
                                os.path.join("filestore", relative_path),
                            )
            os.chmod(partial_path, 0o600)
            os.replace(partial_path, target_path)
        finally:
            for temporary_path in (sql_path, partial_path):
                try:
                    if os.path.exists(temporary_path):
                        os.unlink(temporary_path)
                except OSError:
                    _logger.warning(
                        "Unable to remove temporary backup file %s",
                        temporary_path,
                        exc_info=True,
                    )

    @api.model
    def _remove_unsupported_dump_settings(self, sql_path):
        """Keep newer pg_dump output restorable on the PostgreSQL 16 server."""
        filtered_path = f"{sql_path}.filtered"
        try:
            with open(sql_path, "r", encoding="utf-8") as source, open(filtered_path, "w", encoding="utf-8") as target:
                for line in source:
                    if line.startswith("SET transaction_timeout = "):
                        continue
                    target.write(line)
            os.chmod(filtered_path, 0o600)
            os.replace(filtered_path, sql_path)
        finally:
            if os.path.exists(filtered_path):
                os.unlink(filtered_path)

    @api.model
    def _business_workbook_specs(self):
        return [
            ("zfmd.contract", "合同台账"),
            ("zfmd.project.start", "开工申请"),
            ("zfmd.service.record", "服务记录"),
            ("zfmd.invoice.record", "开票登记"),
            ("zfmd.payment.record", "回款登记"),
            ("zfmd.receivable.plan", "应收计划"),
            ("zfmd.project.management", "项目管理"),
            ("zfmd.after.sale.service", "售后服务"),
        ]

    @api.model
    def _excel_formats(self, workbook):
        return {
            "title": workbook.add_format(
                {
                    "bold": True,
                    "font_size": 18,
                    "font_color": "#2F1760",
                    "align": "left",
                    "valign": "vcenter",
                }
            ),
            "subtitle": workbook.add_format({"font_color": "#667085", "font_size": 10, "valign": "vcenter"}),
            "header": workbook.add_format(
                {
                    "bold": True,
                    "font_color": "#FFFFFF",
                    "bg_color": "#4B3575",
                    "border": 1,
                    "border_color": "#D0D5DD",
                    "align": "center",
                    "valign": "vcenter",
                    "text_wrap": True,
                }
            ),
            "section": workbook.add_format(
                {
                    "bold": True,
                    "font_color": "#2F1760",
                    "bg_color": "#F1ECFB",
                    "border": 1,
                    "border_color": "#D8D0E8",
                }
            ),
            "text": workbook.add_format(
                {
                    "border": 1,
                    "border_color": "#E4E7EC",
                    "valign": "top",
                    "text_wrap": True,
                }
            ),
            "center": workbook.add_format(
                {
                    "border": 1,
                    "border_color": "#E4E7EC",
                    "align": "center",
                    "valign": "vcenter",
                }
            ),
            "number": workbook.add_format(
                {
                    "border": 1,
                    "border_color": "#E4E7EC",
                    "align": "right",
                    "num_format": "#,##0.00",
                }
            ),
            "integer": workbook.add_format(
                {
                    "border": 1,
                    "border_color": "#E4E7EC",
                    "align": "right",
                    "num_format": "#,##0",
                }
            ),
            "count": workbook.add_format(
                {
                    "border": 1,
                    "border_color": "#E4E7EC",
                    "align": "center",
                    "num_format": "#,##0",
                }
            ),
            "date": workbook.add_format(
                {
                    "border": 1,
                    "border_color": "#E4E7EC",
                    "align": "center",
                    "num_format": "yyyy-mm-dd",
                }
            ),
            "datetime": workbook.add_format(
                {
                    "border": 1,
                    "border_color": "#E4E7EC",
                    "align": "center",
                    "num_format": "yyyy-mm-dd hh:mm:ss",
                }
            ),
        }

    @api.model
    def _write_business_cell(self, worksheet, row_index, col_index, record, field_name, formats):
        field = record._fields[field_name]
        raw_value = record[field_name]
        if field.type == "date":
            if raw_value:
                worksheet.write_datetime(row_index, col_index, raw_value, formats["date"])
            else:
                worksheet.write_blank(row_index, col_index, None, formats["date"])
            return
        if field.type == "datetime":
            if raw_value:
                worksheet.write_datetime(row_index, col_index, raw_value, formats["datetime"])
            else:
                worksheet.write_blank(row_index, col_index, None, formats["datetime"])
            return

        value = self.env["zfmd.export.mixin"]._format_export_value(record, field_name)
        if field.type in {"float", "monetary"}:
            worksheet.write_number(row_index, col_index, float(value or 0.0), formats["number"])
        elif field.type == "integer":
            worksheet.write_number(row_index, col_index, int(value or 0), formats["integer"])
        elif field.type in {"boolean", "selection"}:
            worksheet.write(row_index, col_index, value, formats["center"])
        else:
            worksheet.write(row_index, col_index, value, formats["text"])

    @api.model
    def _archive_business_excel(self, target_path):
        backup_root = os.path.dirname(target_path)
        os.makedirs(backup_root, mode=0o700, exist_ok=True)
        partial_path = f"{target_path}.part"
        total_count = 0
        sheet_results = []
        try:
            workbook = xlsxwriter.Workbook(
                partial_path,
                {
                    "constant_memory": True,
                    "strings_to_formulas": False,
                    "strings_to_urls": False,
                },
            )
            formats = self._excel_formats(workbook)
            summary = workbook.add_worksheet("备份说明")
            summary.set_tab_color("#4B3575")
            summary.set_column("A:A", 15)
            summary.set_column("B:B", 26)
            summary.set_column("C:C", 11)
            summary.set_column("D:D", 28)
            summary.merge_range("A1:D1", "ZFMD 业务数据 Excel 备份", formats["title"])
            summary.set_row(0, 30)
            summary.merge_range(
                "A2:D2",
                "用于日常核对、分析和补录；完整灾难恢复请使用系统恢复包。",
                formats["subtitle"],
            )
            summary.write("A4", "数据库", formats["section"])
            summary.write("B4", self.env.cr.dbname, formats["text"])
            summary.write("A5", "生成时间", formats["section"])
            summary.write_datetime("B5", datetime.utcnow(), formats["datetime"])
            summary.write("A6", "生成账号", formats["section"])
            summary.write("B6", self.env.user.display_name, formats["text"])
            summary.write_row(
                "A8",
                ["工作表", "数据模型", "记录数", "说明"],
                formats["header"],
            )

            for model_name, sheet_name in self._business_workbook_specs():
                model = self.env[model_name].sudo().with_context(include_deleted=True, active_test=False)
                order = getattr(model, "_order", "id asc")
                records = model.search([], order=order)
                columns = list(model._export_columns())
                if "is_deleted" in model._fields:
                    columns.extend(
                        [
                            ("is_deleted", "已删除", 10),
                            ("deleted_at", "删除时间", 20),
                            ("deleted_by", "删除人", 14),
                        ]
                    )

                worksheet = workbook.add_worksheet(sheet_name[:31])
                worksheet.set_tab_color("#8B6BB1")
                worksheet.set_row(0, 32)
                for col_index, (_field_name, label, width) in enumerate(columns):
                    worksheet.write(0, col_index, label, formats["header"])
                    worksheet.set_column(col_index, col_index, max(8, min(width, 36)))
                for row_index, record in enumerate(records, start=1):
                    for col_index, (field_name, _label, _width) in enumerate(columns):
                        self._write_business_cell(
                            worksheet,
                            row_index,
                            col_index,
                            record,
                            field_name,
                            formats,
                        )
                worksheet.freeze_panes(1, 0)
                worksheet.autofilter(0, 0, max(len(records), 1), max(len(columns) - 1, 0))
                total_count += len(records)
                sheet_results.append((sheet_name, model_name, len(records)))

            for row_index, (sheet_name, model_name, count) in enumerate(sheet_results, start=8):
                summary.write(row_index, 0, sheet_name, formats["text"])
                summary.write(row_index, 1, model_name, formats["text"])
                summary.write_number(row_index, 2, count, formats["count"])
                summary.write(
                    row_index,
                    3,
                    "含业务导出字段及回收站状态",
                    formats["text"],
                )
            summary.write(8 + len(sheet_results), 1, "总业务记录数", formats["section"])
            summary.write_number(
                8 + len(sheet_results),
                2,
                total_count,
                formats["count"],
            )
            summary.freeze_panes(7, 0)
            workbook.close()
            os.chmod(partial_path, 0o600)
            os.replace(partial_path, target_path)
            return total_count
        finally:
            try:
                if os.path.exists(partial_path):
                    os.unlink(partial_path)
            except OSError:
                _logger.warning(
                    "Unable to remove temporary Excel backup %s",
                    partial_path,
                    exc_info=True,
                )

    @api.model
    def create_backup(self, backup_type="manual"):
        self._check_backup_manager()
        if backup_type not in ("manual", "scheduled"):
            raise UserError(_("不支持的备份方式。"))
        self._acquire_backup_lock()

        started_at = fields.Datetime.now()
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
        safe_db_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", self.env.cr.dbname)
        file_name = f"{safe_db_name}-{timestamp}.zip"
        file_path = os.path.join(self._backup_root(), file_name)
        record = self.create(
            {
                "name": file_name,
                "backup_type": backup_type,
                "backup_format": "system_zip",
                "state": "running",
                "database_name": self.env.cr.dbname,
                "started_at": started_at,
                "file_name": file_name,
                "file_path": file_path,
            }
        )
        try:
            self._archive_database(file_path)
            record.write(
                {
                    "state": "done",
                    "completed_at": fields.Datetime.now(),
                    "file_size": os.path.getsize(file_path),
                    "error_message": False,
                }
            )
            self._cleanup_old_backups()
            _logger.info("ZFMD backup completed: %s", file_path)
        except Exception as error:
            _logger.exception("ZFMD backup failed")
            try:
                if os.path.exists(file_path):
                    os.unlink(file_path)
            except OSError:
                _logger.warning("Unable to remove failed backup %s", file_path)
            record.write(
                {
                    "state": "failed",
                    "completed_at": fields.Datetime.now(),
                    "error_message": str(error)[:4000],
                }
            )
        return record

    @api.model
    def create_excel_backup(self, backup_type="manual"):
        self._check_backup_manager()
        if backup_type not in ("manual", "scheduled"):
            raise UserError(_("不支持的备份方式。"))
        self._acquire_backup_lock()

        started_at = fields.Datetime.now()
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
        safe_db_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", self.env.cr.dbname)
        file_name = f"{safe_db_name}-business-{timestamp}.xlsx"
        file_path = os.path.join(self._backup_root(), file_name)
        record = self.create(
            {
                "name": file_name,
                "backup_type": backup_type,
                "backup_format": "business_xlsx",
                "state": "running",
                "database_name": self.env.cr.dbname,
                "started_at": started_at,
                "file_name": file_name,
                "file_path": file_path,
            }
        )
        try:
            record_count = self._archive_business_excel(file_path)
            record.write(
                {
                    "state": "done",
                    "completed_at": fields.Datetime.now(),
                    "file_size": os.path.getsize(file_path),
                    "record_count": record_count,
                    "error_message": False,
                }
            )
            self._cleanup_old_backups()
            _logger.info("ZFMD Excel backup completed: %s", file_path)
        except Exception as error:
            _logger.exception("ZFMD Excel backup failed")
            try:
                if os.path.exists(file_path):
                    os.unlink(file_path)
            except OSError:
                _logger.warning("Unable to remove failed Excel backup %s", file_path)
            record.write(
                {
                    "state": "failed",
                    "completed_at": fields.Datetime.now(),
                    "error_message": str(error)[:4000],
                }
            )
        return record

    @api.model
    def _cleanup_old_backups(self):
        for backup_format in ("system_zip", "business_xlsx"):
            completed = self.search(
                [
                    ("state", "=", "done"),
                    ("backup_format", "=", backup_format),
                ],
                order="completed_at desc, id desc",
                offset=self._retention_count(),
            )
            if completed:
                completed.unlink()

    @api.model
    def _cron_create_backup(self):
        mode = self._scheduled_mode()
        records = self.browse()
        if mode in ("system_zip", "both"):
            records |= self.create_backup(backup_type="scheduled")
        if mode in ("business_xlsx", "both"):
            records |= self.create_excel_backup(backup_type="scheduled")
        for record in records.filtered(lambda item: item.state == "failed"):
            _logger.error(
                "Scheduled ZFMD backup failed: %s",
                record.error_message or "unknown",
            )
        return True

    def action_download(self):
        self._check_backup_manager()
        self.ensure_one()
        backup = self.sudo()
        if backup.state != "done" or not backup.file_path or not os.path.isfile(backup.file_path):
            raise UserError(_("备份文件不存在或尚未生成完成。"))
        return {
            "type": "ir.actions.act_url",
            "url": f"/zfmd_pm/backup/{backup.id}/download",
            "target": "self",
        }

    def unlink(self):
        self._check_backup_manager()
        backup_root = os.path.realpath(self._backup_root())
        protected_records = self.sudo()
        paths = [record.file_path for record in protected_records if record.file_path]
        result = super().unlink()
        for path in paths:
            real_path = os.path.realpath(path)
            if os.path.commonpath([backup_root, real_path]) == backup_root and os.path.isfile(real_path):
                try:
                    os.unlink(real_path)
                except OSError:
                    _logger.warning("Unable to remove backup file %s", real_path, exc_info=True)
        return result

from odoo import fields, models


class ZfmdBackupCenterWizard(models.TransientModel):
    _name = "zfmd.backup.center.wizard"
    _description = "ZFMD 备份中心"

    backup_scope = fields.Html(readonly=True, sanitize=False, string="备份范围")
    execution_steps = fields.Html(readonly=True, sanitize=False, string="执行步骤")
    recovery_notes = fields.Html(readonly=True, sanitize=False, string="恢复说明")
    script_command = fields.Text(readonly=True, string="本地一键备份脚本")
    daily_checklist = fields.Html(readonly=True, sanitize=False, string="固定操作清单")

    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        res.update(
            {
                "backup_scope": "\n".join(
                    [
                        "<div>",
                        "<p><strong>本次完整备份包含两层内容：</strong></p>",
                        "<ol>",
                        "<li>业务导出：合同台账、开工申请、服务记录、开票登记、回款登记、应收计划。</li>",
                        "<li>系统冷备份：PostgreSQL 数据库、Odoo filestore、当前模块源码与文档。</li>",
                        "</ol>",
                        "<p>业务导出用于日常核对，系统冷备份用于完整恢复。</p>",
                        "</div>",
                    ]
                ),
                "execution_steps": "\n".join(
                    [
                        "<div>",
                        "<ol>",
                        "<li>先导出 6 个业务台账，确认表头完整、金额单位统一为元。</li>",
                        "<li>在项目根目录执行本地一键备份脚本。</li>",
                        "<li>确认备份目录里存在 <code>postgres_data</code>、<code>odoo_data</code>、<code>addons</code>、<code>docs</code>。</li>",
                        "<li>抽查 1 份业务 Excel 和 1 份备份说明文件是否可打开。</li>",
                        "</ol>",
                        "</div>",
                    ]
                ),
                "recovery_notes": "\n".join(
                    [
                        "<div>",
                        "<ol>",
                        "<li>业务导出不能替代数据库备份，只能用于核对和补录。</li>",
                        "<li>恢复时先恢复数据库，再恢复 filestore，最后恢复模块代码。</li>",
                        "<li>每次升级模块前，必须先完成数据库和文件备份。</li>",
                        "</ol>",
                        "</div>",
                    ]
                ),
                "script_command": "\n".join(
                    [
                        "脚本位置：scripts\\backup_local.ps1",
                        "推荐执行：powershell -ExecutionPolicy Bypass -File .\\scripts\\backup_local.ps1",
                        "默认输出目录：项目根目录下 backups\\时间戳",
                    ]
                ),
                "daily_checklist": "\n".join(
                    [
                        "<div>",
                        "<ul>",
                        "<li>每次结构调整、批量导入前先做一次完整备份。</li>",
                        "<li>每次客户演示前先导出 6 张业务台账并做一次冷备份。</li>",
                        "<li>备份完成后抽查导出文件和备份目录，不要只看脚本执行成功提示。</li>",
                        "<li>升级模块前，必须先完成数据库和文件目录备份。</li>",
                        "</ul>",
                        "</div>",
                    ]
                ),
            }
        )
        return res

    def _open_action(self, xmlid):
        action = self.env.ref(xmlid).sudo().read()[0]
        return action

    def action_open_contracts(self):
        return self._open_action("zfmd_pm.action_zfmd_contract")

    def action_open_project_starts(self):
        return self._open_action("zfmd_pm.action_zfmd_project_start")

    def action_open_service_records(self):
        return self._open_action("zfmd_pm.action_zfmd_service_record")

    def action_open_invoices(self):
        return self._open_action("zfmd_pm.action_zfmd_invoice_record")

    def action_open_payments(self):
        return self._open_action("zfmd_pm.action_zfmd_payment_record")

    def action_open_receivables(self):
        return self._open_action("zfmd_pm.action_zfmd_receivable_plan")

import json

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    services = env["zfmd.service.record"].with_context(include_deleted=True).search([])
    parser = env["zfmd.service.record.import.wizard"].new({})

    for service in services:
        imported_end_date = service.service_end_date
        if service.raw_import_data:
            try:
                raw = json.loads(service.raw_import_data)
                imported_end_date = parser._parse_date(raw.get("服务合同到期时间")) or imported_end_date
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
        if imported_end_date:
            service.with_context(
                skip_service_end_date_recompute=True,
                skip_entry_confirmation_stage=True,
                skip_zfmd_sync=True,
            ).write({"imported_service_end_date": imported_end_date})

    services.filtered(lambda record: not record.is_deleted)._refresh_service_end_date_from_contracts()

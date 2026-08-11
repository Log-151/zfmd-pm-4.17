from odoo import SUPERUSER_ID, api, fields


def _repair_split_taian_contracts(env):
    contract_model = env["zfmd.contract"].sudo().with_context(include_deleted=True)
    original = contract_model.search([("name", "=", "ZFMD/SD-23121-21140-3-SH")], limit=1)
    if not original:
        return contract_model.browse()

    shared_fields = [
        "contract_name",
        "customer_level_1",
        "customer_level_2",
        "customer_level_3",
        "partner_id",
        "customer_code",
        "site_id",
        "site_other_name",
        "site_category",
        "capacity_text",
        "province_name",
        "group_name",
        "project_content",
        "sale_manager",
        "sale_contact",
        "contract_sign_date",
        "contract_sign_date_text",
        "archive_date",
        "archive_date_text",
        "archive_document_type",
        "archive_copy_count",
        "service_start_date",
        "service_start_date_text",
        "service_end_date",
        "service_end_date_text",
        "exclude_sales_revenue",
        "exclude_sales_performance",
        "bond_status",
        "delivery_department",
        "project_manager",
        "handover_meeting_date",
        "handover_meeting_date_text",
        "third_party_interface_fee",
        "state",
        "entry_state",
    ]
    shared_vals = {}
    for field_name in shared_fields:
        value = original[field_name]
        shared_vals[field_name] = value.id if original._fields[field_name].type == "many2one" else value

    specifications = [
        ("ZFMD/SD-23121-21140-1-SH", "23121-21140-1", "风电AGC/AVC", 11000.0, 1),
        ("ZFMD/SD-23121-21140-2-SH", "23121-21140-2", "风电功率预测", 181000.0, 2),
        ("ZFMD/SD-23121-21140-3-SH", "23121-21140-3", "电力通讯", 7000.0, 3),
    ]
    repaired = contract_model.browse()
    contracts_by_product = {}
    for name, contract_key, product_line, amount, display_order in specifications:
        contract = contract_model.search([("name", "=", name)], limit=1)
        vals = {
            **shared_vals,
            "name": name,
            "contract_key": contract_key,
            "product_line": product_line,
            "initial_fee": amount,
            "service_fee": 0.0,
            "amount_total": amount,
            "amount_untaxed": 0.0,
            "display_order": display_order,
            "confirmed_at": original.confirmed_at or fields.Datetime.now(),
            "confirmed_by": original.confirmed_by.id or env.user.id,
            "is_deleted": False,
        }
        if contract:
            contract.with_context(skip_zfmd_sync=True, skip_entry_confirmation_stage=True).write(vals)
        else:
            contract = contract_model.with_context(skip_zfmd_sync=True).create(vals)
        repaired |= contract
        contracts_by_product[product_line] = contract

    affected_models = [
        "zfmd.invoice.record",
        "zfmd.payment.record",
        "zfmd.receivable.plan",
    ]
    for model_name in affected_models:
        model = env[model_name].sudo().with_context(include_deleted=True)
        for product_line, contract in contracts_by_product.items():
            records = model.search(
                [
                    ("contract_id", "=", original.id),
                    ("site_name", "=", "台安桑林"),
                    ("product_line", "=", product_line),
                ]
            )
            vals = {
                "contract_id": contract.id,
                "source_contract_no": contract.name,
                "contract_amount": contract.amount_total,
            }
            if model_name == "zfmd.invoice.record":
                vals.update(
                    {
                        "actual_payment_manual": False,
                        "actual_payment_date": False,
                        "actual_payment_amount": 0.0,
                        "actual_payment_date_note": False,
                        "actual_payment_amount_note": False,
                    }
                )
            records.with_context(
                skip_zfmd_sync=True,
                skip_entry_confirmation_stage=True,
                auto_link_sync=True,
            ).write(vals)
    return repaired


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env.cr.execute(
        """
        UPDATE zfmd_project_management
           SET bad_debt_manual = TRUE
         WHERE COALESCE(bad_debt_amount, 0) <> 0
        """
    )
    env.invalidate_all()
    contract_model = env["zfmd.contract"].sudo().with_context(include_deleted=True)
    for contract in contract_model.search([]):
        contract_key = contract_model._extract_contract_key(contract.name)
        if contract_key and contract.contract_key != contract_key:
            contract.with_context(skip_zfmd_sync=True, skip_entry_confirmation_stage=True).write(
                {"contract_key": contract_key}
            )

    repaired_contracts = _repair_split_taian_contracts(env)

    imported_draft_invoices = (
        env["zfmd.invoice.record"]
        .sudo()
        .search(
            [
                ("entry_state", "=", "draft"),
                ("import_source_row", ">", 0),
            ]
        )
    )
    if imported_draft_invoices:
        imported_draft_invoices.with_context(
            skip_zfmd_sync=True,
            skip_entry_confirmation_stage=True,
        ).write(
            {
                "entry_state": "confirmed",
                "confirmed_at": fields.Datetime.now(),
                "confirmed_by": env.user.id,
            }
        )

    engine = env["zfmd.sync.engine"]
    if repaired_contracts:
        engine.sync_contracts(repaired_contracts)
        repaired_numbers = set(repaired_contracts.mapped("name"))
        engine.refresh_from_payments(repaired_numbers)
        engine.refresh_from_invoices(repaired_numbers)
    if imported_draft_invoices:
        engine.refresh_from_invoices(engine._contract_numbers(imported_draft_invoices))
    engine.rebuild_projects_from_ledgers()

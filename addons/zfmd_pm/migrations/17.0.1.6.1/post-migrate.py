from odoo import SUPERUSER_ID, api

SOFT_DELETE_TABLES = (
    "zfmd_contract",
    "zfmd_project_start",
    "zfmd_service_record",
    "zfmd_invoice_record",
    "zfmd_payment_record",
    "zfmd_receivable_plan",
    "zfmd_project_management",
    "zfmd_after_sale_service",
    "zfmd_site",
)


def migrate(cr, version):
    for table_name in SOFT_DELETE_TABLES:
        cr.execute(f"UPDATE {table_name} SET is_deleted = FALSE WHERE is_deleted IS NULL")

    cr.execute(
        """
        WITH unique_codes AS (
            SELECT customer_name, MIN(customer_code) AS customer_code
              FROM zfmd_project_management
             WHERE COALESCE(customer_name, '') != ''
               AND COALESCE(customer_code, '') != ''
             GROUP BY customer_name
            HAVING COUNT(DISTINCT customer_code) = 1
        )
        UPDATE res_partner partner
           SET customer_code = codes.customer_code
          FROM unique_codes codes
         WHERE partner.name = codes.customer_name
           AND COALESCE(partner.customer_code, '') = ''
        """
    )
    cr.execute(
        """
        UPDATE zfmd_contract contract
           SET customer_code = partner.customer_code
          FROM res_partner partner
         WHERE contract.partner_id = partner.id
           AND COALESCE(contract.customer_code, '') = ''
           AND COALESCE(partner.customer_code, '') != ''
        """
    )
    cr.execute(
        """
        UPDATE zfmd_receivable_plan receivable
           SET customer_name = partner.name
          FROM zfmd_contract contract
          JOIN res_partner partner ON partner.id = contract.partner_id
         WHERE receivable.contract_id = contract.id
           AND COALESCE(receivable.customer_name, '') = ''
        """
    )
    cr.execute(
        """
        WITH unique_projects AS (
            SELECT name, MIN(customer_name) AS customer_name
              FROM zfmd_project_management
             WHERE COALESCE(name, '') != ''
               AND COALESCE(customer_name, '') != ''
             GROUP BY name
            HAVING COUNT(DISTINCT customer_name) = 1
        )
        UPDATE zfmd_receivable_plan receivable
           SET customer_name = project.customer_name
          FROM unique_projects project
         WHERE receivable.contract_id IS NULL
           AND receivable.source_contract_no = project.name
           AND COALESCE(receivable.customer_name, '') = ''
        """
    )

    env = api.Environment(cr, SUPERUSER_ID, {})
    contracts = env["zfmd.contract"].search([])
    env["zfmd.sync.engine"].sync_contracts(contracts)
    env["zfmd.project.management"].action_refresh_all_projects()

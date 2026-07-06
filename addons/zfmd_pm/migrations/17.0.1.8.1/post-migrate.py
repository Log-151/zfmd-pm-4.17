from odoo import SUPERUSER_ID, api, fields


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    site = env["zfmd.site"].search([("name", "=", "待补充场站")], limit=1)
    if not site:
        site = env["zfmd.site"].create({"name": "待补充场站"})

    today = fields.Date.today()
    cr.execute(
        """
        UPDATE zfmd_contract
           SET site_id = COALESCE(site_id, %s),
               contract_name = COALESCE(NULLIF(contract_name, ''), COALESCE(name, '待补充合同名称')),
               province_name = COALESCE(NULLIF(province_name, ''), '待补充'),
               group_name = COALESCE(NULLIF(group_name, ''), '待补充'),
               product_line = COALESCE(NULLIF(product_line, ''), '待补充'),
               sale_manager = COALESCE(NULLIF(sale_manager, ''), '待补充'),
               sale_contact = COALESCE(NULLIF(sale_contact, ''), '待补充'),
               delivery_department = COALESCE(NULLIF(delivery_department, ''), '待补充'),
               project_content = COALESCE(NULLIF(project_content, ''), '待补充'),
               archive_date = COALESCE(archive_date, %s),
               initial_fee = COALESCE(initial_fee, 0),
               service_fee = COALESCE(service_fee, 0),
               amount_total = COALESCE(amount_total, 0),
               amount_untaxed = COALESCE(amount_untaxed, 0)
         WHERE site_id IS NULL
            OR COALESCE(contract_name, '') = ''
            OR COALESCE(province_name, '') = ''
            OR COALESCE(group_name, '') = ''
            OR COALESCE(product_line, '') = ''
            OR COALESCE(sale_manager, '') = ''
            OR COALESCE(sale_contact, '') = ''
            OR COALESCE(delivery_department, '') = ''
            OR COALESCE(project_content, '') = ''
            OR archive_date IS NULL
            OR initial_fee IS NULL
            OR service_fee IS NULL
            OR amount_total IS NULL
            OR amount_untaxed IS NULL
        """,
        (site.id, today),
    )

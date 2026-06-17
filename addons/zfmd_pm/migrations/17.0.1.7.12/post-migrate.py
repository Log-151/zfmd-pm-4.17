def migrate(cr, version):
    cr.execute(
        """
        ALTER TABLE zfmd_receivable_plan
        ADD COLUMN IF NOT EXISTS bad_debt_info text
        """
    )
    cr.execute(
        """
        ALTER TABLE zfmd_receivable_plan
        ADD COLUMN IF NOT EXISTS bad_debt_amount double precision
        """
    )
    cr.execute(
        """
        ALTER TABLE zfmd_project_start
        ADD COLUMN IF NOT EXISTS estimated_receivable double precision
        """
    )
    cr.execute(
        """
        UPDATE zfmd_project_start
        SET estimated_receivable = COALESCE(estimated_contract_amount, 0) * 0.3
        WHERE estimated_receivable IS NULL
        """
    )
    cr.execute(
        """
        UPDATE zfmd_contract
        SET archive_document_type = CASE
            WHEN archive_document_type = 'original' THEN 'original'
            WHEN archive_document_type = 'copy' THEN 'copy'
            WHEN archive_document_type LIKE '%%原件%%' THEN 'original'
            WHEN archive_document_type LIKE '%%复印%%' THEN 'copy'
            ELSE NULL
        END
        WHERE archive_document_type IS NOT NULL
        """
    )
    cr.execute(
        """
        UPDATE zfmd_project_management pm
        SET customer_code = COALESCE(c.customer_code, rp.customer_code)
        FROM zfmd_contract c
        LEFT JOIN res_partner rp ON c.partner_id = rp.id
        WHERE pm.contract_id = c.id
          AND COALESCE(pm.customer_code, '') = ''
          AND COALESCE(c.customer_code, rp.customer_code, '') <> ''
        """
    )

def table_exists(cr, table_name):
    cr.execute("SELECT to_regclass(%s)", (table_name,))
    return bool(cr.fetchone()[0])


def column_exists(cr, table_name, column_name):
    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = %s
           AND column_name = %s
         LIMIT 1
        """,
        (table_name, column_name),
    )
    return bool(cr.fetchone())


def run_batched_update(cr, sql, batch_size=5000):
    while True:
        cr.execute(sql, {"batch_size": batch_size})
        updated = cr.rowcount
        if not updated:
            break


def migrate(cr, version):
    if table_exists(cr, "zfmd_project_management"):
        run_batched_update(
            cr,
            """
            UPDATE zfmd_project_management
               SET contract_key = COALESCE(
                    substring(name from '([0-9]{5}(-[0-9]+)?)'),
                    NULLIF(name, '')
               )
             WHERE id IN (
                   SELECT id
                     FROM zfmd_project_management
                    WHERE name IS NOT NULL
                      AND (
                           contract_key IS NULL
                           OR contract_key IS DISTINCT FROM COALESCE(
                               substring(name from '([0-9]{5}(-[0-9]+)?)'),
                               NULLIF(name, '')
                           )
                      )
                    LIMIT %(batch_size)s
             )
            """,
        )
        run_batched_update(
            cr,
            """
            UPDATE zfmd_project_management pm
               SET contract_id = c.id
              FROM zfmd_contract c
             WHERE pm.id IN (
                   SELECT pm_inner.id
                     FROM zfmd_project_management pm_inner
                     JOIN zfmd_contract c_inner
                       ON c_inner.contract_key = pm_inner.contract_key
                    WHERE pm_inner.contract_key IS NOT NULL
                      AND pm_inner.contract_id IS DISTINCT FROM c_inner.id
                    LIMIT %(batch_size)s
             )
               AND c.contract_key = pm.contract_key
            """,
        )
        run_batched_update(
            cr,
            """
            UPDATE zfmd_project_management
               SET contract_match_state = CASE
                    WHEN contract_id IS NOT NULL THEN 'matched'
                    WHEN COALESCE(name, '') != '' THEN 'unmatched'
                    ELSE 'empty'
               END
             WHERE id IN (
                   SELECT id
                     FROM zfmd_project_management
                    WHERE contract_match_state IS NULL
                       OR contract_match_state IS DISTINCT FROM CASE
                           WHEN contract_id IS NOT NULL THEN 'matched'
                           WHEN COALESCE(name, '') != '' THEN 'unmatched'
                           ELSE 'empty'
                      END
                    LIMIT %(batch_size)s
             )
            """,
        )

    if table_exists(cr, "res_partner") and column_exists(cr, "res_partner", "zfmd_customer_manual"):
        run_batched_update(
            cr,
            """
            UPDATE res_partner
               SET zfmd_customer_manual = TRUE
             WHERE id IN (
                   SELECT id
                     FROM res_partner
                    WHERE is_zfmd_customer = TRUE
                      AND COALESCE(zfmd_customer_manual, FALSE) = FALSE
                    LIMIT %(batch_size)s
             )
            """,
        )

    if table_exists(cr, "zfmd_receivable_plan") and column_exists(cr, "zfmd_receivable_plan", "exception_type"):
        run_batched_update(
            cr,
            """
            UPDATE zfmd_receivable_plan
               SET exception_type = CASE
                    WHEN COALESCE(note, '') LIKE '%%坏账%%' THEN 'bad_debt'
                    WHEN COALESCE(note, '') LIKE '%%扣款%%' THEN 'deduction'
                    WHEN COALESCE(note, '') LIKE '%%作废%%' THEN 'cancel'
                    ELSE exception_type
               END
             WHERE id IN (
                   SELECT id
                     FROM zfmd_receivable_plan
                    WHERE COALESCE(exception_type, 'none') = 'none'
                      AND (
                           COALESCE(note, '') LIKE '%%坏账%%'
                           OR COALESCE(note, '') LIKE '%%扣款%%'
                           OR COALESCE(note, '') LIKE '%%作废%%'
                      )
                    LIMIT %(batch_size)s
             )
            """,
        )

    if table_exists(cr, "zfmd_contract") and column_exists(cr, "zfmd_contract", "contract_name"):
        run_batched_update(
            cr,
            """
            UPDATE zfmd_contract
               SET contract_name = '自动创建合同主档：' || name
             WHERE id IN (
                   SELECT id
                     FROM zfmd_contract
                    WHERE contract_name = '导入自动创建合同主档'
                      AND COALESCE(name, '') != ''
                    LIMIT %(batch_size)s
             )
            """,
        )

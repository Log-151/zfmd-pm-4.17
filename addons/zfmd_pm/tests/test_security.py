import os
import tempfile

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestZfmdSecurity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        cls.manager_user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "安全测试管理员",
                    "login": "zfmd-security-manager",
                    "groups_id": [(6, 0, [cls.env.ref("zfmd_pm.group_zfmd_manager").id])],
                    "company_id": company.id,
                    "company_ids": [(6, 0, [company.id])],
                }
            )
        )
        cls.viewer_user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "安全测试访客",
                    "login": "zfmd-security-viewer",
                    "groups_id": [(6, 0, [cls.env.ref("zfmd_pm.group_zfmd_viewer").id])],
                    "company_id": company.id,
                    "company_ids": [(6, 0, [company.id])],
                }
            )
        )

    def test_module_install_does_not_create_fixed_password_user(self):
        self.assertFalse(self.env.ref("zfmd_pm.user_zfmd", raise_if_not_found=False))

    def test_import_mapping_is_restricted_to_manager(self):
        manager_model = self.env["zfmd.import.mapping.line"].with_user(self.manager_user)
        viewer_model = self.env["zfmd.import.mapping.line"].with_user(self.viewer_user)
        self.assertTrue(manager_model.check_access_rights("create"))
        with self.assertRaises(AccessError):
            viewer_model.check_access_rights("create")

    def test_viewer_cannot_call_privileged_backup_or_sync_methods(self):
        backup_model = self.env["zfmd.backup.record"].with_user(self.viewer_user)
        sync_engine = self.env["zfmd.sync.engine"].with_user(self.viewer_user)
        warning_model = self.env["zfmd.warning.event"].with_user(self.viewer_user)
        import_wizard = self.env["zfmd.contract.import.wizard"].with_user(self.viewer_user)

        with self.assertRaisesRegex(AccessError, "请联系管理员开通备份管理权限"):
            backup_model._check_backup_manager()
        with self.assertRaises(AccessError):
            sync_engine._check_sync_manager()
        with self.assertRaises(AccessError):
            warning_model.recompute_warning_events()
        with self.assertRaises(AccessError):
            import_wizard._check_import_manager()

    def test_manager_can_access_backup_and_sync_guards(self):
        self.env["zfmd.backup.record"].with_user(self.manager_user)._check_backup_manager()
        self.env["zfmd.sync.engine"].with_user(self.manager_user)._check_sync_manager()

    def test_backup_dump_removes_postgresql_18_only_setting(self):
        descriptor, path = tempfile.mkstemp(prefix="zfmd-backup-test-", suffix=".sql")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as dump_file:
                dump_file.write(
                    "SET statement_timeout = 0;\n" "SET transaction_timeout = 0;\n" "SET client_encoding = 'UTF8';\n"
                )
            self.env["zfmd.backup.record"]._remove_unsupported_dump_settings(path)
            with open(path, encoding="utf-8") as dump_file:
                contents = dump_file.read()
            self.assertNotIn("transaction_timeout", contents)
            self.assertIn("statement_timeout", contents)
            self.assertIn("client_encoding", contents)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_backup_manifest_does_not_depend_on_database_management(self):
        manifest = self.env["zfmd.backup.record"]._build_db_manifest()

        self.assertEqual(manifest["odoo_dump"], "1")
        self.assertEqual(manifest["db_name"], self.env.cr.dbname)
        self.assertIn("base", manifest["modules"])
        self.assertTrue(manifest["version"])
        self.assertTrue(manifest["pg_version"])

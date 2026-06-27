from __future__ import annotations

import os
from pathlib import Path
import unittest

os.environ.setdefault("ULTRAVOX_API_KEY", "test_ultravox_key")
os.environ.setdefault("AUTH0_DOMAIN", "example.auth0.com")
os.environ.setdefault("AUTH0_AUDIENCE", "https://api.example.test")
os.environ["SERVIAI_TEST_SECRET_FALLBACK"] = "1"
TEST_DB_PATH = Path("serviai_integrations_base_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"

from app.db.base import Base
from app.db.session import engine
from app.services.secret_manager_service import SecretManager


class IntegrationsBaseTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        engine.dispose()
        TEST_DB_PATH.unlink(missing_ok=True)

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

    def tearDown(self):
        Base.metadata.drop_all(bind=engine)

    def test_secret_manager_encrypts_and_decrypts(self):
        manager = SecretManager("test-key")
        encrypted = manager.encrypt_secret("re_secret_test")

        self.assertNotEqual(encrypted, "re_secret_test")
        self.assertEqual(manager.decrypt_secret(encrypted), "re_secret_test")

    def test_secret_manager_does_not_return_plain_secret(self):
        manager = SecretManager("test-key")
        encrypted = manager.encrypt_secret("re_secret_test")

        self.assertNotIn("re_secret_test", encrypted)
        self.assertEqual(manager.mask_secret("re_secret_test"), "re_s...test")


if __name__ == "__main__":
    unittest.main()

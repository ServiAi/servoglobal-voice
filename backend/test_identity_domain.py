import unittest
from dataclasses import FrozenInstanceError

from app.modules.identity.domain.contracts import ExternalIdentity
from app.modules.identity.domain.roles import ADMIN_ROLES


class IdentityDomainTests(unittest.TestCase):
    def test_external_identity_is_immutable_and_provider_neutral(self):
        identity = ExternalIdentity(external_auth_id="subject-1", email="user@example.test")
        with self.assertRaises(FrozenInstanceError):
            identity.email = "other@example.test"
        self.assertEqual(identity.external_auth_id, "subject-1")

    def test_admin_roles_are_explicit(self):
        self.assertEqual(ADMIN_ROLES, frozenset({"tenant_admin", "admin", "owner"}))


if __name__ == "__main__":
    unittest.main()

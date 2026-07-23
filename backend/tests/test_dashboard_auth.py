from __future__ import annotations

import unittest

from src.api.auth import DashboardAuth


class DashboardAuthTests(unittest.TestCase):
    def test_password_comparison_requires_an_exact_non_empty_value(self) -> None:
        self.assertTrue(DashboardAuth.password_matches("correct horse", "correct horse"))
        self.assertFalse(DashboardAuth.password_matches("incorrect", "correct horse"))
        self.assertFalse(DashboardAuth.password_matches("", "correct horse"))
        self.assertFalse(DashboardAuth.password_matches("correct horse", None))

    def test_session_can_be_revoked(self) -> None:
        auth = DashboardAuth()
        token = auth.create_session(ttl_minutes=5)

        self.assertTrue(auth.is_valid_session(token))
        auth.revoke_session(token)
        self.assertFalse(auth.is_valid_session(token))


if __name__ == "__main__":
    unittest.main()

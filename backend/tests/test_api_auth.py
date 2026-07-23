from __future__ import annotations

import os
import unittest

from fastapi.testclient import TestClient

os.environ["DASHBOARD_PASSWORD"] = "test-dashboard-password"

from src.api.app import app  # noqa: E402


class DashboardAuthApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_protected_endpoints_require_a_valid_login_session(self) -> None:
        self.assertEqual(self.client.get("/api/v1/not-a-real-route").status_code, 401)

        invalid = self.client.post("/api/v1/auth/login", json={"password": "wrong"})
        self.assertEqual(invalid.status_code, 401)

        login = self.client.post("/api/v1/auth/login", json={"password": "test-dashboard-password"})
        self.assertEqual(login.status_code, 200)
        self.assertTrue(login.json()["authenticated"])

        self.assertEqual(self.client.get("/api/v1/not-a-real-route").status_code, 404)

        logout = self.client.post("/api/v1/auth/logout")
        self.assertEqual(logout.status_code, 200)
        self.assertEqual(self.client.get("/api/v1/not-a-real-route").status_code, 401)


if __name__ == "__main__":
    unittest.main()

# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
#  type: ignore
"""Unit tests for Superset"""

from unittest.mock import patch

from superset import security_manager
from superset.utils import json, slack  # noqa: F401
from tests.conftest import with_config
from tests.integration_tests.base_tests import SupersetTestCase
from tests.integration_tests.conftest import with_feature_flags
from tests.integration_tests.constants import ADMIN_USERNAME

meUri = "/api/v1/me/"  # noqa: N816
AVATAR_URL = "/internal/avatar.png"


class TestCurrentUserApi(SupersetTestCase):
    def test_get_me_logged_in(self):
        self.login(ADMIN_USERNAME)

        rv = self.client.get(meUri)

        assert 200 == rv.status_code
        response = json.loads(rv.data.decode("utf-8"))
        assert "admin" == response["result"]["username"]
        assert True is response["result"]["is_active"]
        assert False is response["result"]["is_anonymous"]

    def test_get_me_with_roles(self):
        self.login(ADMIN_USERNAME)

        rv = self.client.get(meUri + "roles/")
        assert 200 == rv.status_code
        response = json.loads(rv.data.decode("utf-8"))
        roles = list(response["result"]["roles"].keys())
        assert "Admin" == roles.pop()

    @patch("superset.security.manager.g")
    def test_get_my_roles_anonymous(self, mock_g):
        mock_g.user = security_manager.get_anonymous_user
        rv = self.client.get(meUri + "roles/")
        assert 401 == rv.status_code

    def test_get_me_unauthorized(self):
        rv = self.client.get(meUri)
        assert 401 == rv.status_code

    @patch("superset.security.manager.g")
    def test_get_me_anonymous(self, mock_g):
        mock_g.user = security_manager.get_anonymous_user
        rv = self.client.get(meUri)
        assert 401 == rv.status_code

    def test_update_me_success(self):
        self.login(ADMIN_USERNAME)

        payload = {
            "first_name": "UpdatedFirst",
            "last_name": "UpdatedLast",
        }

        rv = self.client.put("/api/v1/me/", json=payload)
        assert rv.status_code == 200

        data = json.loads(rv.data.decode("utf-8"))
        assert data["result"]["first_name"] == "UpdatedFirst"
        assert data["result"]["last_name"] == "UpdatedLast"

    def test_update_me_unauthenticated(self):
        rv = self.client.put("/api/v1/me/", json={"first_name": "Hacker"})
        assert rv.status_code == 401

    def test_update_me_invalid_payload(self):
        self.login(ADMIN_USERNAME)
        rv = self.client.put("/api/v1/me/", json={"first_name": 123})
        assert rv.status_code == 400
        data = json.loads(rv.data.decode("utf-8"))
        assert "first_name" in data["message"]

    def test_update_me_empty_payload(self):
        self.login(ADMIN_USERNAME)
        rv = self.client.put("/api/v1/me/", json={})
        assert rv.status_code == 400

    def test_update_me_password_requires_current_password(self):
        """PUT /api/v1/me/ with a new password but no current_password is rejected.

        Regression test for the missing-old-password check that previously
        allowed account takeover from a compromised session.
        """
        self.login(ADMIN_USERNAME)

        rv = self.client.put(
            "/api/v1/me/",
            json={"password": "NewAttackerP@ss1!"},
        )
        assert rv.status_code == 400
        data = json.loads(rv.data.decode("utf-8"))
        assert "current_password" in data["message"]

        # The admin password must still be the original so subsequent tests pass.
        rv = self.client.post(
            "/api/v1/security/login",
            json={
                "username": ADMIN_USERNAME,
                "password": "general",
                "provider": "db",
            },
        )
        assert rv.status_code == 200

    def test_update_me_password_wrong_current_password(self):
        """PUT /api/v1/me/ with a wrong current_password is rejected."""
        self.login(ADMIN_USERNAME)

        rv = self.client.put(
            "/api/v1/me/",
            json={
                "password": "NewAttackerP@ss1!",
                "current_password": "definitely-not-the-password",
            },
        )
        assert rv.status_code == 400
        data = json.loads(rv.data.decode("utf-8"))
        assert "current_password" in data["message"]

        rv = self.client.post(
            "/api/v1/security/login",
            json={
                "username": ADMIN_USERNAME,
                "password": "general",
                "provider": "db",
            },
        )
        assert rv.status_code == 200

    def test_update_me_password_with_current_password(self):
        """Happy-path: password change succeeds when current_password is correct."""
        new_password = "Brand-NewP@ssw0rd!"  # noqa: S105
        original_password = "general"  # noqa: S105

        self.login(ADMIN_USERNAME, password=original_password)
        try:
            rv = self.client.put(
                "/api/v1/me/",
                json={
                    "password": new_password,
                    "current_password": original_password,
                },
            )
            assert rv.status_code == 200, rv.data

            # The new password must actually work for login.
            self.client.get("/logout/")
            self.login(ADMIN_USERNAME, password=new_password)
            rv = self.client.get(meUri)
            assert rv.status_code == 200, rv.data
        finally:
            # Always restore the original password so subsequent tests keep
            # working. Re-establish a session with whichever password is
            # currently active before issuing the restore.
            self.client.get("/logout/")
            self.login(ADMIN_USERNAME, password=new_password)
            rv = self.client.put(
                "/api/v1/me/",
                json={
                    "password": original_password,
                    "current_password": new_password,
                },
            )
            if rv.status_code != 200:
                # The password might still be the original (test failed before
                # the change took effect). Re-login with the original to leave
                # the admin user usable for downstream tests.
                self.client.get("/logout/")
                self.login(ADMIN_USERNAME, password=original_password)
            assert rv.status_code == 200, rv.data


class TestUserApi(SupersetTestCase):
    def test_avatar_with_invalid_user(self):
        self.login(ADMIN_USERNAME)
        response = self.client.get("/api/v1/user/NOT_A_USER/avatar.png")
        assert response.status_code == 404  # Assuming no user found leads to 404
        response = self.client.get("/api/v1/user/999/avatar.png")
        assert response.status_code == 404  # Assuming no user found leads to 404

    def test_avatar_valid_user_no_avatar(self):
        self.login(ADMIN_USERNAME)

        response = self.client.get("/api/v1/user/1/avatar.png", follow_redirects=False)
        assert response.status_code == 204

    @with_config({"SLACK_API_TOKEN": "dummy"})
    @with_feature_flags(SLACK_ENABLE_AVATARS=True)
    @patch("superset.views.users.api.get_user_avatar", return_value=AVATAR_URL)
    def test_avatar_with_valid_user(self, mock):
        self.login(ADMIN_USERNAME)
        response = self.client.get("/api/v1/user/1/avatar.png", follow_redirects=False)
        mock.assert_called_once_with("admin@fab.org")
        assert response.status_code == 301
        assert response.headers["Location"] == AVATAR_URL

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
"""Unit tests for ``superset.views.users.schemas``."""

import pytest
from marshmallow import ValidationError

from superset.views.users.schemas import CurrentUserPutSchema


def test_current_user_put_schema_password_requires_current_password(
    app_context: None,
) -> None:
    """A password change must require ``current_password``.

    Regression test for the missing-old-password check that previously
    allowed account takeover from a compromised session via PUT /api/v1/me/.
    """
    schema = CurrentUserPutSchema()
    with pytest.raises(ValidationError) as excinfo:
        schema.load({"password": "Brand-NewP@ssw0rd!"})
    assert "current_password" in excinfo.value.messages


def test_current_user_put_schema_password_with_current_password_ok(
    app_context: None,
) -> None:
    """A password change with ``current_password`` deserializes without error."""
    schema = CurrentUserPutSchema()
    data = schema.load(
        {
            "password": "Brand-NewP@ssw0rd!",
            "current_password": "original-password",
        }
    )
    assert data["password"] == "Brand-NewP@ssw0rd!"  # noqa: S105
    assert data["current_password"] == "original-password"  # noqa: S105


def test_current_user_put_schema_no_password_no_current_password_required(
    app_context: None,
) -> None:
    """Updating only first/last name must not require ``current_password``."""
    schema = CurrentUserPutSchema()
    data = schema.load({"first_name": "Alice", "last_name": "Anderson"})
    assert data == {"first_name": "Alice", "last_name": "Anderson"}

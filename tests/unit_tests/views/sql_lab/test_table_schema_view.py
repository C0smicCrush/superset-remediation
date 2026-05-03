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
"""
Authorization tests for ``TableSchemaView``.

Regression tests for the cross-user IDOR on ``DELETE /tableschemaview/<id>``
and ``POST /tableschemaview/<id>/expanded``: the handlers must reject requests
where the calling user is not the owner of the parent ``TabState`` row.
"""

from typing import Any
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

OWNER_ID = 7
ATTACKER_ID = 99
TABLE_SCHEMA_ID = 42


@pytest.fixture
def mock_db_session(mocker: MockerFixture) -> MagicMock:
    """Replace ``superset.views.sql_lab.views.db.session`` with a MagicMock."""
    session = MagicMock(name="db.session")
    mocker.patch(
        "superset.views.sql_lab.views.db.session",
        new=session,
    )
    return session


def _patch_owner(mocker: MockerFixture, owner_id: int | None) -> MagicMock:
    return mocker.patch(
        "superset.views.sql_lab.views._get_table_schema_owner_id",
        return_value=owner_id,
    )


def _patch_caller(mocker: MockerFixture, user_id: int) -> MagicMock:
    return mocker.patch(
        "superset.views.sql_lab.views.get_user_id",
        return_value=user_id,
    )


def test_get_table_schema_owner_id_uses_join(
    app_context: None, mocker: MockerFixture
) -> None:
    """
    The helper must look up ownership via the ``tab_state`` parent (i.e. the
    ``TabState.user_id`` resolved through ``TableSchema.tab_state_id``) rather
    than reading ``TableSchema.id`` directly.
    """
    from superset.views.sql_lab import views as sql_lab_views

    fake_session = MagicMock(name="db.session")
    fake_query = MagicMock(name="query")
    fake_session.query.return_value = fake_query
    fake_query.join.return_value = fake_query
    fake_query.filter.return_value = fake_query
    fake_query.scalar.return_value = OWNER_ID
    mocker.patch.object(sql_lab_views.db, "session", new=fake_session)

    owner = sql_lab_views._get_table_schema_owner_id(TABLE_SCHEMA_ID)

    assert owner == OWNER_ID
    fake_query.join.assert_called_once()
    fake_query.scalar.assert_called_once()


def test_delete_returns_404_when_row_missing(
    app_context: None,
    client: Any,
    full_api_access: None,
    mock_db_session: MagicMock,
    mocker: MockerFixture,
) -> None:
    _patch_owner(mocker, None)
    _patch_caller(mocker, ATTACKER_ID)

    response = client.delete(f"/tableschemaview/{TABLE_SCHEMA_ID}")

    assert response.status_code == 404
    mock_db_session.query.assert_not_called()
    mock_db_session.commit.assert_not_called()


def test_delete_rejects_cross_user_caller_with_403(
    app_context: None,
    client: Any,
    full_api_access: None,
    mock_db_session: MagicMock,
    mocker: MockerFixture,
) -> None:
    """
    A SQL Lab user calling ``DELETE /tableschemaview/<id>`` for a row owned by
    another user must receive ``403`` and the row must not be deleted.
    """
    _patch_owner(mocker, OWNER_ID)
    _patch_caller(mocker, ATTACKER_ID)

    response = client.delete(f"/tableschemaview/{TABLE_SCHEMA_ID}")

    assert response.status_code == 403
    # The ownership guard must short-circuit before any mutating SQL runs.
    mock_db_session.query.assert_not_called()
    mock_db_session.commit.assert_not_called()


def test_delete_allows_owner_with_200(
    app_context: None,
    client: Any,
    full_api_access: None,
    mock_db_session: MagicMock,
    mocker: MockerFixture,
) -> None:
    _patch_owner(mocker, OWNER_ID)
    _patch_caller(mocker, OWNER_ID)

    response = client.delete(f"/tableschemaview/{TABLE_SCHEMA_ID}")

    assert response.status_code == 200
    mock_db_session.query.assert_called_once()
    mock_db_session.commit.assert_called_once()


def test_expanded_returns_404_when_row_missing(
    app_context: None,
    client: Any,
    full_api_access: None,
    mock_db_session: MagicMock,
    mocker: MockerFixture,
) -> None:
    _patch_owner(mocker, None)
    _patch_caller(mocker, ATTACKER_ID)

    response = client.post(
        f"/tableschemaview/{TABLE_SCHEMA_ID}/expanded",
        data={"expanded": "true"},
    )

    assert response.status_code == 404
    mock_db_session.query.assert_not_called()


def test_expanded_rejects_cross_user_caller_with_403(
    app_context: None,
    client: Any,
    full_api_access: None,
    mock_db_session: MagicMock,
    mocker: MockerFixture,
) -> None:
    """
    A SQL Lab user calling ``POST /tableschemaview/<id>/expanded`` for a row
    owned by another user must receive ``403`` and the ``expanded`` flag must
    not be updated.
    """
    _patch_owner(mocker, OWNER_ID)
    _patch_caller(mocker, ATTACKER_ID)

    response = client.post(
        f"/tableschemaview/{TABLE_SCHEMA_ID}/expanded",
        data={"expanded": "true"},
    )

    assert response.status_code == 403
    mock_db_session.query.assert_not_called()


def test_expanded_allows_owner_with_200(
    app_context: None,
    client: Any,
    full_api_access: None,
    mock_db_session: MagicMock,
    mocker: MockerFixture,
) -> None:
    _patch_owner(mocker, OWNER_ID)
    _patch_caller(mocker, OWNER_ID)

    response = client.post(
        f"/tableschemaview/{TABLE_SCHEMA_ID}/expanded",
        data={"expanded": "true"},
    )

    assert response.status_code == 200
    mock_db_session.query.assert_called_once()

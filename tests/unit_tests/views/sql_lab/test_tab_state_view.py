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
"""Unit tests for mass-assignment protection in TabStateView.put()."""

import inspect
from unittest.mock import MagicMock, patch

from superset.views.sql_lab.views import TabStateView


def test_put_allowed_fields_whitelist_exists() -> None:
    """TabStateView must declare a _put_allowed_fields whitelist."""
    assert hasattr(TabStateView, "_put_allowed_fields")
    assert isinstance(TabStateView._put_allowed_fields, set)
    assert len(TabStateView._put_allowed_fields) > 0


def test_put_allowed_fields_excludes_sensitive_columns() -> None:
    """Sensitive columns must not appear in the PUT whitelist."""
    disallowed = {
        "id",
        "user_id",
        "active",
        "created_by_fk",
        "changed_by_fk",
        "created_on",
        "changed_on",
    }
    overlap = TabStateView._put_allowed_fields & disallowed
    assert overlap == set(), f"Sensitive columns in whitelist: {overlap}"


def test_put_allowed_fields_contains_expected_fields() -> None:
    """The whitelist includes every field the frontend legitimately sends."""
    expected = {
        "autorun",
        "catalog",
        "database_id",
        "extra_json",
        "hide_left_bar",
        "label",
        "latest_query_id",
        "query_limit",
        "saved_query_id",
        "schema",
        "sql",
        "template_params",
    }
    assert expected.issubset(TabStateView._put_allowed_fields)


def test_put_filters_disallowed_fields() -> None:
    """put() must silently drop fields not in the whitelist."""
    view = TabStateView()
    unwrapped_put = inspect.unwrap(view.put)

    mock_query = MagicMock()
    mock_filter = MagicMock()
    mock_query.return_value.filter_by.return_value = mock_filter

    form_data = {
        "sql": '"SELECT 1"',
        "label": '"My Tab"',
        "user_id": "999",
        "created_by_fk": "1",
    }

    mock_request = MagicMock()
    mock_request.form.to_dict.return_value = form_data
    mock_db = MagicMock()
    mock_db.session.query.return_value.filter_by.return_value = mock_filter

    with (
        patch(
            "superset.views.sql_lab.views._get_owner_id",
            return_value=42,
        ),
        patch(
            "superset.views.sql_lab.views.get_user_id",
            return_value=42,
        ),
        patch(
            "superset.views.sql_lab.views.request",
            new=mock_request,
        ),
        patch(
            "superset.views.sql_lab.views.db",
            new=mock_db,
        ),
    ):
        unwrapped_put(view, tab_state_id=1)

        update_call = mock_filter.update
        assert update_call.called
        updated_fields = update_call.call_args[0][0]

        assert "sql" in updated_fields
        assert "label" in updated_fields
        assert "user_id" not in updated_fields
        assert "created_by_fk" not in updated_fields

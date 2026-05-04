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
"""Unit tests for resource-level authorization in superset/views/api.py.

Specifically covers ``Api.query_form_data`` (the ``/api/v1/form_data/``
endpoint), which historically returned a chart's full ``form_data``
without consulting datasource RBAC. The fix calls
``security_manager.raise_for_access(chart=...)`` after loading the slice.
"""

import inspect
from unittest.mock import MagicMock, patch

import pytest

from superset.errors import ErrorLevel, SupersetError, SupersetErrorType
from superset.exceptions import SupersetSecurityException


def _security_exception() -> SupersetSecurityException:
    return SupersetSecurityException(
        SupersetError(
            message="You don't have access to this chart.",
            error_type=SupersetErrorType.CHART_SECURITY_ACCESS_ERROR,
            level=ErrorLevel.WARNING,
        )
    )


def _get_view_func(name: str):
    """Return the unwrapped body of an ``Api`` view method."""
    from superset.views.api import Api

    return inspect.unwrap(getattr(Api, name))


def _view_self() -> MagicMock:
    """Create a minimal stand-in for an ``Api`` view instance."""
    self = MagicMock()
    self.json_response = MagicMock(return_value="ok")
    return self


@patch("superset.views.api.update_time_range")
@patch("superset.views.api.security_manager", new_callable=MagicMock)
@patch("superset.views.api.db", new_callable=MagicMock)
@patch("superset.views.api.request", new_callable=MagicMock)
def test_query_form_data_raises_when_chart_access_denied(
    mock_request: MagicMock,
    mock_db: MagicMock,
    mock_security_manager: MagicMock,
    mock_update_time_range: MagicMock,
) -> None:
    """A caller without datasource access must NOT receive ``form_data``.

    Regression for the IDOR at ``/api/v1/form_data/?slice_id=N`` where the
    handler returned the chart's full configuration (filter SQL, custom
    metric SQL, datasource refs) regardless of whether the caller could
    access the chart's underlying datasource.
    """
    mock_request.args.get.return_value = "42"

    mock_slice = MagicMock()
    mock_slice.form_data = {"slice_id": 42, "secret": "should-not-be-returned"}
    (
        mock_db.session.query.return_value.filter_by.return_value.one_or_none.return_value
    ) = mock_slice

    mock_security_manager.raise_for_access.side_effect = _security_exception()

    raw_fn = _get_view_func("query_form_data")
    view = _view_self()
    with pytest.raises(SupersetSecurityException):
        raw_fn(view)

    mock_security_manager.raise_for_access.assert_called_once_with(chart=mock_slice)
    # The body must never be serialized when access is denied.
    view.json_response.assert_not_called()
    mock_update_time_range.assert_not_called()


@patch("superset.views.api.update_time_range")
@patch("superset.views.api.security_manager", new_callable=MagicMock)
@patch("superset.views.api.db", new_callable=MagicMock)
@patch("superset.views.api.request", new_callable=MagicMock)
def test_query_form_data_succeeds_for_authorised_user(
    mock_request: MagicMock,
    mock_db: MagicMock,
    mock_security_manager: MagicMock,
    mock_update_time_range: MagicMock,
) -> None:
    """Authorised callers still receive the chart ``form_data`` payload."""
    mock_request.args.get.return_value = "42"

    form_data = {"slice_id": 42, "viz_type": "table"}
    mock_slice = MagicMock()
    mock_slice.form_data = form_data
    (
        mock_db.session.query.return_value.filter_by.return_value.one_or_none.return_value
    ) = mock_slice
    mock_security_manager.raise_for_access.return_value = None

    raw_fn = _get_view_func("query_form_data")
    view = _view_self()
    raw_fn(view)

    mock_security_manager.raise_for_access.assert_called_once_with(chart=mock_slice)
    mock_update_time_range.assert_called_once()
    view.json_response.assert_called_once()
    payload = view.json_response.call_args.args[0]
    assert payload == form_data
    # Defensive: ensure the handler returns a copy (mutating must not bleed).
    assert payload is not form_data


@patch("superset.views.api.update_time_range")
@patch("superset.views.api.security_manager", new_callable=MagicMock)
@patch("superset.views.api.db", new_callable=MagicMock)
@patch("superset.views.api.request", new_callable=MagicMock)
def test_query_form_data_skips_access_check_when_no_slice_id(
    mock_request: MagicMock,
    mock_db: MagicMock,
    mock_security_manager: MagicMock,
    mock_update_time_range: MagicMock,
) -> None:
    """Without a ``slice_id`` query param the handler returns ``{}`` and never
    consults the security manager — preserves the original behaviour for
    callers that probe the endpoint without a target chart."""
    mock_request.args.get.return_value = None

    raw_fn = _get_view_func("query_form_data")
    view = _view_self()
    raw_fn(view)

    mock_security_manager.raise_for_access.assert_not_called()
    mock_db.session.query.assert_not_called()
    mock_update_time_range.assert_called_once_with({})
    view.json_response.assert_called_once_with({})


@patch("superset.views.api.update_time_range")
@patch("superset.views.api.security_manager", new_callable=MagicMock)
@patch("superset.views.api.db", new_callable=MagicMock)
@patch("superset.views.api.request", new_callable=MagicMock)
def test_query_form_data_skips_access_check_when_slice_missing(
    mock_request: MagicMock,
    mock_db: MagicMock,
    mock_security_manager: MagicMock,
    mock_update_time_range: MagicMock,
) -> None:
    """When the slice does not exist the handler returns ``{}`` without
    invoking the access check (nothing to authorise against)."""
    mock_request.args.get.return_value = "999"
    (
        mock_db.session.query.return_value.filter_by.return_value.one_or_none.return_value
    ) = None

    raw_fn = _get_view_func("query_form_data")
    view = _view_self()
    raw_fn(view)

    mock_security_manager.raise_for_access.assert_not_called()
    mock_update_time_range.assert_called_once_with({})
    view.json_response.assert_called_once_with({})

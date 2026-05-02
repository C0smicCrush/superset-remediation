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
Regression tests guarding against the cookie-injection sink at the seven
``/api/v1/.../export/`` endpoints.

The legitimate frontend (``superset-frontend/src/utils/export.ts``) does not
send a ``token`` query parameter, so each export handler must not call
``response.set_cookie(token, ...)`` on attacker-controlled input. This test
asserts the sink has been removed across all affected handlers and is a
guardrail against accidental reintroduction.
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest

# (module path, attribute path inside module) for every previously affected
# export handler.
EXPORT_HANDLERS: list[tuple[str, str]] = [
    ("superset.dashboards.api", "DashboardRestApi.export"),
    ("superset.dashboards.api", "DashboardRestApi.export_as_example"),
    ("superset.charts.api", "ChartRestApi.export"),
    ("superset.datasets.api", "DatasetRestApi.export"),
    ("superset.databases.api", "DatabaseRestApi.export"),
    ("superset.queries.saved_queries.api", "SavedQueryRestApi.export"),
    ("superset.themes.api", "ThemeRestApi.export"),
]


def _resolve_handler(module_path: str, attr_path: str) -> Any:
    import importlib

    module = importlib.import_module(module_path)
    obj: Any = module
    for part in attr_path.split("."):
        obj = getattr(obj, part)
    return obj


@pytest.mark.parametrize("module_path,attr_path", EXPORT_HANDLERS)
def test_export_handler_does_not_set_attacker_controlled_cookie(
    module_path: str, attr_path: str
) -> None:
    """The export handler must not write a cookie keyed by the request's
    ``token`` query parameter.

    Re-introducing ``response.set_cookie(token, ...)`` would re-open
    a CSRF / cookie-tossing primitive that lets a remote attacker overwrite
    arbitrary Superset cookies (including ``session``) at ``Path=/`` via a
    one-click top-level GET navigation.
    """
    handler = _resolve_handler(module_path, attr_path)
    source = inspect.getsource(handler)

    assert 'request.args.get("token")' not in source, (
        f"{module_path}:{attr_path} still reads an unvalidated `token` "
        f"query parameter; this enables attacker-controlled cookie injection."
    )
    assert "set_cookie(token" not in source, (
        f"{module_path}:{attr_path} still calls `response.set_cookie(token, ...)`"
        f" with an attacker-controlled cookie name; this is a CSRF / "
        f"cookie-tossing sink."
    )

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
"""Global ORM visibility filter for soft-delete-enabled models.

A ``do_orm_execute`` event listener automatically appends
``WHERE deleted_at IS NULL`` to every ORM SELECT that targets a model using
:class:`~superset.models.helpers.SoftDeleteMixin`. This ensures that
soft-deleted rows are hidden from all existing query paths without requiring
changes at every call site.

The filter is bypassed when:

* The query carries the ``skip_visibility_filter=True`` execution option
  (used by restore commands and import/export tooling).
* Flask's request-scoped ``g.skip_soft_delete_filter`` flag is truthy (used
  by the ``include_deleted`` list-endpoint parameter).
"""

from __future__ import annotations

import logging
from typing import Any

from flask import g, has_app_context
from sqlalchemy import event, orm
from sqlalchemy.orm import ORMExecuteState, with_loader_criteria

from superset.extensions import db
from superset.models.helpers import SoftDeleteMixin

logger = logging.getLogger(__name__)


def _should_skip_filter(orm_execute_state: ORMExecuteState) -> bool:
    """Return ``True`` if the filter should be bypassed for this statement."""

    if orm_execute_state.execution_options.get("skip_visibility_filter"):
        return True

    if has_app_context() and getattr(g, "skip_soft_delete_filter", False):
        return True

    return False


def _soft_delete_listener(orm_execute_state: ORMExecuteState) -> None:
    """Append ``deleted_at IS NULL`` to every SELECT on a soft-delete model."""

    if not orm_execute_state.is_select:
        return

    if _should_skip_filter(orm_execute_state):
        return

    orm_execute_state.statement = orm_execute_state.statement.options(
        with_loader_criteria(
            SoftDeleteMixin,
            lambda cls: cls.deleted_at.is_(None),
            include_aliases=True,
        )
    )


def register_soft_delete_listener(session: orm.Session | Any = None) -> None:
    """Attach the visibility filter to the given session (defaults to ``db.session``).

    Safe to call multiple times — subsequent registrations are no-ops because
    SQLAlchemy deduplicates ``event.listen`` calls with the same target and
    function.
    """

    target = session if session is not None else db.session
    if not event.contains(target, "do_orm_execute", _soft_delete_listener):
        event.listen(target, "do_orm_execute", _soft_delete_listener)

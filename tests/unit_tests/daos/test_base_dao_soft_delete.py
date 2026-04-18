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
"""Unit tests for :meth:`BaseDAO.delete` / :meth:`BaseDAO.hard_delete` routing.

These tests cover the bounded DAO-routing increment of the Soft Delete SIP: the
``delete`` classmethod must call ``soft_delete`` on instances that inherit from
:class:`SoftDeleteMixin` and fall through to ``Session.delete`` for everything
else. The global ``do_orm_execute`` visibility filter, restore commands,
``/restore`` endpoints, and ``include_deleted`` listing parameter remain
explicitly out of scope.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from superset.daos.base import BaseDAO
from superset.models.helpers import SoftDeleteMixin


class _SoftDeletable(SoftDeleteMixin):
    """Plain object that simulates a SoftDeleteMixin-enabled ORM row.

    We avoid instantiating a real SQLAlchemy model here — the DAO branch is
    based on ``isinstance(item, SoftDeleteMixin)`` and calls ``soft_delete()``
    on the instance, so a lightweight stand-in is sufficient and keeps the
    test focused on the routing itself.
    """

    def __init__(self) -> None:
        self.deleted_at = None


class _HardOnly:
    """Plain object that does NOT inherit SoftDeleteMixin."""


def test_delete_routes_soft_delete_mixin_instances_through_soft_delete() -> None:
    soft_item = _SoftDeletable()

    with patch("superset.daos.base.db.session") as mock_session:
        BaseDAO.delete([soft_item])

    assert soft_item.deleted_at is not None
    mock_session.delete.assert_not_called()


def test_delete_routes_non_mixin_instances_through_session_delete() -> None:
    hard_item = _HardOnly()

    with patch("superset.daos.base.db.session") as mock_session:
        BaseDAO.delete([hard_item])

    mock_session.delete.assert_called_once_with(hard_item)


def test_delete_handles_mixed_items_in_single_call() -> None:
    soft_item = _SoftDeletable()
    hard_item = _HardOnly()

    with patch("superset.daos.base.db.session") as mock_session:
        BaseDAO.delete([soft_item, hard_item])

    assert soft_item.deleted_at is not None
    mock_session.delete.assert_called_once_with(hard_item)


def test_delete_is_idempotent_for_already_soft_deleted_rows() -> None:
    soft_item = _SoftDeletable()
    soft_item.soft_delete()
    original_ts = soft_item.deleted_at

    with patch("superset.daos.base.db.session") as mock_session:
        BaseDAO.delete([soft_item])

    assert soft_item.deleted_at == original_ts
    mock_session.delete.assert_not_called()


def test_hard_delete_always_calls_session_delete_even_for_soft_mixin() -> None:
    soft_item = _SoftDeletable()
    hard_item = _HardOnly()

    with patch("superset.daos.base.db.session") as mock_session:
        BaseDAO.hard_delete([soft_item, hard_item])

    assert mock_session.delete.call_count == 2
    mock_session.delete.assert_any_call(soft_item)
    mock_session.delete.assert_any_call(hard_item)
    assert soft_item.deleted_at is None


def test_delete_noop_for_empty_list() -> None:
    with patch("superset.daos.base.db.session") as mock_session:
        BaseDAO.delete([])

    mock_session.delete.assert_not_called()


def test_hard_delete_is_accessible_for_explicit_purge_paths() -> None:
    """Documented escape hatch: callers (e.g. import pipeline) must be able to
    hard-delete a soft-delete-enabled row without routing through soft_delete.
    """
    soft_item = _SoftDeletable()

    with patch("superset.daos.base.db.session") as mock_session:
        BaseDAO.hard_delete([soft_item])

    mock_session.delete.assert_called_once_with(soft_item)
    assert soft_item.deleted_at is None


def test_mock_session_not_touched_during_soft_delete_only_call() -> None:
    """Soft-delete-only calls must not dispatch any Session mutation.

    Global ORM visibility filtering is deferred to a follow-up PR, so the
    session should see zero writes for purely soft-delete invocations.
    """
    soft_item = _SoftDeletable()

    mock_session = MagicMock()
    with patch("superset.daos.base.db.session", mock_session):
        BaseDAO.delete([soft_item])

    mock_session.delete.assert_not_called()
    mock_session.flush.assert_not_called()
    mock_session.commit.assert_not_called()

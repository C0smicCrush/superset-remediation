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
"""Tests for soft-delete routing in ``BaseDAO``.

Verifies that :meth:`BaseDAO.delete` routes soft-delete-enabled models
through :meth:`BaseDAO.soft_delete` (setting ``deleted_at``) while other
models are hard-deleted via ``Session.delete``.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy.orm.session import Session

from superset.daos.base import BaseDAO
from superset.models.slice import Slice


@pytest.fixture
def chart(session: Session) -> Slice:
    Slice.metadata.create_all(session.get_bind())  # pylint: disable=no-member
    item = Slice(slice_name="chart-to-delete", datasource_type="table")
    session.add(item)
    session.flush()
    return item


def test_base_dao_delete_routes_soft_delete_for_mixin_models(
    session: Session, chart: Slice
) -> None:
    with patch.object(BaseDAO, "hard_delete") as hard_delete:
        BaseDAO.delete([chart])

    hard_delete.assert_not_called()
    assert chart.deleted_at is not None
    assert chart.is_deleted is True


def test_base_dao_delete_routes_hard_delete_for_plain_models(
    session: Session,
) -> None:
    class _Plain:
        pass

    item = _Plain()
    with (
        patch.object(BaseDAO, "soft_delete") as soft_delete,
        patch.object(BaseDAO, "hard_delete") as hard_delete,
    ):
        BaseDAO.delete([item])

    soft_delete.assert_not_called()
    hard_delete.assert_called_once_with(item)


def test_base_dao_restore_clears_deleted_at(session: Session, chart: Slice) -> None:
    BaseDAO.delete([chart])
    session.flush()
    assert chart.is_deleted is True

    BaseDAO.restore(chart)
    session.flush()

    assert chart.deleted_at is None
    assert chart.is_deleted is False

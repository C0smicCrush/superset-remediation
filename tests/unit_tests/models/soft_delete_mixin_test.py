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
"""Unit tests for ``SoftDeleteMixin``.

Covers the instance-level helpers (``soft_delete``/``restore``), the
``is_deleted`` hybrid property, and the ``not_deleted`` class-level filter.
Also verifies that the mixin has been wired into ``Slice``, ``Dashboard`` and
``SqlaTable`` and that the ``deleted_at`` column is indexed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import declarative_base, Session

from superset.models.helpers import SoftDeleteMixin

Base: Any = declarative_base()


class _SoftDeletable(SoftDeleteMixin, Base):
    """Minimal model used to exercise the mixin in isolation."""

    __tablename__ = "soft_deletable"

    id = sa.Column(sa.Integer, primary_key=True)
    name = sa.Column(sa.String(50))


@pytest.fixture
def session() -> Session:
    engine = sa.create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session


def test_deleted_at_column_is_nullable_and_indexed() -> None:
    """The mixin must add a nullable, indexed ``deleted_at`` column."""
    column = _SoftDeletable.__table__.c.deleted_at
    assert column.nullable is True
    assert isinstance(column.type, sa.DateTime)
    assert column.index is True


def test_default_row_is_not_deleted(session: Session) -> None:
    row = _SoftDeletable(name="active")
    session.add(row)
    session.commit()

    assert row.deleted_at is None
    assert row.is_deleted is False


def test_soft_delete_sets_deleted_at(session: Session) -> None:
    row = _SoftDeletable(name="target")
    session.add(row)
    session.commit()

    before = datetime.now()
    row.soft_delete()
    session.commit()

    assert row.deleted_at is not None
    assert row.deleted_at >= before
    assert row.is_deleted is True


def test_soft_delete_respects_explicit_timestamp(session: Session) -> None:
    row = _SoftDeletable(name="target")
    session.add(row)
    session.commit()

    explicit = datetime(2026, 1, 2, 3, 4, 5)
    row.soft_delete(deleted_at=explicit)
    session.commit()

    assert row.deleted_at == explicit


def test_soft_delete_is_idempotent(session: Session) -> None:
    row = _SoftDeletable(name="target")
    session.add(row)
    row.soft_delete(deleted_at=datetime(2026, 1, 1))
    session.commit()

    # A second call must not overwrite the original timestamp.
    row.soft_delete(deleted_at=datetime(2030, 1, 1))
    assert row.deleted_at == datetime(2026, 1, 1)


def test_restore_clears_deleted_at(session: Session) -> None:
    row = _SoftDeletable(name="target")
    session.add(row)
    row.soft_delete()
    session.commit()

    assert row.is_deleted is True
    row.restore()
    session.commit()

    assert row.deleted_at is None
    assert row.is_deleted is False


def test_not_deleted_filter_excludes_soft_deleted_rows(session: Session) -> None:
    active = _SoftDeletable(name="active")
    deleted = _SoftDeletable(name="deleted")
    deleted.soft_delete()
    session.add_all([active, deleted])
    session.commit()

    rows = session.query(_SoftDeletable).filter(_SoftDeletable.not_deleted()).all()
    names = [row.name for row in rows]

    assert names == ["active"]


def test_is_deleted_sql_expression_selects_soft_deleted_rows(
    session: Session,
) -> None:
    active = _SoftDeletable(name="active")
    deleted = _SoftDeletable(name="deleted")
    deleted.soft_delete()
    session.add_all([active, deleted])
    session.commit()

    rows = session.query(_SoftDeletable).filter(_SoftDeletable.is_deleted).all()
    names = [row.name for row in rows]

    assert names == ["deleted"]


def test_mixin_is_wired_into_core_models() -> None:
    """``Slice``, ``Dashboard`` and ``SqlaTable`` must expose ``deleted_at``."""
    from superset.connectors.sqla.models import SqlaTable
    from superset.models.dashboard import Dashboard
    from superset.models.slice import Slice

    for model in (Slice, Dashboard, SqlaTable):
        assert issubclass(model, SoftDeleteMixin)
        column = model.__table__.c.deleted_at
        assert column.nullable is True
        assert isinstance(column.type, sa.DateTime)
        assert column.index is True

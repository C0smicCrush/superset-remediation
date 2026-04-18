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
"""Unit tests for :class:`SoftDeleteMixin`.

These tests exercise the mixin in isolation against an in-memory SQLite
database so they run without requiring the full Superset application stack.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Session

from superset.models.helpers import SoftDeleteMixin


class Base(DeclarativeBase):
    pass


class _ExampleModel(Base, SoftDeleteMixin):
    __tablename__ = "soft_delete_example"

    id = sa.Column(sa.Integer, primary_key=True)
    name = sa.Column(sa.String(32), nullable=False)


@pytest.fixture
def session() -> Session:
    engine = sa.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as sess:
        yield sess


def test_deleted_at_column_is_nullable_and_defaults_to_none(session: Session) -> None:
    row = _ExampleModel(name="a")
    session.add(row)
    session.commit()

    assert row.deleted_at is None
    assert row.is_deleted is False


def test_deleted_at_column_is_indexed() -> None:
    column = _ExampleModel.__table__.c.deleted_at
    assert column.nullable is True
    assert column.index is True


def test_soft_delete_sets_deleted_at_to_a_recent_timestamp(session: Session) -> None:
    row = _ExampleModel(name="a")
    session.add(row)
    session.commit()

    before = datetime.utcnow()
    row.soft_delete()
    after = datetime.utcnow()
    session.commit()

    assert row.deleted_at is not None
    assert (
        before - timedelta(seconds=1) <= row.deleted_at <= after + timedelta(seconds=1)
    )
    assert row.is_deleted is True


def test_soft_delete_accepts_explicit_timestamp(session: Session) -> None:
    row = _ExampleModel(name="a")
    session.add(row)
    session.commit()

    stamp = datetime(2024, 1, 2, 3, 4, 5)
    row.soft_delete(when=stamp)
    session.commit()

    assert row.deleted_at == stamp


def test_soft_delete_is_idempotent(session: Session) -> None:
    row = _ExampleModel(name="a")
    session.add(row)
    session.commit()

    first = datetime(2024, 1, 2, 3, 4, 5)
    row.soft_delete(when=first)
    session.commit()

    # Calling soft_delete again must not overwrite the original timestamp.
    row.soft_delete(when=datetime(2025, 6, 7, 8, 9, 10))
    session.commit()

    assert row.deleted_at == first


def test_restore_clears_deleted_at(session: Session) -> None:
    row = _ExampleModel(name="a")
    session.add(row)
    session.commit()

    row.soft_delete()
    session.commit()
    assert row.is_deleted is True

    row.restore()
    session.commit()
    assert row.deleted_at is None
    assert row.is_deleted is False


def test_not_deleted_filter_excludes_soft_deleted_rows(session: Session) -> None:
    kept = _ExampleModel(name="kept")
    deleted = _ExampleModel(name="deleted")
    session.add_all([kept, deleted])
    session.commit()

    deleted.soft_delete()
    session.commit()

    visible = session.query(_ExampleModel).filter(_ExampleModel.not_deleted()).all()

    assert [r.name for r in visible] == ["kept"]


def test_mixin_does_not_auto_hide_rows_from_unfiltered_queries(
    session: Session,
) -> None:
    """The mixin itself must not install a global visibility filter.

    Global ``do_orm_execute`` filtering is an explicit follow-up; this
    increment ships only the column + helpers, so unfiltered queries must
    continue to return soft-deleted rows.
    """

    kept = _ExampleModel(name="kept")
    deleted = _ExampleModel(name="deleted")
    session.add_all([kept, deleted])
    session.commit()

    deleted.soft_delete()
    session.commit()

    all_rows = session.query(_ExampleModel).all()
    assert sorted(r.name for r in all_rows) == ["deleted", "kept"]

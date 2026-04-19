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
"""Unit tests for the global soft-delete ORM visibility filter.

Uses an in-memory SQLite session with a standalone ``SoftDeleteMixin`` model
so the filter's SQLAlchemy event behaviour can be exercised without booting
the full Superset app.
"""

from __future__ import annotations

from typing import Any, Iterator

import pytest
import sqlalchemy as sa
from flask import Flask
from sqlalchemy.orm import declarative_base, Session

from superset.models.helpers import SoftDeleteMixin
from superset.models.soft_delete import (
    _soft_delete_listener,
    register_soft_delete_listener,
)

Base: Any = declarative_base()


class _SoftDeletable(SoftDeleteMixin, Base):
    __tablename__ = "soft_deletable_filter"

    id = sa.Column(sa.Integer, primary_key=True)
    name = sa.Column(sa.String(50))


@pytest.fixture
def session() -> Iterator[Session]:
    engine = sa.create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        register_soft_delete_listener(db_session)
        try:
            yield db_session
        finally:
            sa.event.remove(db_session, "do_orm_execute", _soft_delete_listener)


@pytest.fixture
def seeded(session: Session) -> Session:
    active = _SoftDeletable(name="active")
    deleted = _SoftDeletable(name="deleted")
    deleted.soft_delete()
    session.add_all([active, deleted])
    session.commit()
    session.expire_all()
    return session


def test_filter_hides_soft_deleted_rows_from_default_queries(
    seeded: Session,
) -> None:
    rows = seeded.query(_SoftDeletable).all()
    assert [row.name for row in rows] == ["active"]


def test_skip_visibility_filter_option_bypasses_filter(seeded: Session) -> None:
    rows = (
        seeded.query(_SoftDeletable)
        .execution_options(skip_visibility_filter=True)
        .all()
    )
    assert sorted(row.name for row in rows) == ["active", "deleted"]


def test_flask_g_flag_bypasses_filter(seeded: Session) -> None:
    app = Flask(__name__)
    with app.app_context():
        from flask import g

        g.skip_soft_delete_filter = True
        rows = seeded.query(_SoftDeletable).all()

    assert sorted(row.name for row in rows) == ["active", "deleted"]


def test_filter_does_not_affect_non_soft_delete_models(session: Session) -> None:
    class _Plain(Base):
        __tablename__ = "plain_model"

        id = sa.Column(sa.Integer, primary_key=True)
        name = sa.Column(sa.String(50))

    Base.metadata.create_all(session.get_bind(), tables=[_Plain.__table__])
    session.add_all([_Plain(name="a"), _Plain(name="b")])
    session.commit()

    rows = session.query(_Plain).all()
    assert sorted(row.name for row in rows) == ["a", "b"]


def test_register_is_idempotent(session: Session) -> None:
    register_soft_delete_listener(session)
    register_soft_delete_listener(session)
    # Listener de-duplication means rows should still be filtered exactly once.
    deleted = _SoftDeletable(name="deleted")
    deleted.soft_delete()
    session.add(deleted)
    session.commit()

    assert session.query(_SoftDeletable).all() == []

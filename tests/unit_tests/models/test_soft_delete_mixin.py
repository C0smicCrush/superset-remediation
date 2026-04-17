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
"""Unit tests for :class:`superset.models.helpers.SoftDeleteMixin`.

These tests exercise the bounded first increment of the soft-delete SIP: the
mixin's column, hybrid property, instance methods, and class-level filter
helper. They intentionally use a standalone SQLAlchemy declarative base with
an in-memory SQLite engine so that the mixin contract can be validated
without pulling in the full Superset app context.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import declarative_base, sessionmaker

from superset.models.helpers import SoftDeleteMixin

Base = declarative_base()


class Widget(Base, SoftDeleteMixin):
    __tablename__ = "widget"
    id = sa.Column(sa.Integer, primary_key=True)
    name = sa.Column(sa.String(50), nullable=False)


@pytest.fixture
def session():
    engine = sa.create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    db_session = session_factory()
    try:
        yield db_session
    finally:
        db_session.close()
        Base.metadata.drop_all(engine)


def test_deleted_at_column_defaults_to_none(session):
    widget = Widget(name="w1")
    session.add(widget)
    session.commit()

    assert widget.deleted_at is None
    assert widget.is_deleted is False


def test_soft_delete_sets_timestamp(session):
    widget = Widget(name="w2")
    session.add(widget)
    session.commit()

    before = datetime.now() - timedelta(seconds=1)
    widget.soft_delete()
    session.commit()
    after = datetime.now() + timedelta(seconds=1)

    assert widget.deleted_at is not None
    assert before <= widget.deleted_at <= after
    assert widget.is_deleted is True


def test_soft_delete_is_idempotent(session):
    widget = Widget(name="w3")
    session.add(widget)
    session.commit()

    widget.soft_delete()
    session.commit()
    first_deleted_at = widget.deleted_at

    widget.soft_delete()
    session.commit()

    assert widget.deleted_at == first_deleted_at


def test_soft_delete_accepts_explicit_timestamp(session):
    widget = Widget(name="w4")
    session.add(widget)
    session.commit()

    ts = datetime(2024, 1, 1, 12, 0, 0)
    widget.soft_delete(deleted_at=ts)
    session.commit()

    assert widget.deleted_at == ts


def test_restore_clears_deleted_at(session):
    widget = Widget(name="w5")
    session.add(widget)
    session.commit()

    widget.soft_delete()
    session.commit()
    assert widget.is_deleted is True

    widget.restore()
    session.commit()

    assert widget.deleted_at is None
    assert widget.is_deleted is False


def test_not_deleted_class_filter(session):
    alive = Widget(name="alive")
    dead = Widget(name="dead")
    session.add_all([alive, dead])
    session.commit()

    dead.soft_delete()
    session.commit()

    rows = session.query(Widget).filter(Widget.not_deleted()).all()
    names = {row.name for row in rows}
    assert names == {"alive"}


def test_is_deleted_expression_in_filter(session):
    alive = Widget(name="alive")
    dead = Widget(name="dead")
    session.add_all([alive, dead])
    session.commit()

    dead.soft_delete()
    session.commit()

    deleted_rows = session.query(Widget).filter(Widget.is_deleted).all()
    assert {row.name for row in deleted_rows} == {"dead"}


def test_deleted_at_index_is_created():
    indexes = {index.name for index in Widget.__table__.indexes}
    assert any("deleted_at" in name for name in indexes)

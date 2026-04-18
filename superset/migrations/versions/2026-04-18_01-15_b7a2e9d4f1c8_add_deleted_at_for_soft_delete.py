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
"""Add deleted_at for soft delete (SIP first increment).

Adds a nullable, indexed ``deleted_at`` DateTime column to ``slices``,
``dashboards``, and ``tables``. Purely additive; the column defaults to NULL
so existing rows are unaffected and no behaviour changes for any existing
API, DAO, or view: DAO routing and the global visibility filter are
intentionally deferred to follow-up increments.

Revision ID: b7a2e9d4f1c8
Revises: ce6bd21901ab
Create Date: 2026-04-18 01:15:00.000000

"""

import sqlalchemy as sa

from superset.migrations.shared.utils import (  # noqa: E402
    add_columns,
    create_index,
    drop_columns,
    drop_index,
)

# revision identifiers, used by Alembic.
revision = "b7a2e9d4f1c8"
down_revision = "ce6bd21901ab"

SOFT_DELETE_TABLES = ("slices", "dashboards", "tables")


def _index_name(table_name: str) -> str:
    return f"ix_{table_name}_deleted_at"


def upgrade() -> None:
    for table_name in SOFT_DELETE_TABLES:
        add_columns(
            table_name,
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
        )
        create_index(
            table_name=table_name,
            index_name=_index_name(table_name),
            columns=["deleted_at"],
        )


def downgrade() -> None:
    for table_name in SOFT_DELETE_TABLES:
        drop_index(table_name=table_name, index_name=_index_name(table_name))
        drop_columns(table_name, "deleted_at")

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
"""add deleted_at soft delete column to slices, dashboards, and tables

Revision ID: b7d4f8e9a1c2
Revises: ce6bd21901ab
Create Date: 2026-04-18 22:30:00.000000

"""

import sqlalchemy as sa

from superset.migrations.shared.utils import (
    add_columns,
    create_index,
    drop_columns,
    drop_index,
)

# revision identifiers, used by Alembic.
revision = "b7d4f8e9a1c2"
down_revision = "ce6bd21901ab"


SOFT_DELETE_TABLES = ("slices", "dashboards", "tables")


def _index_name(table_name: str) -> str:
    return f"ix_{table_name}_deleted_at"


def upgrade():
    """Add nullable ``deleted_at`` column and supporting index to the
    slices, dashboards, and tables tables to support soft deletes.
    """
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


def downgrade():
    """Drop the ``deleted_at`` column and its index from the
    slices, dashboards, and tables tables.
    """
    for table_name in SOFT_DELETE_TABLES:
        drop_index(
            table_name=table_name,
            index_name=_index_name(table_name),
        )
        drop_columns(
            table_name,
            "deleted_at",
        )

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
"""add deleted_at to slices, dashboards, and tables

Revision ID: 033a2fd8ec9a
Revises: ce6bd21901ab
Create Date: 2026-04-17 21:35:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "033a2fd8ec9a"
down_revision = "ce6bd21901ab"

# Tables receiving the soft-delete column as part of the SoftDeleteMixin
# skeleton. Keep this list aligned with the mixin application in the ORM
# models; see ``superset.models.helpers.SoftDeleteMixin``.
SOFT_DELETE_TABLES = ("slices", "dashboards", "tables")


def _index_name(table_name: str) -> str:
    return f"ix_{table_name}_deleted_at"


def upgrade():
    for table_name in SOFT_DELETE_TABLES:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.add_column(
                sa.Column("deleted_at", sa.DateTime(), nullable=True),
            )
            batch_op.create_index(
                _index_name(table_name),
                ["deleted_at"],
                unique=False,
            )


def downgrade():
    for table_name in SOFT_DELETE_TABLES:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_index(_index_name(table_name))
            batch_op.drop_column("deleted_at")

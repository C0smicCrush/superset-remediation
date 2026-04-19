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
import logging
from functools import partial
from typing import Optional

from superset import security_manager
from superset.commands.base import BaseCommand
from superset.commands.dashboard.exceptions import (
    DashboardForbiddenError,
    DashboardNotDeletedError,
    DashboardNotFoundError,
    DashboardRestoreFailedError,
)
from superset.daos.dashboard import DashboardDAO
from superset.exceptions import SupersetSecurityException
from superset.extensions import db
from superset.models.dashboard import Dashboard
from superset.utils.decorators import on_error, transaction

logger = logging.getLogger(__name__)


class RestoreDashboardCommand(BaseCommand):
    """Clear ``deleted_at`` on a soft-deleted dashboard, making it active again."""

    def __init__(self, model_id: int):
        self._model_id = model_id
        self._model: Optional[Dashboard] = None

    @transaction(on_error=partial(on_error, reraise=DashboardRestoreFailedError))
    def run(self) -> None:
        self.validate()
        assert self._model
        DashboardDAO.restore(self._model)

    def validate(self) -> None:
        query = db.session.query(Dashboard).execution_options(
            skip_visibility_filter=True
        )
        self._model = query.filter(Dashboard.id == self._model_id).one_or_none()
        if not self._model:
            raise DashboardNotFoundError()
        if not self._model.is_deleted:
            raise DashboardNotDeletedError()
        try:
            security_manager.raise_for_ownership(self._model)
        except SupersetSecurityException as ex:
            raise DashboardForbiddenError() from ex

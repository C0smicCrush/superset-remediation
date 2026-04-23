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
import gzip
import ipaddress
import logging
import re
import socket
from typing import Any
from urllib import request
from urllib.parse import urlparse

import pandas as pd
from flask import current_app as app
from sqlalchemy import BigInteger, Boolean, Date, DateTime, Float, String, Text
from sqlalchemy.exc import MultipleResultsFound
from sqlalchemy.sql.visitors import VisitableType

from superset import db, security_manager
from superset.commands.dataset.exceptions import DatasetForbiddenDataURI
from superset.commands.exceptions import ImportFailedError
from superset.connectors.sqla.models import SqlaTable
from superset.models.core import Database
from superset.sql.parse import Table
from superset.utils import json
from superset.utils.core import get_user

logger = logging.getLogger(__name__)

# Schemes that may reach the SSRF-sensitive ``urlopen`` sink. Only ``http`` and
# ``https`` are accepted from untrusted (schema-validated) inputs. ``file`` is
# allowed because :func:`superset.examples.helpers.normalize_example_data_url`
# rewrites trusted ``examples://`` identifiers to ``file://`` paths inside the
# examples folder (with its own path-traversal protection) before this
# validator runs; the marshmallow ``URL`` field used by the import schema
# rejects ``file://`` submissions from end users.
_ALLOWED_URL_SCHEMES = frozenset({"http", "https"})
_TRUSTED_LOCAL_URL_SCHEMES = frozenset({"file"})

CHUNKSIZE = 512
VARCHAR = re.compile(r"VARCHAR\((\d+)\)", re.IGNORECASE)

JSON_KEYS = {"params", "template_params", "extra"}


type_map = {
    "BOOLEAN": Boolean(),
    "VARCHAR": String(255),
    "STRING": String(255),
    "TEXT": Text(),
    "BIGINT": BigInteger(),
    "FLOAT": Float(),
    "FLOAT64": Float(),
    "DOUBLE PRECISION": Float(),
    "DATE": Date(),
    "DATETIME": DateTime(),
    "TIMESTAMP WITHOUT TIME ZONE": DateTime(timezone=False),
    "TIMESTAMP WITH TIME ZONE": DateTime(timezone=True),
}


def get_sqla_type(native_type: str) -> VisitableType:
    if native_type.upper() in type_map:
        return type_map[native_type.upper()]

    if match := VARCHAR.match(native_type):
        size = int(match.group(1))
        return String(size)

    raise Exception(  # pylint: disable=broad-exception-raised
        f"Unknown type: {native_type}"
    )


def get_dtype(df: pd.DataFrame, dataset: SqlaTable) -> dict[str, VisitableType]:
    return {
        column.column_name: get_sqla_type(column.type)
        for column in dataset.columns
        if column.column_name in df.keys()
    }


def _is_unsafe_ip(ip_str: str) -> bool:
    """Return True if ``ip_str`` points at a non-routable / sensitive address.

    Any of the following IP categories are treated as unsafe SSRF targets:
    private (RFC1918), loopback, link-local (e.g. cloud IMDS
    ``169.254.169.254``), multicast, reserved, or unspecified.
    """
    try:
        ip_obj = ipaddress.ip_address(ip_str)
    except ValueError:
        return True
    return (
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_reserved
        or ip_obj.is_unspecified
    )


def _validate_remote_host(host: str) -> None:
    """Resolve ``host`` and reject any result that maps to an unsafe IP.

    Raises :class:`DatasetForbiddenDataURI` if DNS resolution fails or any
    returned address is private/loopback/link-local/multicast/reserved.
    Every address returned by :func:`socket.getaddrinfo` is checked so that
    DNS rebinding or dual-stack responses cannot bypass the filter.
    """
    if not host:
        raise DatasetForbiddenDataURI()

    # Fast path: the host is already a literal IP address.
    try:
        literal = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        literal = None
    if literal is not None:
        if _is_unsafe_ip(str(literal)):
            raise DatasetForbiddenDataURI()
        return

    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as ex:
        raise DatasetForbiddenDataURI() from ex

    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            raise DatasetForbiddenDataURI()
        resolved_ip = sockaddr[0]
        if _is_unsafe_ip(resolved_ip):
            raise DatasetForbiddenDataURI()


def validate_data_uri(data_uri: str) -> None:
    """
    Validate that the data URI is safe to fetch from the dataset importer.

    This applies multiple independent layers of defense so that a
    misconfigured ``DATASET_IMPORT_ALLOWED_DATA_URLS`` alone cannot expose the
    importer to server-side request forgery:

    1. The URL scheme must be ``http``/``https``. Internally-produced
       ``file://`` URLs (emitted by
       :func:`superset.examples.helpers.normalize_example_data_url`) are
       permitted because they have their own path-traversal protection and are
       unreachable via user-submitted YAML (marshmallow's ``URL`` field
       rejects the ``file`` scheme).
    2. The URL must match one of the operator-configured allowlist regexes in
       ``DATASET_IMPORT_ALLOWED_DATA_URLS``. The shipped default is an empty
       list, which forces operators to explicitly opt in to remote import
       sources.
    3. For ``http``/``https`` URLs, the hostname is resolved via DNS and every
       returned address is checked. Any address that is private, loopback,
       link-local (including cloud instance metadata at
       ``169.254.169.254``), multicast, reserved, or unspecified is rejected.

    :raises DatasetForbiddenDataURI: if any layer rejects the URL.
    """
    parsed = urlparse(data_uri)
    scheme = (parsed.scheme or "").lower()

    # Internally-normalized example URIs bypass the remote-URL checks because
    # they point at vendored local files inside the examples folder.
    if scheme in _TRUSTED_LOCAL_URL_SCHEMES:
        return

    if scheme not in _ALLOWED_URL_SCHEMES:
        raise DatasetForbiddenDataURI()

    allowed_urls = app.config["DATASET_IMPORT_ALLOWED_DATA_URLS"]
    matched = False
    for allowed_url in allowed_urls:
        try:
            match = re.match(allowed_url, data_uri)
        except re.error:
            logger.exception(
                "Invalid regular expression on DATASET_IMPORT_ALLOWED_URLS"
            )
            raise
        if match:
            matched = True
            break
    if not matched:
        raise DatasetForbiddenDataURI()

    _validate_remote_host(parsed.hostname or "")


def import_dataset(  # noqa: C901
    config: dict[str, Any],
    overwrite: bool = False,
    force_data: bool = False,
    ignore_permissions: bool = False,
) -> SqlaTable:
    can_write = ignore_permissions or security_manager.can_access(
        "can_write",
        "Dataset",
    )
    existing = db.session.query(SqlaTable).filter_by(uuid=config["uuid"]).first()
    user = get_user()
    if existing:
        if overwrite and can_write and user:
            if user not in existing.owners and not security_manager.is_admin():
                raise ImportFailedError(
                    "A dataset already exists and user doesn't "
                    "have permissions to overwrite it"
                )
        if not overwrite or not can_write:
            return existing
        config["id"] = existing.id

    elif not can_write:
        raise ImportFailedError(
            "Dataset doesn't exist and user doesn't have permission to create datasets"
        )

    # TODO (betodealmeida): move this logic to import_from_dict
    config = config.copy()
    for key in JSON_KEYS:
        if config.get(key) is not None:
            try:
                config[key] = json.dumps(config[key])
            except TypeError:
                logger.info("Unable to encode `%s` field: %s", key, config[key])
    for key in ("metrics", "columns"):
        for attributes in config.get(key, []):
            if attributes.get("extra") is not None:
                try:
                    attributes["extra"] = json.dumps(attributes["extra"])
                except TypeError:
                    logger.info(
                        "Unable to encode `extra` field: %s", attributes["extra"]
                    )
                    attributes["extra"] = None

    # should we delete columns and metrics not present in the current import?
    sync = ["columns", "metrics"] if overwrite else []

    # should we also load data into the dataset?
    data_uri = config.get("data")

    # import recursively to include columns and metrics
    try:
        dataset = SqlaTable.import_from_dict(config, recursive=True, sync=sync)
    except MultipleResultsFound:
        # Finding multiple results when importing a dataset only happens because initially  # noqa: E501
        # datasets were imported without schemas (eg, `examples.NULL.users`), and later
        # they were fixed to have the default schema (eg, `examples.public.users`). If a
        # user created `examples.public.users` during that time the second import will
        # fail because the UUID match will try to update `examples.NULL.users` to
        # `examples.public.users`, resulting in a conflict.
        #
        # When that happens, we return the original dataset, unmodified.
        dataset = db.session.query(SqlaTable).filter_by(uuid=config["uuid"]).one()

    if dataset.id is None:
        db.session.flush()

    try:
        table_exists = dataset.database.has_table(
            Table(dataset.table_name, dataset.schema, dataset.catalog),
        )
    except Exception:  # pylint: disable=broad-except
        # MySQL doesn't play nice with GSheets table names
        logger.warning(
            "Couldn't check if table %s exists, assuming it does", dataset.table_name
        )
        table_exists = True

    if data_uri and (not table_exists or force_data):
        load_data(data_uri, dataset, dataset.database)

    if (user := get_user()) and user not in dataset.owners:
        dataset.owners.append(user)

    return dataset


def load_data(data_uri: str, dataset: SqlaTable, database: Database) -> None:
    """
    Load data from a data URI into a dataset.

    :raises DatasetUnAllowedDataURI: If a dataset is trying
    to load data from a URI that is not allowed.
    """
    from superset.examples.helpers import normalize_example_data_url

    # Convert example URLs to align with configuration
    data_uri = normalize_example_data_url(data_uri)

    validate_data_uri(data_uri)
    logger.info("Downloading data from %s", data_uri)
    data = request.urlopen(data_uri)  # pylint: disable=consider-using-with  # noqa: S310
    if data_uri.endswith(".gz"):
        data = gzip.open(data)
    df = pd.read_csv(data, encoding="utf-8")
    dtype = get_dtype(df, dataset)

    # convert temporal columns
    for column_name, sqla_type in dtype.items():
        if isinstance(sqla_type, (Date, DateTime)):
            df[column_name] = pd.to_datetime(df[column_name])

    # reuse session when loading data if possible, to make import atomic
    if database.sqlalchemy_uri == app.config.get("SQLALCHEMY_DATABASE_URI"):
        logger.info("Loading data inside the import transaction")
        connection = db.session.connection()
        df.to_sql(
            dataset.table_name,
            con=connection,
            schema=dataset.schema,
            if_exists="replace",
            chunksize=CHUNKSIZE,
            dtype=dtype,
            index=False,
            method="multi",
        )
    else:
        logger.warning("Loading data outside the import transaction")
        with database.get_sqla_engine(
            catalog=dataset.catalog,
            schema=dataset.schema,
        ) as engine:
            df.to_sql(
                dataset.table_name,
                con=engine,
                schema=dataset.schema,
                if_exists="replace",
                chunksize=CHUNKSIZE,
                dtype=dtype,
                index=False,
                method="multi",
            )

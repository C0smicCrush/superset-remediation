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
"""Utilities for validating URLs against SSRF attacks."""

from __future__ import annotations

import ipaddress
import socket
from typing import Any
from urllib.parse import urlparse

import requests
from requests import Response


def is_private_ip(hostname: str) -> bool:
    """Check whether a hostname resolves to a private/reserved IP address.

    Resolves the hostname via DNS and checks all resulting addresses against
    private, loopback, link-local, and reserved IP ranges.

    :param hostname: The hostname or IP literal to check.
    :returns: True if any resolved address is private/reserved.
    """
    try:
        addr = ipaddress.ip_address(hostname)
        return addr.is_private or addr.is_loopback or addr.is_link_local
    except ValueError:
        pass

    try:
        addrinfos = socket.getaddrinfo(hostname, None)
    except OSError:
        return False

    for _family, _type, _proto, _canonname, sockaddr in addrinfos:
        ip_str = sockaddr[0]
        try:
            addr = ipaddress.ip_address(ip_str)
            if addr.is_private or addr.is_loopback or addr.is_link_local:
                return True
        except ValueError:
            continue
    return False


def validate_webhook_url(
    url: str,
    *,
    https_only: bool = True,
    allowed_domains: list[str] | None = None,
) -> str | None:
    """Validate a webhook URL for SSRF safety.

    Returns ``None`` when the URL is safe, or a human-readable error string
    when the URL should be rejected.

    :param url: The URL to validate.
    :param https_only: Whether to require the ``https`` scheme.
    :param allowed_domains: If provided, only these domains (exact match) are
        permitted.  An empty list means *no* domain is allowed.
    :returns: ``None`` if valid, otherwise an error message.
    """
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()

    if scheme not in ("http", "https"):
        return "Webhook URL must use http or https scheme."

    if https_only and scheme != "https":
        return "Webhook URL must use the https scheme."

    hostname = parsed.hostname
    if not hostname:
        return "Webhook URL must include a hostname."

    if is_private_ip(hostname):
        return (
            "Webhook URL must not point to a private, loopback, or link-local address."
        )

    if allowed_domains is not None:
        if hostname not in allowed_domains:
            return (
                f"Webhook URL hostname '{hostname}' is not in the allowed domains list."
            )

    return None


def _check_redirect_target(response: Response, **kwargs: object) -> None:
    """``requests`` event hook that validates every redirect target.

    Attached to a :class:`requests.Session` via ``session.hooks["response"]``
    to enforce SSRF protections on intermediate redirect URLs.
    """
    if not response.is_redirect:
        return

    location = response.headers.get("Location", "")
    parsed = urlparse(location)
    hostname = parsed.hostname

    if hostname and is_private_ip(hostname):
        response.close()
        raise requests.ConnectionError(
            f"Redirect to private/reserved address blocked: {location}"
        )


def ssrf_safe_post(
    url: str,
    **kwargs: Any,
) -> Response:
    """Send a POST request with SSRF protections.

    Uses a ``requests.Session`` with a response hook that validates every
    redirect target against private/reserved IP ranges.

    :param url: Target URL (already validated via :func:`validate_webhook_url`).
    :param kwargs: Additional keyword arguments forwarded to
        :meth:`requests.Session.post`.
    :returns: The final :class:`Response` object.
    :raises requests.ConnectionError: If a redirect targets a private IP.
    """
    session = requests.Session()
    session.max_redirects = 10
    session.hooks["response"].append(_check_redirect_target)

    return session.post(url, **kwargs)

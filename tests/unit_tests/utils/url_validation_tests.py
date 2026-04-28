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
"""Tests for superset.utils.url_validation SSRF protections."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from superset.utils.url_validation import (
    _check_redirect_target,
    is_private_ip,
    validate_webhook_url,
)


class TestIsPrivateIp:
    def test_loopback_ipv4(self) -> None:
        assert is_private_ip("127.0.0.1") is True

    def test_loopback_ipv6(self) -> None:
        assert is_private_ip("::1") is True

    def test_link_local(self) -> None:
        assert is_private_ip("169.254.169.254") is True

    def test_rfc1918_10(self) -> None:
        assert is_private_ip("10.0.0.1") is True

    def test_rfc1918_172(self) -> None:
        assert is_private_ip("172.16.0.1") is True

    def test_rfc1918_192(self) -> None:
        assert is_private_ip("192.168.1.1") is True

    def test_public_ip(self) -> None:
        assert is_private_ip("8.8.8.8") is False

    def test_hostname_resolves_to_private(self) -> None:
        with patch("superset.utils.url_validation.socket.getaddrinfo") as mock_gai:
            mock_gai.return_value = [
                (2, 1, 6, "", ("127.0.0.1", 0)),
            ]
            assert is_private_ip("evil.internal") is True

    def test_hostname_resolves_to_public(self) -> None:
        with patch("superset.utils.url_validation.socket.getaddrinfo") as mock_gai:
            mock_gai.return_value = [
                (2, 1, 6, "", ("93.184.216.34", 0)),
            ]
            assert is_private_ip("example.com") is False

    def test_unresolvable_hostname(self) -> None:
        with patch("superset.utils.url_validation.socket.getaddrinfo") as mock_gai:
            mock_gai.side_effect = OSError("DNS failure")
            assert is_private_ip("nonexistent.invalid") is False


class TestValidateWebhookUrl:
    def test_valid_https_public_url(self) -> None:
        with patch("superset.utils.url_validation.is_private_ip", return_value=False):
            assert validate_webhook_url("https://hooks.example.com/wh") is None

    def test_rejects_http_when_https_only(self) -> None:
        result = validate_webhook_url("http://hooks.example.com/wh", https_only=True)
        assert result is not None
        assert "https" in result.lower()

    def test_allows_http_when_https_not_required(self) -> None:
        with patch("superset.utils.url_validation.is_private_ip", return_value=False):
            assert (
                validate_webhook_url("http://hooks.example.com/wh", https_only=False)
                is None
            )

    def test_rejects_ftp_scheme(self) -> None:
        result = validate_webhook_url("ftp://evil.com/file")
        assert result is not None
        assert "http" in result.lower()

    def test_rejects_private_ip(self) -> None:
        result = validate_webhook_url(
            "https://169.254.169.254/latest/meta-data/", https_only=True
        )
        assert result is not None
        assert "private" in result.lower()

    def test_rejects_loopback(self) -> None:
        result = validate_webhook_url("https://127.0.0.1/admin")
        assert result is not None
        assert "private" in result.lower()

    def test_rejects_hostname_resolving_to_private(self) -> None:
        with patch("superset.utils.url_validation.is_private_ip", return_value=True):
            result = validate_webhook_url("https://internal.corp/hook")
            assert result is not None
            assert "private" in result.lower()

    def test_rejects_url_without_hostname(self) -> None:
        result = validate_webhook_url("https:///path")
        assert result is not None
        assert "hostname" in result.lower()

    def test_allowed_domains_pass(self) -> None:
        with patch("superset.utils.url_validation.is_private_ip", return_value=False):
            assert (
                validate_webhook_url(
                    "https://hooks.slack.com/services/T/B/x",
                    allowed_domains=["hooks.slack.com"],
                )
                is None
            )

    def test_allowed_domains_reject(self) -> None:
        with patch("superset.utils.url_validation.is_private_ip", return_value=False):
            result = validate_webhook_url(
                "https://evil.com/hook",
                allowed_domains=["hooks.slack.com"],
            )
            assert result is not None
            assert "allowed domains" in result.lower()

    def test_empty_allowed_domains_rejects_all(self) -> None:
        with patch("superset.utils.url_validation.is_private_ip", return_value=False):
            result = validate_webhook_url(
                "https://hooks.example.com/wh",
                allowed_domains=[],
            )
            assert result is not None
            assert "allowed domains" in result.lower()

    def test_allowed_domains_none_permits_any(self) -> None:
        with patch("superset.utils.url_validation.is_private_ip", return_value=False):
            assert (
                validate_webhook_url(
                    "https://any.domain.com/hook",
                    allowed_domains=None,
                )
                is None
            )


class TestCheckRedirectTarget:
    def test_blocks_redirect_to_private_ip(self) -> None:
        response = MagicMock()
        response.is_redirect = True
        response.headers = {"Location": "http://169.254.169.254/latest/meta-data/"}
        with pytest.raises(requests.ConnectionError, match="private"):
            _check_redirect_target(response)

    def test_blocks_redirect_to_loopback(self) -> None:
        response = MagicMock()
        response.is_redirect = True
        response.headers = {"Location": "http://127.0.0.1/admin"}
        with pytest.raises(requests.ConnectionError, match="private"):
            _check_redirect_target(response)

    def test_allows_redirect_to_public_ip(self) -> None:
        with patch("superset.utils.url_validation.is_private_ip", return_value=False):
            response = MagicMock()
            response.is_redirect = True
            response.headers = {"Location": "https://hooks.example.com/wh2"}
            _check_redirect_target(response)

    def test_ignores_non_redirect(self) -> None:
        response = MagicMock()
        response.is_redirect = False
        _check_redirect_target(response)

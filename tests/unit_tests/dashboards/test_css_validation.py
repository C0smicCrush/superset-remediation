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

import pytest
from marshmallow.validate import ValidationError

from superset.dashboards.schemas import validate_css


def test_validate_css_accepts_legitimate_css() -> None:
    validate_css("body { background: red; }")


def test_validate_css_accepts_empty_string() -> None:
    validate_css("")


def test_validate_css_rejects_style_closing_tag() -> None:
    with pytest.raises(ValidationError, match="style closing tags"):
        validate_css("</style><img src=x onerror=alert(1)>")


def test_validate_css_rejects_style_closing_tag_case_insensitive() -> None:
    with pytest.raises(ValidationError, match="style closing tags"):
        validate_css("</STYLE><img src=x onerror=alert(1)>")


def test_validate_css_rejects_style_closing_tag_with_spaces() -> None:
    with pytest.raises(ValidationError, match="style closing tags"):
        validate_css("<  / style><img src=x onerror=alert(1)>")


def test_validate_css_rejects_script_tag() -> None:
    with pytest.raises(ValidationError, match="script tags"):
        validate_css("<script>alert(1)</script>")


def test_validate_css_rejects_script_tag_case_insensitive() -> None:
    with pytest.raises(ValidationError, match="script tags"):
        validate_css("<SCRIPT>alert(1)</SCRIPT>")


def test_validate_css_accepts_css_with_angle_brackets_in_comments() -> None:
    validate_css("/* a > b */ body { color: red; }")


def test_validate_css_accepts_complex_selectors() -> None:
    validate_css(".dashboard > .row { margin: 0; }")

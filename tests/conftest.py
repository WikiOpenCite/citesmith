# SPDX-FileCopyrightText: 2026 Zoe Nickson <zoe.nickson@sidingsmedia.com>
# SPDX-License-Identifier: MIT

"""Useful pytest fixtures"""

import os.path

import pytest


@pytest.fixture
def valid_config_file(tmp_path: str) -> str:
    """A standard config file pointing to an empty database"""

    target_output = os.path.join(tmp_path, "config.toml")
    with open(target_output, "w+", encoding="utf-8") as f:
        text = f"""
[database]
type = "sqlite"
"""
        f.write(text)

    return target_output

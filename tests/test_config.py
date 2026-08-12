# SPDX-FileCopyrightText: 2026 Zoe Nickson <zoe.nickson@sidingsmedia.com>
# SPDX-License-Identifier: MIT

from pathlib import Path
from tomllib import TOMLDecodeError
import os.path


import pytest
from pytest_mock import MockerFixture
from pydantic import ValidationError

from citesmith.config import (
    ConfigManager,
    ConfigNotFoundError,
    ConfigParseError,
    ConfigReadError,
)


@pytest.fixture
def config_manager(tmp_path: Path) -> ConfigManager:
    """Pytest fixture for a new config manager"""
    conf = ConfigManager()
    conf.lookup_paths = [str(tmp_path / Path("random-dir")), str(tmp_path)]
    return conf


def test_load_file(
    valid_config_file: str,
    config_manager: ConfigManager,
    mocker: MockerFixture,
) -> None:
    """Successful loading of a config file"""

    mock_open = mocker.patch("builtins.open", wraps=open)

    assert config_manager.path == valid_config_file

    config = config_manager.config
    mock_open.assert_called_once()

    assert config is not None
    assert config.database.type == "sqlite"

    config = config_manager.config
    mock_open.assert_called_once()


def test_reload(
    valid_config_file: str,
    config_manager: ConfigManager,
    mocker: MockerFixture,
) -> None:
    """Reloading should re-read the file from disk"""

    mock_open = mocker.patch("builtins.open", wraps=open)

    config_manager.reload()
    assert mock_open.call_count == 1
    config_manager.reload()
    assert mock_open.call_count == 2


def test_file_not_found(config_manager: ConfigManager) -> None:
    """Test loading a non-existent file"""

    config_manager.lookup_paths = []

    with pytest.raises(ConfigNotFoundError):
        config_manager.reload()


def test_toml_decode_error(
    config_manager: ConfigManager, mocker: MockerFixture, valid_config_file: str
) -> None:
    """Invalid TOML files should generate an error"""
    mocker.patch(
        "tomllib.load", side_effect=TOMLDecodeError("mock error", "mock doc", 0)
    )

    with pytest.raises(ConfigParseError):
        config_manager.reload()


def test_validation_error(
    config_manager: ConfigManager, mocker: MockerFixture, valid_config_file: str
) -> None:
    """Missing required arguments"""

    mocker.patch(
        "citesmith.config.Config.model_validate",
        side_effect=ValidationError("mock error", []),
    )

    with pytest.raises(ValidationError):
        config_manager.reload()


def test_read_on_oserror(
    config_manager: ConfigManager, tmp_path: Path, mocker: MockerFixture
) -> None:
    """Handling of OSErrors on open config file"""

    file = tmp_path / Path("config.toml")
    file.touch()
    config_manager.lookup_paths = [str(tmp_path)]

    mocker.patch("builtins.open", side_effect=OSError)

    with pytest.raises(ConfigReadError):
        config_manager.reload()


def test_path_is_cached(
    config_manager: ConfigManager, valid_config_file: str, mocker: MockerFixture
) -> None:
    """The path of the config file should be cached"""
    mock_exists = mocker.patch("os.path.exists", wrap=os.path.exists)

    config_manager.path
    mock_exists.assert_called_once()
    config_manager.path
    mock_exists.assert_called_once()

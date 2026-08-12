# SPDX-FileCopyrightText: 2026 Zoe Nickson <zoe.nickson@sidingsmedia.com>
# SPDX-License-Identifier: MIT

"""
Global config handler

Handles loading and access to the application configuration file.
Example usage:
config = get_config()
"""

import os.path
from typing import Literal
import tomllib
import logging

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)


class SQLiteConfig(BaseModel):
    """Pydantic model for SQLite config"""

    type: Literal["sqlite"]


class Config(BaseModel):
    """Pydantic model for config file"""

    database: SQLiteConfig = Field(..., discriminator="type")


class ConfigError(Exception):
    """Base error for config parsing"""


class ConfigNotFoundError(ConfigError):
    """The configuration file could not be found"""


class ConfigParseError(ConfigError):
    """The configuration could not be parsed correctly"""


class ConfigReadError(ConfigError):
    """Failed to read configuration from disk"""


class ConfigManager:
    """
    Manage access to application configuration

    Attributes:
        lookup_paths: List of paths to search for the configuration file
        in. Will be searched in order.
    """

    def __init__(self) -> None:
        self.lookup_paths = ["./", "/etc/finance-manager/"]
        self._config: Config | None = None
        self._path: str | None = None

    @staticmethod
    def _load_toml_config(path: str) -> Config:
        """
        Load configuration from a toml file

        Loads and validates the application configuration from a toml file.

        Args:
            path: Path to configuration file

        Returns:
            Validated configuration
        """

        try:
            with open(path, "rb") as f:
                try:
                    data = tomllib.load(f)
                except tomllib.TOMLDecodeError as e:
                    logger.error("Failed to parse config file: %s", e)
                    raise ConfigParseError(e) from e
        except OSError as e:
            logger.error("Failed to open config file: %s", e)
            raise ConfigReadError(e) from e

        try:
            return Config.model_validate(data)
        except ValidationError as e:
            logger.error("Invalid config found: %s", e)
            raise e

    @property
    def path(self) -> str:
        """
        Path to the configuration file

        If not already found, will search the search paths to find the
        TOML file. If no config file can be found, an exception will be raised.

        Raises:
            ConfigNotFoundError: No config file could be found along the
            search path.

        Returns:
            Path to config file
        """

        if self._path is not None:
            return self._path

        for path in self.lookup_paths:
            path = os.path.join(path, "config.toml")
            if os.path.exists(path):
                self._path = path
                return path

        raise ConfigNotFoundError("Could not find configuration file on search paths")

    @property
    def config(self) -> Config:
        """
        Retrieve the config.

        Will return the current application configuration. If it has not yet
        been loaded, it will first be loaded from disk.

        Raises:
            ConfigNotFoundError: The configuration file could not be found
            anywhere.

        Returns:
            Current application configuration
        """

        if self._config:
            return self._config

        self._config = ConfigManager._load_toml_config(self.path)

        return self._config

    def reload(self) -> None:
        """Force reloading the config file."""

        self._config = ConfigManager._load_toml_config(self.path)


manager = ConfigManager()

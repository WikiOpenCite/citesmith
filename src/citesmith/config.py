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

from pydantic import BaseModel, DirectoryPath, Field, ValidationError

logger = logging.getLogger(__name__)


class MariaDBConfig(BaseModel):
    """Pydantic model for MariaDB config"""

    type: Literal["mariadb"]
    host: str
    port: int
    user: str
    password: str
    database: str
    min_pool_size: int = 5
    max_pool_size: int = 20
    max_idle_time: float = 600.0  # in seconds
    max_lifetime: float = 3600.0  # in seconds
    ping_threshold: float = 0.25  # in seconds
    enable_health_check: bool = True


class DumpsConfig(BaseModel):
    """Pydantic model for Dumps config"""

    root_dir: DirectoryPath


class WorkerConfig(BaseModel):
    """Pydantic model for worker config"""

    sleep_time: int = 60  # in seconds
    out_base_dir: DirectoryPath
    citescoop_path: str


class WebConfig(BaseModel):
    """Pydantic model for web config"""

    dump_path: DirectoryPath
    static_base_url: str


class Config(BaseModel):
    """Pydantic model for config file"""

    database: MariaDBConfig = Field(..., discriminator="type")
    dumps: DumpsConfig
    worker: WorkerConfig
    web: WebConfig


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
        self.lookup_paths = ["./", "/etc/citesmith/"]
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
            logger.debug("Searching for config file in %s", path)
            path = os.path.join(path, "config.toml")
            if os.path.exists(path):
                self._path = path
                logger.debug("Found config file at %s", path)
                return path

        raise ConfigNotFoundError("Could not find configuration file on search paths")

    @path.setter
    def path(self, value: str) -> None:
        """
        Set the path to the configuration file

        Args:
            value: Path to configuration file
        """

        self._path = value

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

from typing import Optional
import logging

import mariadb  # type: ignore
import mariadb_pool.pool  # type: ignore

from citesmith.db._database import MariaDBDatabase
from citesmith.db.errors import DBConnectionError, DBStateError

_logger = logging.getLogger(__name__)

__pool: Optional[mariadb_pool.pool.ConnectionPool] = None


def get_pool() -> mariadb_pool.pool.ConnectionPool:

    if __pool is None:
        raise DBStateError("Database pool has not been initialized.")

    return __pool


def create_pool(db: MariaDBDatabase) -> None:
    global __pool  # pylint: disable=global-statement

    if __pool is not None:
        raise DBStateError("Database pool has already been initialized.")
    _logger.debug("Creating database connection pool for %s", db.db_type.value)
    try:
        __pool = mariadb.create_pool(
            user=db.user,
            password=db.password,
            host=db.host,
            port=db.port,
            database=db.database,
            min_size=db.min_pool_size,
            max_size=db.max_pool_size,
            max_idle_time=db.max_idle_time,
            max_lifetime=db.max_lifetime,
            ping_threshold=db.ping_threshold,
            enable_health_check=db.enable_health_check,
        )
    except mariadb.Error as e:  # type: ignore
        raise DBConnectionError(f"Failed to create MariaDB connection pool: {e}") from e

    _logger.debug("Created connection pool")

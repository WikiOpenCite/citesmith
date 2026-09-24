"""
Perform database migrations for backend database
"""

import logging
import os
from typing import cast
import re

import mariadb  # type: ignore

from citesmith.config import manager

from .pool import get_pool

logger = logging.getLogger(__name__)


# Migrations in order to be applied
_migrations = [
    "20260813_initial_database",
    "20260924_published_status",
]


def _extract_statements(sql: str) -> list[str]:
    statements: list[str] = []

    statement = ""

    for line in sql.splitlines():
        if re.match(r"--", line):  # ignore sql comment lines
            continue
        if not re.search(r";$", line):  # keep appending lines that don't end in ';'
            statement = statement + line
        else:  # when you get a line ending in ';' then exec statement and reset for next statement
            statement = statement + line
            statements.append(statement)
            statement = ""

    return statements


def apply_migrations() -> None:
    """
    apply_migrations Apply the migrations to the database

    """

    logger.info("Applying database migrations")

    applied_migrations: list[str] = []

    logger.debug("Getting database connection from pool")
    with get_pool().acquire() as conn:  # type: ignore
        with conn.cursor() as cursor:  # type: ignore
            logger.debug("Checking for existing tables in database")

            cursor.execute(  # type: ignore
                "SELECT COUNT(DISTINCT `table_name`) FROM `information_schema`.`columns` WHERE `table_schema` = ?",
                (manager.config.database.database,),
            )
            table_count = cast(int, cursor.fetchone()[0])  # type: ignore
            logger.debug("Found %d tables", table_count)

            if table_count != 0:
                logger.debug("Found existing tables, checking for applied migrations")
                cursor.execute("SELECT Name FROM Migration;")  # type: ignore
                rows = cast(
                    list[tuple[str]],
                    cursor.fetchall(),  # type: ignore
                )
                applied_migrations = [row[0] for row in rows]
                logger.debug("Already applied migrations: %s", applied_migrations)

            migration_path = os.path.join(
                os.path.abspath(os.path.dirname(__file__)), "migrations"
            )

            for migration in _migrations:
                if migration in applied_migrations:
                    logger.info("Skipping %s - Already applied", migration)
                    continue

                logger.info("Applying migration %s", migration)
                with open(
                    os.path.join(migration_path, f"{migration}.sql"), encoding="utf-8"
                ) as f:
                    sql = _extract_statements(f.read())

                    for statement in sql:
                        cursor.execute(statement)  # type: ignore
                    cursor.execute(  # type: ignore
                        "INSERT INTO Migration (Name) VALUES (?)", (migration,)
                    )

        conn.commit()  # type: ignore

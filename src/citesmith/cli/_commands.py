# SPDX-FileCopyrightText: 2026 The University of St Andrews
# SPDX-License-Identifier: GPL-3.0-or-later
"""Command-line interface entry points for the citesmith application."""

import logging
import sys

import click
from tabulate import tabulate

from citesmith.config import manager, ConfigError
from citesmith.db.migrate import apply_migrations
from citesmith.db import build_from_config
from citesmith.db.pool import create_pool, get_pool
from citesmith.publisher import run_publisher, run_publisher_singleshot
from citesmith.watcher import run_watcher_singleshot
from citesmith.processor import run_processor_singleshot, run_processor
from citesmith.combiner import run_combiner_singleshot, run_combiner


@click.version_option(prog_name="citesmith")
@click.option(
    "--log-level",
    "-l",
    default="OFF",
    type=click.Choice(
        ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "OFF"], case_sensitive=False
    ),
    help="Set the logging level.",
)
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True),
    default=None,
    help=(
        "Path to configuration file. If one is not provided, an attempt"
        " will be made to find one in the current working directory or"
        " /etc/citesmith/"
    ),
)
@click.group()
def cli(config: click.Path, log_level: str):
    """Build and serve WikiOpenCite citation data"""

    if log_level and log_level.upper() == "OFF":
        # Disable all logging when OFF is specified
        logging.disable(logging.CRITICAL)
    else:
        level = getattr(logging, log_level.upper(), logging.INFO)
        logging.basicConfig(level=level)

    # Only load configuration when help was not requested
    if not ("--help" in sys.argv[1:]):
        if config:
            manager.path = str(config)

        try:
            manager.reload()
        except ConfigError as e:
            raise click.ClickException(str(e)) from e

        create_pool(build_from_config(manager.config.database))


@cli.command()
def serve():
    """Start citesmith API"""
    click.echo("Not implemented")


@cli.command()
def migrate():
    """Migrate the application database"""
    apply_migrations()
    click.echo("Migrations complete")


@cli.command()
def watch():
    """Run the watcher

    The watcher should typically be run by a cron job or similar, and
    will check for new data to process.
    """
    run_watcher_singleshot()


@cli.command()
@click.option(
    "--worker-id",
    "-i",
    type=int,
    help="ID of worker to process files for.",
)
@click.option(
    "--singleshot",
    type=bool,
    help="ID of worker to process files for.",
)
def process(worker_id: int, singleshot: bool):
    """Process new dump files

    Process any new dump files discovered by the watcher. Will keep
    processing indefinitely unless singleshot is specified.
    """

    if singleshot:
        run_processor_singleshot(worker_id)
    else:
        run_processor(worker_id)


@cli.command()
@click.option(
    "--singleshot",
    type=bool,
    help="ID of worker to process files for.",
)
def combine(singleshot: bool):
    """Combines all files for a given dump when processing is complete

    Will run indefinitely, checking for new files to combine unless singleshot is specified.
    """

    if singleshot:
        run_combiner_singleshot()
    else:
        run_combiner()


@cli.command()
@click.option(
    "--singleshot",
    type=bool,
    help="ID of worker to process files for.",
)
def publish(singleshot: bool):
    """Publish the combined data to the configured output location"""

    if singleshot:
        run_publisher_singleshot()
    else:
        run_publisher()


@cli.group()
def workers():
    """Manage background workers for processing and combining data"""


@workers.command(name="add")
@click.option(
    "--name",
    "-n",
    type=str,
    help="Add a new worker.",
)
def workers_add(name: str):
    """Add a new worker to the system"""
    with get_pool().acquire() as conn:  # type: ignore
        with conn.cursor() as cursor:  # type: ignore
            cursor.execute(  # type: ignore
                "INSERT INTO Worker (Name) VALUES (?)",
                (name,),
            )
            conn.commit()  # type: ignore


@workers.command(name="list")
def workers_list():
    """List all workers in the system"""
    with get_pool().acquire() as conn:  # type: ignore
        with conn.cursor() as cursor:  # type: ignore
            cursor.execute("SELECT WorkerId, Name FROM Worker;")  # type: ignore
            rows: list[tuple[int, str]] = cursor.fetchall()  # type: ignore

    click.echo(tabulate(rows, headers=["Id", "Name"]))  # type: ignore


@workers.command(name="remove")
@click.option(
    "--id",
    "-i",
    type=int,
    help="Remove a worker by ID.",
)
def workers_remove(id: int):
    """Remove a worker from the system"""

    with get_pool().acquire() as conn:  # type: ignore
        with conn.cursor() as cursor:  # type: ignore
            cursor.execute("DELETE FROM Worker WHERE WorkerId = ?", (id,))  # type: ignore
            if cursor.rowcount == 0:  # type: ignore
                click.echo("Worker not found.")
            conn.commit()  # type: ignore

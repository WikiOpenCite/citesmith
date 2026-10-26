import logging
import json
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import boto3
from botocore import UNSIGNED
from botocore.config import Config

from citesmith.db.pool import get_pool

_logger = logging.getLogger(__name__)


def _get_last_processed_date() -> datetime:
    """
    Retrieve the last processed date from the database.

    Returns:
        datetime: The last processed date, or a very old date if not found.
    """
    sql = "SELECT MAX(Date) FROM OpenAlexDump"
    with get_pool().acquire() as conn:  # type: ignore
        with conn.cursor() as cursor:  # type: ignore
            cursor.execute(sql)  # type: ignore
            result = cursor.fetchone()  # type: ignore
            if result and result[0] is not None:
                return datetime.fromisoformat(str(result[0]))  # type: ignore
            return datetime.fromisoformat("1970-01-01")


def _extract_file_urls(manifest_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract file URL entries for works from the manifest JSON data.

    Args:
        manifest_data (dict[str, Any]): Parsed manifest JSON data.

    Returns:
        list[dict[str, Any]]: List of file metadata entries from the works entity.
    """
    _logger.debug("Extracting file metadata from manifest data")
    for entity in manifest_data.get("entities", []):
        if entity.get("entity") == "works":
            file_entries: list[dict[str, Any]] = []
            for file in entity.get("files", []):
                meta: dict[str, Any] = file.get("meta", {}) or {}
                file_entries.append(
                    {
                        "url": str(file.get("url")),
                        "content_length": int(meta.get("content_length", 0) or 0),
                        "record_count": int(meta.get("record_count", 0) or 0),
                    }
                )
            _logger.info(
                "Found %d file metadata entries in manifest works entity",
                len(file_entries),
            )
            return file_entries

    _logger.warning("No works entity found in manifest data")
    return []


def _get_files_from_manifest() -> tuple[datetime, datetime, list[str]]:
    last_processed_date = _get_last_processed_date()
    _logger.info("Connecting to OpenAlex S3 manifest")
    s3 = boto3.client(  # type: ignore
        "s3",
        config=Config(signature_version=UNSIGNED),
    )

    manifest = s3.get_object(Bucket="openalex", Key="data/jsonl/manifest.json")  # type: ignore
    manifest_data = json.loads(manifest["Body"].read().decode("utf-8"))  # type: ignore

    manifest_date: str | None = None
    if isinstance(manifest_data, dict):
        manifest_date = manifest_data.get("date")  # type: ignore

    if not manifest_date:
        _logger.error("Manifest file does not contain a date field")
        return last_processed_date, last_processed_date, []

    manifest_datetime = datetime.fromisoformat(str(manifest_date))  # type: ignore
    _logger.info("Manifest publication date: %s", manifest_datetime)
    _logger.info("Configured watcher date: %s", last_processed_date)
    if manifest_datetime <= last_processed_date:
        _logger.info(
            "Manifest is not newer than configured date; no new files to process"
        )
        return last_processed_date, last_processed_date, []

    file_entries = _extract_file_urls(manifest_data)  # type: ignore
    return (
        manifest_datetime,
        last_processed_date,
        [entry["url"] for entry in file_entries],
    )


def _filter_new_files(file_urls: list[str], last_processed_date: datetime) -> list[str]:
    """Filter the list of file URLs to only include those that are newer than the last processed date.

    Args:
        file_urls (list[str]): List of file URLs from the manifest.
        last_processed_date (datetime): The last processed date.

    Returns:
        list[str]: List of new file URLs to process.
    """
    new_files: list[str] = []
    for url in file_urls:
        try:
            parsed = urlparse(url)
            path_parts = [part for part in parsed.path.split("/") if part]
            date_str = None

            for part in reversed(path_parts):
                if part.startswith("updated_date="):
                    date_str = part.split("=", 1)[1]
                    break

            if date_str is None:
                raise ValueError(f"No updated_date segment found in URL: {url}")

            file_date = datetime.fromisoformat(date_str)

            if file_date > last_processed_date:
                new_files.append(url)
        except Exception as e:
            _logger.error("Error parsing date from URL %s: %s", url, e)

    _logger.info("Found %d new files to process", len(new_files))
    return new_files


def _insert_new_dumps_into_db(manifest_date: datetime) -> None:
    """Insert a new dump entry into the OpenAlexDump table in the database.

    Args:
        last_processed_date (datetime): The last processed date.
    """
    sql = "INSERT INTO OpenAlexDump (Date) VALUES (?)"
    with get_pool().acquire() as conn:  # type: ignore
        with conn.cursor() as cursor:  # type: ignore
            cursor.execute(sql, (manifest_date.date().isoformat(),))  # type: ignore
            _logger.info("Inserted new dump entry for date %s", manifest_date)  # type: ignore
            conn.commit()  # type: ignore


def _insert_new_files_into_db(file_urls: list[str], manifest_date: datetime) -> None:
    """Insert new file entries into the OpenAlexFile table in the database.

    Args:
        file_urls (list[str]): List of new file URLs to insert.
        manifest_date (datetime): The manifest date.
    """
    sql = "INSERT INTO OpenAlexFile (DumpDate, Path) VALUES (?, ?)"
    with get_pool().acquire() as conn:  # type: ignore
        with conn.cursor() as cursor:  # type: ignore
            data = [(manifest_date.date().isoformat(), url) for url in file_urls]
            cursor.executemany(sql, data)  # type: ignore
            _logger.info("Inserted %d new file entries into the database", cursor.rowcount)  # type: ignore
            conn.commit()  # type: ignore


def run_watcher_singleshot():
    """
    Run the OpenAlex watcher in singleshot mode.

    This function is intended to be called from a command-line interface (CLI) or a script.
    It will run the OpenAlex watcher once, checking for new data to process.
    """

    manifest_datetime, last_processed_date, file_urls = _get_files_from_manifest()
    _logger.info("Manifest datetime: %s", manifest_datetime)
    _logger.info("Last processed date: %s", last_processed_date)
    if len(file_urls) == 0:
        _logger.info("No files to process; exiting watcher")
        return

    new_files = _filter_new_files(file_urls, last_processed_date)
    if len(new_files) == 0:
        _logger.info("No new files to process after filtering; exiting watcher")
        return

    _insert_new_dumps_into_db(manifest_datetime)
    _insert_new_files_into_db(new_files, manifest_datetime)

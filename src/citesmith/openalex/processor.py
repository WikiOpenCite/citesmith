from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import gzip
import logging
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import boto3  # type: ignore[reportMissingTypeStubs]
from botocore import UNSIGNED  # type: ignore[reportMissingTypeStubs]
from botocore.config import Config  # type: ignore[reportMissingTypeStubs]

from citesmith.db.pool import get_pool
from citesmith.config import manager as config_manager

from ._utils import derive_temp_paths

_logger = logging.getLogger(__name__)


@dataclass
class _File:
    file_id: int
    path: str
    date: str


def _get_s3_bucket_and_key(file_url: str) -> tuple[str, str]:
    """Extract the S3 bucket and key from a file URL.

    Args:
        file_url (str): S3 URL to parse.

    Returns:
        tuple[str, str]: Bucket name and object key.

    Raises:
        SystemExit: If the file URL does not use the s3 scheme.
    """
    parsed_url = urlparse(file_url)
    if parsed_url.scheme != "s3":
        raise SystemExit(f"Unsupported file URL scheme: {parsed_url.scheme}")

    bucket = parsed_url.netloc
    key = parsed_url.path.lstrip("/")
    return bucket, key


def _get_next_file(exclude_ids: tuple[int, ...] = ()):
    # Base query
    sql = """ 
          SELECT FileId,
                Path,
                DumpDate
          FROM   OpenAlexFile
          WHERE  Complete = FALSE
          """

    # Dynamically inject exclusion logic if active tasks exist
    params = []
    if exclude_ids:
        # Generates a string placeholder like "?, ?, ?" for MariaDB parameter binding
        placeholders = ", ".join(["?"] * len(exclude_ids))
        sql += f" AND FileId NOT IN ({placeholders})\n"
        params.extend(exclude_ids)

    sql += " LIMIT 1;"

    with get_pool().acquire() as conn:  # type: ignore
        with conn.cursor() as cursor:  # type: ignore
            # Pass parameters to execute safely to prevent SQL injection
            # MariaDB client expects a tuple or list for positional arguments
            cursor.execute(sql, params if params else None)  # type: ignore
            file = cursor.fetchone()  # type: ignore

    if file is None:
        return None

    return _File(file_id=file[0], path=file[1], date=file[2])  # type: ignore


def _build_citescoop_command(
    citescoop_path: str,
    authors_path: Path,
    institutions_path: Path,
    works_path: Path,
) -> list[str]:
    """Build the citescoop openalex processing command arguments.

    Args:
        citescoop_path (str): Path to the citescoop binary.
        authors_path (Path): Path to the temporary authors output file.
        institutions_path (Path): Path to the temporary institutions output file.
        works_path (Path): Path to the temporary works output file.

    Returns:
        list[str]: Arguments for the citescoop openalex process command.
    """
    return [
        str(citescoop_path),
        "openalex",
        "process",
        "--stdin",
        "--authors",
        str(authors_path),
        "--institutions",
        str(institutions_path),
        "--works",
        str(works_path),
    ]


def _stream_to_process(
    gz_reader: gzip.GzipFile,
    process: subprocess.Popen[Any],
    chunk_size: int,
    rate_limit_bytes: int,
) -> None:
    """Stream decompressed gzipped content into the citescoop subprocess with rate limiting.

    Args:
        gz_reader (gzip.GzipFile): Reader for the gzipped source file.
    """

    stdin = process.stdin
    assert stdin is not None

    window_bytes = 0
    window_start = time.monotonic()

    while True:
        chunk = gz_reader.read(chunk_size)
        if not chunk:
            break

        stdin.write(chunk)
        stdin.flush()
        window_bytes += len(chunk)

        if window_bytes >= rate_limit_bytes:
            elapsed = time.monotonic() - window_start
            if elapsed < 1.0:
                time.sleep(1.0 - elapsed)
            window_start = time.monotonic()
            window_bytes = 0


def _finalize_process(
    file_url: str,
    process: subprocess.Popen[Any],
    authors_path: Path,
    institutions_path: Path,
    works_path: Path,
) -> str:
    """Finalize the citescoop process, check for errors, and log completion.

    Args:
        file_url (str): URL of the processed file.
        process (subprocess.Popen[Any]): Completed subprocess.
        authors_path (Path): Path to the temporary authors output file.
        institutions_path (Path): Path to the temporary institutions output file.
        works_path (Path): Path to the temporary works output file.

    Returns:
        str: The processed file URL.

    Raises:
        SystemExit: If the citescoop process exits with a non-zero status.
    """

    stdin = process.stdin
    assert stdin is not None
    stdin.close()

    stderr = process.stderr
    assert stderr is not None

    err = stderr.read().decode("utf-8", errors="replace")
    return_code = process.wait()
    if return_code != 0:
        raise SystemExit(
            f"citescoop failed for {file_url} with exit code {return_code}: {err}"
        )

    _logger.info(
        "Completed stream for %s -> %s, %s, %s",
        file_url,
        authors_path,
        institutions_path,
        works_path,
    )
    return file_url


def _cleanup_process(process: subprocess.Popen[Any]) -> None:
    """Close and terminate the process if it is still running.

    Args:
        process (subprocess.Popen[Any]): Subprocess to clean up.

    Returns:
        None
    """
    if process.stdin and not process.stdin.closed:
        process.stdin.close()
    if process.poll() is None:
        process.kill()
        process.wait()


def _process_one_file(
    file_url: str,
    citescoop_path: str,
    output_dir: Path,
    s3_client: Any,
    rate_limit_bytes: int,
    chunk_size: int,
) -> str:
    """Download a single file from S3, process it through citescoop, and return metadata.

    Args:
        file_url (str): URL of the file to process.
        citescoop_path (str): Path to the citescoop binary.
        output_dir (Path): Directory where temporary files will be written.
        s3_client (Any): S3 client for downloading the file.
        rate_limit_bytes (int): Maximum bytes per second to send to the process.
        chunk_size (int): Size of chunks to read from the gzipped stream.

    Returns:
        str: The processed file URL.

    Raises:
        SystemExit: If the S3 URL is not supported or citescoop processing fails.
    """
    _logger.info(
        "Starting stream for %s",
        file_url,
    )
    authors_path, institutions_path, works_path = derive_temp_paths(
        file_url, output_dir
    )
    command = _build_citescoop_command(
        citescoop_path,
        authors_path,
        institutions_path,
        works_path,
    )

    bucket, key = _get_s3_bucket_and_key(file_url)
    response = s3_client.get_object(Bucket=bucket, Key=key)
    body = response["Body"]

    with body, gzip.GzipFile(fileobj=body, mode="rb") as gz_reader:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert process.stdin is not None
        assert process.stderr is not None

        try:
            _stream_to_process(gz_reader, process, chunk_size, rate_limit_bytes)
            _finalize_process(
                file_url,
                process,
                authors_path,
                institutions_path,
                works_path,
            )
            return file_url
        finally:
            _cleanup_process(process)


def _mark_file_complete(file: _File) -> None:
    """Mark a file as complete in the database.

    Args:
        file (_File): The file to mark as complete.

    Returns:
        None
    """
    sql = "UPDATE OpenAlexFile SET Complete = TRUE WHERE FileId = ?"
    with get_pool().acquire() as conn:  # type: ignore
        with conn.cursor() as cursor:  # type: ignore
            cursor.execute(sql, (file.file_id,))  # type: ignore
            conn.commit()  # type: ignore


def run_processor_singleshot():
    """Run the processor in singleshot mode for a specific worker.

    Args:
        worker_id (int): The ID of the worker to process files for.
    """

    s3 = boto3.client(  # type: ignore
        "s3",
        config=Config(signature_version=UNSIGNED),
    )
    rate_limit_bytes = 8 * 1024 * 1024
    chunk_size = 1024 * 1024
    active_file_ids = set()

    with ThreadPoolExecutor(
        max_workers=config_manager.config.worker.max_parallel
    ) as executor:

        def handle_done(future):
            file_entry = future.file_entry
            try:
                future.result()
                _mark_file_complete(file_entry)
            except Exception as e:
                _logger.error(
                    "Failed to process file %d (%s): %s",
                    file_entry.file_id,
                    file_entry.path,
                    e,
                )
            finally:
                active_file_ids.remove(file_entry.file_id)

        while True:
            # Throttle: Don't pull more if our queue/worker slots are completely full
            if len(active_file_ids) >= config_manager.config.worker.max_parallel:
                time.sleep(0.05)
                continue

            # FIX: Pass active IDs down to the DB query so it skips them and finds the *next* available file
            file = _get_next_file(exclude_ids=tuple(active_file_ids))

            if not file:
                # If there are no files left outside of what is currently processing,
                # we must wait for active threads to finish before breaking.
                if active_file_ids:
                    time.sleep(0.1)
                    continue
                else:
                    break

            _logger.info("Processing file %d: %s", file.file_id, file.path)
            active_file_ids.add(file.file_id)

            future = executor.submit(
                _process_one_file,
                file.path,
                config_manager.config.worker.citescoop_path,
                config_manager.config.worker.openalex_out_dir,
                s3,
                rate_limit_bytes,
                chunk_size,
            )

            future.file_entry = file
            future.add_done_callback(handle_done)

    _logger.info("Finished processing all files")


def run_processor():

    sleep_time = config_manager.config.worker.sleep_time

    while True:
        run_processor_singleshot()
        _logger.info(
            "Finished processing available files, sleeping for %d seconds", sleep_time
        )
        time.sleep(sleep_time)

# SPDX-FileCopyrightText: 2026 The University of St Andrews
# SPDX-License-Identifier: GPL-3.0-or-later

from pathlib import Path
import logging
import subprocess
from time import sleep
from shutil import copy2

from citesmith.config import manager as config_manager
from citesmith.db.pool import get_pool

from ._utils import derive_temp_paths

_logger = logging.getLogger(__name__)


def _mark_ready_dumps():
    sql = """
      UPDATE OpenAlexDump d
      INNER JOIN (
          SELECT
              DumpDate
          FROM OpenAlexFile
          GROUP BY DumpDate
          HAVING SUM(Complete IS NULL OR Complete = FALSE) = 0
      ) f
          ON d.Date = f.DumpDate
      SET d.ReadyForCombining = TRUE
      WHERE d.ReadyForCombining = FALSE;
      """

    with get_pool().acquire() as conn:  # type: ignore
        with conn.cursor() as cursor:  # type: ignore
            cursor.execute(sql)  # type: ignore
            _logger.info("Marked %d dumps as ready for combining", cursor.rowcount)  # type: ignore
            conn.commit()  # type: ignore


def _get_ready_dumps() -> list[str]:
    sql = "SELECT Date FROM OpenAlexDump WHERE ReadyForCombining = TRUE AND ProcessingComplete = FALSE"

    with get_pool().acquire() as conn:  # type: ignore
        with conn.cursor() as cursor:  # type: ignore
            cursor.execute(sql)  # type: ignore
            dumps = cursor.fetchall()  # type: ignore

    return [dump[0] for dump in dumps]  # type: ignore


def _get_dump_files(date: str) -> tuple[list[Path], list[Path], list[Path]]:
    sql = "SELECT Path FROM OpenAlexFile WHERE DumpDate = ?"

    with get_pool().acquire() as conn:  # type: ignore
        with conn.cursor() as cursor:  # type: ignore
            cursor.execute(sql, (date,))  # type: ignore
            files = cursor.fetchall()  # type: ignore

    root_path = config_manager.config.worker.openalex_out_dir

    return [
        [derive_temp_paths(file[0], root_path)[2] for file in files],  # type: ignore
        [derive_temp_paths(file[0], root_path)[0] for file in files],  # type: ignore
        [derive_temp_paths(file[0], root_path)[1] for file in files],  # type: ignore
    ]


def _combine_pbf(inputs: list[Path], output: Path) -> bool:
    citescoop_path = config_manager.config.worker.citescoop_path

    _logger.debug("Combining dumps into %s", output)
    cmd = [
        citescoop_path,
        "pbf",
        "combine",
        "--output",
        str(output.absolute()),
    ]

    for input_file in inputs:
        cmd.extend(["--input", str(input_file.absolute())])

    _logger.debug("Running command %s", " ".join(map(str, cmd)))  # type: ignore

    result = subprocess.run(
        cmd,  # type: ignore
        check=False,
    )

    if result.returncode != 0:
        _logger.error("Command exited with non-zero exit code: %d", result.returncode)
        _logger.debug(result.stderr)
        return False
    return True


def _remove_if_exists(files: list[Path]) -> None:
    for file in files:
        if file.exists():
            _logger.debug("Removing file %s", file)
            file.unlink()


def _mark_dump_combined(date: str) -> None:
    sql = "UPDATE OpenAlexDump SET ProcessingComplete = TRUE WHERE  Date = ?"

    with get_pool().acquire() as conn:  # type: ignore
        with conn.cursor() as cursor:  # type: ignore
            cursor.execute(sql, (date,))  # type: ignore
            _logger.info("Marked dump %s as combined", date)  # type: ignore
            conn.commit()  # type: ignore


def _get_previous_combined_files(
    date: str,
) -> tuple[Path | None, Path | None, Path | None]:
    sql = "SELECT Date FROM OpenAlexDump WHERE Date < ? AND ProcessingComplete = TRUE ORDER BY Date DESC LIMIT 1"

    with get_pool().acquire() as conn:  # type: ignore
        with conn.cursor() as cursor:  # type: ignore
            cursor.execute(sql, (date,))  # type: ignore
            previous_files = cursor.fetchone()  # type: ignore

    if not previous_files or previous_files[0] is None:
        return (None, None, None)

    root_path = config_manager.config.worker.openalex_out_dir

    return (
        (Path(root_path / Path(f"{previous_files[0]}.works.pbf"))),
        (Path(root_path / Path(f"{previous_files[0]}.authors.pbf"))),
        (Path(root_path / Path(f"{previous_files[0]}.institutions.pbf"))),
    )


def _combine_dump(date: str):
    works_files, author_files, institution_files = _get_dump_files(date)

    root_path = config_manager.config.worker.openalex_out_dir
    output_works = root_path / Path(f"{date}.works.pbf")
    output_authors = root_path / Path(f"{date}.authors.pbf")
    output_institutions = root_path / Path(f"{date}.institutions.pbf")

    previous_work_file, previous_author_file, previous_institution_file = (
        _get_previous_combined_files(date)
    )

    if previous_work_file is not None:
        works_files.insert(0, previous_work_file)
    if previous_author_file is not None:
        author_files.insert(0, previous_author_file)
    if previous_institution_file is not None:
        institution_files.insert(0, previous_institution_file)

    if _combine_pbf(works_files, output_works):
        _logger.info("Successfully combined works for %s", date)
        _remove_if_exists(works_files)
    else:
        _logger.error("Failed to combine works for %s", date)
        _remove_if_exists([output_works])
        return

    if _combine_pbf(author_files, output_authors):
        _logger.info("Successfully combined authors for %s", date)
        _remove_if_exists(author_files)
    else:
        _logger.error("Failed to combine authors for %s", date)
        _remove_if_exists([output_authors])
        return

    if _combine_pbf(institution_files, output_institutions):
        _logger.info("Successfully combined institutions for %s", date)
        _remove_if_exists(institution_files)
    else:
        _logger.error("Failed to combine institutions for %s", date)
        _remove_if_exists([output_institutions])
        return

    copy2(
        output_works,
        config_manager.config.web.openalex_path / Path(f"{date}.works.pbf"),
    )
    copy2(
        output_authors,
        config_manager.config.web.openalex_path / Path(f"{date}.authors.pbf"),
    )
    copy2(
        output_institutions,
        config_manager.config.web.openalex_path / Path(f"{date}.institutions.pbf"),
    )

    _mark_dump_combined(date)


def run_combiner_singleshot():
    _mark_ready_dumps()

    dumps = _get_ready_dumps()
    for dump in dumps:
        _combine_dump(dump)


def run_combiner():

    sleep_time = config_manager.config.worker.sleep_time

    while True:
        run_combiner_singleshot()
        _logger.info(
            "Finished combining processed dumps, sleeping for %d seconds", sleep_time
        )
        sleep(sleep_time)

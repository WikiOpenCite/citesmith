from pathlib import Path
import logging
import subprocess
from time import sleep

from citesmith.config import manager as config_manager
from citesmith.db.pool import get_pool

_logger = logging.getLogger(__name__)


def _mark_ready_dumps():
    sql = """
      UPDATE Dump d
      INNER JOIN (
          SELECT
              DumpWiki,
              DumpDate
          FROM File
          GROUP BY DumpWiki, DumpDate
          HAVING SUM(Complete IS NULL OR Complete = FALSE) = 0
      ) f
          ON d.Wiki = f.DumpWiki
          AND d.Date = f.DumpDate
      SET d.ReadyForCombining = TRUE
      WHERE d.ReadyForCombining = FALSE;
      """

    with get_pool().acquire() as conn:  # type: ignore
        with conn.cursor() as cursor:  # type: ignore
            cursor.execute(sql)  # type: ignore
            _logger.info("Marked %d dumps as ready for combining", cursor.rowcount)  # type: ignore
            conn.commit()  # type: ignore


def _get_ready_dumps() -> list[tuple[str, str]]:
    sql = "SELECT Wiki, Date FROM Dump WHERE ReadyForCombining = TRUE AND ProcessingComplete = FALSE"

    with get_pool().acquire() as conn:  # type: ignore
        with conn.cursor() as cursor:  # type: ignore
            cursor.execute(sql)  # type: ignore
            dumps = cursor.fetchall()  # type: ignore

    return [(dump[0], dump[1]) for dump in dumps]  # type: ignore


def _get_dump_files(wiki: str, date: str) -> tuple[list[Path], list[Path]]:
    sql = "SELECT Path FROM File WHERE DumpWiki = ? AND DumpDate = ?"

    with get_pool().acquire() as conn:  # type: ignore
        with conn.cursor() as cursor:  # type: ignore
            cursor.execute(sql, (wiki, date))  # type: ignore
            files = cursor.fetchall()  # type: ignore

    root_path = config_manager.config.worker.out_base_dir / Path(wiki) / Path(date)

    return [
        [Path(root_path / (Path(file[0]).name + ".pages")) for file in files],  # type: ignore
        [Path(root_path / (Path(file[0]).name + ".revisions")) for file in files],  # type: ignore
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


def _mark_dump_combined(wiki: str, date: str) -> None:
    sql = "UPDATE Dump SET ProcessingComplete = TRUE WHERE Wiki = ? AND Date = ?"

    with get_pool().acquire() as conn:  # type: ignore
        with conn.cursor() as cursor:  # type: ignore
            cursor.execute(sql, (wiki, date))  # type: ignore
            _logger.info("Marked dump %s %s as combined", wiki, date)  # type: ignore
            conn.commit()  # type: ignore


def _combine_dump(wiki: str, date: str):
    page_files, revision_files = _get_dump_files(wiki, date)

    root_path = config_manager.config.worker.out_base_dir / Path(wiki)
    output_pages = root_path / Path(f"{wiki}-{date}.pages.pbf")
    output_revisions = root_path / Path(f"{wiki}-{date}.revisions.pbf")

    if _combine_pbf(page_files, output_pages):
        _logger.info("Successfully combined pages for %s %s", wiki, date)
        _remove_if_exists(page_files)
    else:
        _logger.error("Failed to combine pages for %s %s", wiki, date)
        _remove_if_exists([output_pages])
        return

    if _combine_pbf(revision_files, output_revisions):
        _logger.info("Successfully combined revisions for %s %s", wiki, date)
        _remove_if_exists(revision_files)
    else:
        _logger.error("Failed to combine revisions for %s %s", wiki, date)
        _remove_if_exists([output_revisions])
        return

    _mark_dump_combined(wiki, date)


def run_combiner_singleshot():
    _mark_ready_dumps()

    dumps = _get_ready_dumps()
    for dump in dumps:
        _combine_dump(dump[0], dump[1])


def run_combiner():

    sleep_time = config_manager.config.worker.sleep_time

    while True:
        run_combiner_singleshot()
        _logger.info(
            "Finished combining processed dumps, sleeping for %d seconds", sleep_time
        )
        sleep(sleep_time)

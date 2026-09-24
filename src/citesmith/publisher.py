from time import sleep
import logging
from pathlib import Path
from shutil import move

from citesmith.config import manager as config_manager
from citesmith.db.pool import get_pool

_logger = logging.getLogger(__name__)


def _get_completed_dumps() -> list[tuple[str, str]]:
    sql = "SELECT Wiki, Date FROM Dump WHERE Published = FALSE AND ProcessingComplete = TRUE"

    with get_pool().acquire() as conn:  # type: ignore
        with conn.cursor() as cursor:  # type: ignore
            cursor.execute(sql)  # type: ignore
            dumps = cursor.fetchall()  # type: ignore

    return [(dump[0], dump[1]) for dump in dumps]  # type: ignore


def _publish_dump(wiki: str, date: str) -> None:
    source_dir = Path(config_manager.config.worker.out_base_dir) / wiki
    output_dir = Path(config_manager.config.web.dump_path) / wiki / date
    output_dir.mkdir(parents=True, exist_ok=True)

    expected_files = {
        f"{wiki}-{date}.pages.pbf",
        f"{wiki}-{date}.revisions.pbf",
    }

    if source_dir.exists():
        for src_path in sorted(source_dir.iterdir(), key=lambda p: p.name):
            if src_path.name not in expected_files:
                continue

            _logger.debug("Publishing dump file %s/%s -> %s", wiki, date, src_path.name)
            dst_path = output_dir / src_path.name
            if dst_path.exists():
                if dst_path.is_dir() and src_path.is_dir():
                    _logger.debug(
                        "Skipping already-published directory %s/%s/%s",
                        wiki,
                        date,
                        src_path.name,
                    )
                    continue
                _logger.debug(
                    "Replacing existing destination for %s/%s/%s",
                    wiki,
                    date,
                    src_path.name,
                )
                dst_path.unlink()
            move(str(src_path), str(dst_path))
            _logger.debug(
                "Moved dump file %s/%s -> %s",
                wiki,
                date,
                src_path.name,
            )

    sql = "UPDATE Dump SET Published = TRUE WHERE Wiki = ? AND Date = ?"

    with get_pool().acquire() as conn:  # type: ignore
        with conn.cursor() as cursor:  # type: ignore
            cursor.execute(sql, (wiki, date))  # type: ignore
            _logger.info("Published dump %s/%s", wiki, date)  # type: ignore
            conn.commit()  # type: ignore


def run_publisher_singleshot():
    completed_dumps = _get_completed_dumps()

    for dump in completed_dumps:
        _publish_dump(dump[0], dump[1])


def run_publisher():

    sleep_time = config_manager.config.worker.sleep_time

    while True:
        run_publisher_singleshot()
        _logger.info(
            "Finished publishing available dumps, sleeping for %d seconds", sleep_time
        )
        sleep(sleep_time)

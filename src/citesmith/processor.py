from time import sleep
import logging
from dataclasses import dataclass
from pathlib import Path
import subprocess

from citesmith.config import manager as config_manager
from citesmith.db.pool import get_pool


@dataclass
class _File:
    file_id: int
    path: Path
    wiki: str
    date: str


_logger = logging.getLogger(__name__)


def _get_next_file(worker_id: int) -> _File | None:
    sql = """ 
          SELECT FileId,
                Path,
                DumpWiki,
                DumpDate
          FROM   File
          WHERE  Complete = FALSE
                AND Worker = ?
          LIMIT  1;
          """

    with get_pool().acquire() as conn:  # type: ignore
        with conn.cursor() as cursor:  # type: ignore
            cursor.execute(sql, (worker_id,))  # type: ignore
            file = cursor.fetchone()  # type: ignore

    if file is None:
        return None

    return _File(file_id=file[0], path=Path(file[1]), wiki=file[2], date=file[3])  # type: ignore


def _mark_file_complete(file: _File):
    sql = "UPDATE File SET Complete=TRUE WHERE FileId = ?"

    with get_pool().acquire() as conn:  # type: ignore
        with conn.cursor() as cursor:  # type: ignore
            cursor.execute(sql, (file.file_id,))  # type: ignore
        conn.commit()  # type: ignore

    _logger.debug("Marked file %d as complete", file.file_id)


def _ensure_dir(dir: Path):
    if dir.exists():
        if dir.is_dir():
            _logger.debug("Directory %s already exists. No need to create it.", dir)
        else:
            raise ValueError("root path is not a directory")
    else:
        dir.mkdir(parents=True)
        _logger.debug("Created output dir %s", dir)


def _run_subprocess(file: _File) -> bool:
    citescoop_path = config_manager.config.worker.citescoop_path
    root_path = (
        config_manager.config.worker.out_base_dir / Path(file.wiki) / Path(file.date)
    )

    _ensure_dir(root_path)

    _logger.debug("Processing file %d %s", file.file_id, file.path)
    cmd = [  # type: ignore
        citescoop_path,
        "dump",
        "extract",
        "--bz2",
        "--wiki",
        file.wiki,
        "--input",
        file.path,
        "--pages",
        str(Path(root_path / (file.path.name + ".pages")).absolute()),  # type: ignore
        "--revisions",
        str(Path(root_path / (file.path.name + ".revisions")).absolute()),  # type: ignore
    ]
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


def _process_file(file: _File):
    if _run_subprocess(file):
        _mark_file_complete(file)


def run_processor_singleshot(worker_id: int):
    while file := _get_next_file(worker_id):
        _process_file(file)


def run_processor(worker_id: int):

    sleep_time = config_manager.config.worker.sleep_time

    while True:
        run_processor_singleshot(worker_id)
        _logger.info(
            "Finished processing available files, sleeping for %d seconds", sleep_time
        )
        sleep(sleep_time)

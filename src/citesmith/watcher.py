from pathlib import Path
import logging

from citesmith.config import manager as config_manager
from citesmith.db.pool import get_pool

_logger = logging.getLogger(__name__)


def _list_directories(path: Path) -> list[str]:
    return [p.name for p in path.iterdir() if p.is_dir()]


def _store_wikis(wikis: list[str]) -> None:
    sql = "INSERT IGNORE INTO Wiki (Name) VALUES (?)"
    data = [(wiki,) for wiki in wikis]
    with get_pool().acquire() as conn:  # type: ignore
        with conn.cursor() as cursor:  # type: ignore
            cursor.executemany(sql, data)  # type: ignore
            _logger.info("Discovered %d new wikis", cursor.rowcount)  # type: ignore
            conn.commit()  # type: ignore


def _list_dumps(wikis: list[str]) -> dict[str, list[str]]:
    root = Path(config_manager.config.dumps.root_dir)

    dumps: dict[str, list[str]] = {}
    for wiki in wikis:
        wiki_path = root / Path(wiki)
        dumps[wiki] = _list_directories(wiki_path)

    return dumps


def _store_dumps(dumps: dict[str, list[str]]) -> None:
    sql = "INSERT IGNORE INTO Dump (Wiki, Date) VALUES (?, ?)"
    data = [(key, value) for key, values in dumps.items() for value in values]
    with get_pool().acquire() as conn:  # type: ignore
        with conn.cursor() as cursor:  # type: ignore
            cursor.executemany(sql, data)  # type: ignore
            _logger.info("Discovered %d new dumps", cursor.rowcount)  # type: ignore
            conn.commit()  # type: ignore


def _list_dump_files(root: Path) -> list[Path]:
    if (root / Path("_SUCCESS")).exists():
        return [
            p.absolute()
            for p in root.iterdir()
            if p.is_file() and p.name.endswith("bz2")
        ]

    _logger.info("Dump not finished processing (%s)", root)
    return []


def _list_workers() -> list[int]:
    with get_pool().acquire() as conn:  # type: ignore
        with conn.cursor() as cursor:  # type: ignore
            cursor.execute("SELECT WorkerId FROM Worker")  # type: ignore
            workers: list[int] = [row[0] for row in cursor.fetchmany()]  # type: ignore
            conn.commit()  # type: ignore

    return workers


def _store_dump_files(wiki: str, dump: str, files: list[Path]) -> None:
    available_workers = _list_workers()
    if len(available_workers) == 0:
        raise ValueError("No workers available")

    sql = (
        "INSERT IGNORE INTO File (DumpWiki, DumpDate, Path, Worker) VALUES (?, ?, ?, ?)"
    )

    # BUG(computroniks): There is an atomicity issue here if a worker is
    # deleted while watcher is running. Not really much of an issue,
    # just don't do it. We should really handle this nicer but given it
    # is unlikely to occur, we just won't support it instead.

    data = [
        (wiki, dump, file, available_workers[i % len(available_workers)])
        for i, file in enumerate(files)
    ]

    with get_pool().acquire() as conn:  # type: ignore
        with conn.cursor() as cursor:  # type: ignore
            cursor.executemany(sql, data)  # type: ignore
            _logger.info("Discovered %d new dumps", cursor.rowcount)  # type: ignore
            conn.commit()  # type: ignore


def run_watcher_singleshot():
    wikis = _list_directories(Path(config_manager.config.dumps.root_dir))
    _store_wikis(wikis)

    wiki_dumps = _list_dumps(wikis)
    _store_dumps(wiki_dumps)

    root = Path(config_manager.config.dumps.root_dir)

    for wiki, dumps in wiki_dumps.items():
        for dump in dumps:
            files = _list_dump_files(root / Path(wiki) / Path(dump) / Path("xml/bzip2"))
            if len(files) > 0:
                _store_dump_files(wiki, dump, files)

from datetime import datetime, timezone

from flask import Flask, render_template

from citesmith.db.pool import get_pool
from citesmith.config import manager as config_manager

app = Flask(__name__)


def _get_dumps():
    sql = """
    WITH DumpProgress AS (
        SELECT
            d.Wiki,
            d.Date,
            d.ReadyForCombining,
            d.ProcessingComplete,
            d.Published,
            ROUND(
                100.0 * SUM(f.Complete = TRUE) / COUNT(f.DumpWiki),
                1
            ) AS PercentComplete,
            COUNT(*) OVER (
                PARTITION BY d.Wiki
            ) AS DumpCount,
            ROW_NUMBER() OVER (
                PARTITION BY d.Wiki
                ORDER BY d.Date DESC
            ) AS rn
        FROM Dump d
        LEFT JOIN File f
            ON d.Wiki = f.DumpWiki
            AND d.Date = f.DumpDate
        GROUP BY d.Wiki, d.Date
    )
    SELECT
        Wiki,
        Date,
        ReadyForCombining,
        ProcessingComplete,
        Published,
        PercentComplete,
        DumpCount
    FROM DumpProgress
    WHERE rn <= 3
    ORDER BY Wiki, Date DESC;
    """

    with get_pool().acquire() as conn:  # type: ignore
        with conn.cursor() as cursor:  # type: ignore
            cursor.execute(sql)  # type: ignore
            dumps = cursor.fetchall()  # type: ignore

    wikis: dict[str, list[dict[str, str | None]]] = {}
    counts: dict[str, int] = {}

    for dump in dumps:
        wiki, date, ready_for_combining, processing_complete, published, percent_complete, dump_count = dump  # type: ignore

        if published:
            status = "complete"
        elif percent_complete is not None and percent_complete != 0:
            status = "processing"
        else:
            status = "pending"

        if wiki not in wikis:
            wikis[wiki] = []
            counts[wiki] = dump_count

        if status == "complete":
            download_url = (
                f"{config_manager.config.web.static_base_url}/dumps/{wiki}/{date}"
            )
        else:
            download_url = None

        wikis[wiki].append(
            {
                "name": date,
                "status": status,
                "progress": percent_complete,  # type: ignore
                "download_url": download_url,
            }
        )

    return [
        {
            "code": wiki,
            "dumps": dumps,
            "older_dumps_url": f"{config_manager.config.web.static_base_url}/dumps/{wiki}/",
            "total_dumps": counts[wiki],
        }
        for wiki, dumps in wikis.items()
    ]  # type: ignore


@app.route("/")
def index():

    dumps = _get_dumps()  # type: ignore

    return render_template(
        "progress.html",
        generated_at=datetime.now(timezone.utc).strftime(  # type: ignore
            "%Y-%m-%d %H:%M %Z"
        ),
        wikis=dumps,
    )

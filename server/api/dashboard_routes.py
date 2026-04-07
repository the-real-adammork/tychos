"""Dashboard routes: summary stats and leaderboard."""
from fastapi import APIRouter

from server.db import get_async_db

router = APIRouter(prefix="/api/dashboard")


def _row_to_dict(row) -> dict:
    return dict(row)


@router.get("")
async def dashboard():
    """Return aggregate stats, best runs, recent runs, and a leaderboard."""
    async with get_async_db() as conn:
        total_cursor = await conn.execute("SELECT COUNT(*) FROM param_sets")
        total_param_sets = (await total_cursor.fetchone())[0]

        ds_cursor = await conn.execute("SELECT id, slug, name FROM datasets ORDER BY id")
        datasets = await ds_cursor.fetchall()

        best_by_dataset = {}
        for ds in datasets:
            best_cursor = await conn.execute(
                """
                SELECT ps.name, pv.version_number,
                       AVG(er.tychos_error_arcmin) AS mean_error
                FROM runs r
                JOIN param_versions pv ON r.param_version_id = pv.id
                JOIN param_sets ps ON pv.param_set_id = ps.id
                JOIN eclipse_results er ON er.run_id = r.id
                WHERE r.dataset_id = ? AND r.status = 'done' AND r.total_eclipses > 0
                    AND er.tychos_error_arcmin IS NOT NULL
                GROUP BY r.id
                ORDER BY mean_error ASC
                LIMIT 1
                """,
                (ds["id"],),
            )
            best_row = await best_cursor.fetchone()
            best_by_dataset[ds["slug"]] = (
                {
                    "name": f"{best_row['name']} v{best_row['version_number']}",
                    "mean_error": best_row["mean_error"],
                }
                if best_row else None
            )

        recent_cursor = await conn.execute(
            """
            SELECT r.id, ps.name AS param_set_name, pv.version_number, u.name AS owner_name,
                   d.slug AS dataset_slug, d.name AS dataset_name,
                   r.status, r.total_eclipses, r.detected, r.created_at
            FROM runs r
            JOIN param_versions pv ON r.param_version_id = pv.id
            JOIN param_sets ps ON pv.param_set_id = ps.id
            JOIN users u ON ps.owner_id = u.id
            JOIN datasets d ON r.dataset_id = d.id
            ORDER BY r.created_at DESC
            LIMIT 10
            """
        )
        recent_rows = await recent_cursor.fetchall()
        recent_runs = []
        for row in recent_rows:
            d = _row_to_dict(row)
            if d["status"] == "done":
                err_cursor = await conn.execute(
                    """
                    SELECT AVG(tychos_error_arcmin) AS mean_error
                    FROM eclipse_results WHERE run_id = ?
                    """,
                    (d["id"],),
                )
                err_row = await err_cursor.fetchone()
                d["mean_tychos_error"] = (
                    round(err_row["mean_error"], 2) if err_row["mean_error"] is not None else None
                )
            else:
                d["mean_tychos_error"] = None
            recent_runs.append(d)

        leader_cursor = await conn.execute(
            """
            SELECT ps.name AS param_set_name, u.name AS owner_name,
                   AVG(sub.mean_error) AS avg_mean_error
            FROM (
                SELECT r.id AS run_id, pv.param_set_id,
                       AVG(er.tychos_error_arcmin) AS mean_error
                FROM runs r
                JOIN param_versions pv ON r.param_version_id = pv.id
                JOIN eclipse_results er ON er.run_id = r.id
                WHERE r.status = 'done' AND r.total_eclipses > 0
                    AND er.tychos_error_arcmin IS NOT NULL
                GROUP BY r.id
            ) sub
            JOIN param_sets ps ON sub.param_set_id = ps.id
            JOIN users u ON ps.owner_id = u.id
            GROUP BY ps.id
            ORDER BY avg_mean_error ASC
            LIMIT 20
            """
        )
        leaderboard = [_row_to_dict(r) for r in await leader_cursor.fetchall()]

    return {
        "total_param_sets": total_param_sets,
        "best_solar": best_by_dataset.get("solar_eclipse"),
        "best_lunar": best_by_dataset.get("lunar_eclipse"),
        "recent_runs": recent_runs,
        "leaderboard": leaderboard,
    }

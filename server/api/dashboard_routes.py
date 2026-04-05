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

        # Best solar: highest overall_pass rate (threshold + JPL rescued)
        best_solar_cursor = await conn.execute(
            """
            SELECT ps.name, pv.version_number,
                   SUM(CASE WHEN er.detected = 1 OR (er.moon_error_arcmin IS NOT NULL AND er.moon_error_arcmin < 60) THEN 1 ELSE 0 END) AS overall_pass,
                   COUNT(*) AS total,
                   CAST(SUM(CASE WHEN er.detected = 1 OR (er.moon_error_arcmin IS NOT NULL AND er.moon_error_arcmin < 60) THEN 1 ELSE 0 END) AS REAL) / COUNT(*) AS rate
            FROM runs r
            JOIN param_versions pv ON r.param_version_id = pv.id
            JOIN param_sets ps ON pv.param_set_id = ps.id
            JOIN eclipse_results er ON er.run_id = r.id
            WHERE r.test_type = 'solar' AND r.status = 'done' AND r.total_eclipses > 0
            GROUP BY r.id
            ORDER BY rate DESC
            LIMIT 1
            """
        )
        best_solar_row = await best_solar_cursor.fetchone()
        best_solar = (
            {"name": f"{best_solar_row['name']} v{best_solar_row['version_number']}", "rate": best_solar_row["rate"]}
            if best_solar_row else None
        )

        # Best lunar
        best_lunar_cursor = await conn.execute(
            """
            SELECT ps.name, pv.version_number,
                   CAST(SUM(CASE WHEN er.detected = 1 OR (er.moon_error_arcmin IS NOT NULL AND er.moon_error_arcmin < 60) THEN 1 ELSE 0 END) AS REAL) / COUNT(*) AS rate
            FROM runs r
            JOIN param_versions pv ON r.param_version_id = pv.id
            JOIN param_sets ps ON pv.param_set_id = ps.id
            JOIN eclipse_results er ON er.run_id = r.id
            WHERE r.test_type = 'lunar' AND r.status = 'done' AND r.total_eclipses > 0
            GROUP BY r.id
            ORDER BY rate DESC
            LIMIT 1
            """
        )
        best_lunar_row = await best_lunar_cursor.fetchone()
        best_lunar = (
            {"name": f"{best_lunar_row['name']} v{best_lunar_row['version_number']}", "rate": best_lunar_row["rate"]}
            if best_lunar_row else None
        )

        # Recent runs with overall_pass
        recent_cursor = await conn.execute(
            """
            SELECT r.id, ps.name AS param_set_name, pv.version_number, u.name AS owner_name,
                   r.test_type, r.status, r.total_eclipses, r.detected, r.created_at
            FROM runs r
            JOIN param_versions pv ON r.param_version_id = pv.id
            JOIN param_sets ps ON pv.param_set_id = ps.id
            JOIN users u ON ps.owner_id = u.id
            ORDER BY r.created_at DESC
            LIMIT 10
            """
        )
        recent_rows = await recent_cursor.fetchall()
        recent_runs = []
        for row in recent_rows:
            d = _row_to_dict(row)
            if d["status"] == "done":
                op_cursor = await conn.execute(
                    """
                    SELECT SUM(CASE WHEN detected = 1 OR (moon_error_arcmin IS NOT NULL AND moon_error_arcmin < 60) THEN 1 ELSE 0 END) AS overall_pass
                    FROM eclipse_results WHERE run_id = ?
                    """,
                    (d["id"],),
                )
                op_row = await op_cursor.fetchone()
                d["overall_pass"] = op_row["overall_pass"] or 0
            else:
                d["overall_pass"] = None
            recent_runs.append(d)

        # Leaderboard: param sets ordered by avg overall pass rate
        leader_cursor = await conn.execute(
            """
            SELECT ps.name AS param_set_name, u.name AS owner_name,
                   AVG(
                       CAST(sub.overall_pass AS REAL) / sub.total
                   ) AS avg_rate
            FROM (
                SELECT r.id AS run_id, pv.param_set_id,
                       SUM(CASE WHEN er.detected = 1 OR (er.moon_error_arcmin IS NOT NULL AND er.moon_error_arcmin < 60) THEN 1 ELSE 0 END) AS overall_pass,
                       COUNT(*) AS total
                FROM runs r
                JOIN param_versions pv ON r.param_version_id = pv.id
                JOIN eclipse_results er ON er.run_id = r.id
                WHERE r.status = 'done' AND r.total_eclipses > 0
                GROUP BY r.id
            ) sub
            JOIN param_sets ps ON sub.param_set_id = ps.id
            JOIN users u ON ps.owner_id = u.id
            GROUP BY ps.id
            ORDER BY avg_rate DESC
            LIMIT 20
            """
        )
        leaderboard = [_row_to_dict(r) for r in await leader_cursor.fetchall()]

    return {
        "total_param_sets": total_param_sets,
        "best_solar": best_solar,
        "best_lunar": best_lunar,
        "recent_runs": recent_runs,
        "leaderboard": leaderboard,
    }

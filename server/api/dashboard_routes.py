"""Dashboard routes: summary stats and leaderboard."""
from fastapi import APIRouter

from server.db import get_db

router = APIRouter(prefix="/api/dashboard")


def _row_to_dict(row) -> dict:
    return dict(row)


@router.get("/")
def dashboard():
    """Return aggregate stats, best runs, recent runs, and a leaderboard."""
    with get_db() as conn:
        total_param_sets = conn.execute(
            "SELECT COUNT(*) FROM param_sets"
        ).fetchone()[0]

        # Best solar: highest detected/total_eclipses rate among done runs
        best_solar_row = conn.execute(
            """
            SELECT p.name, CAST(r.detected AS REAL) / r.total_eclipses AS rate
            FROM runs r
            JOIN param_sets p ON r.param_set_id = p.id
            WHERE r.test_type = 'solar' AND r.status = 'done'
              AND r.total_eclipses > 0
            ORDER BY rate DESC
            LIMIT 1
            """
        ).fetchone()
        best_solar = (
            {"name": best_solar_row["name"], "rate": best_solar_row["rate"]}
            if best_solar_row
            else None
        )

        # Best lunar
        best_lunar_row = conn.execute(
            """
            SELECT p.name, CAST(r.detected AS REAL) / r.total_eclipses AS rate
            FROM runs r
            JOIN param_sets p ON r.param_set_id = p.id
            WHERE r.test_type = 'lunar' AND r.status = 'done'
              AND r.total_eclipses > 0
            ORDER BY rate DESC
            LIMIT 1
            """
        ).fetchone()
        best_lunar = (
            {"name": best_lunar_row["name"], "rate": best_lunar_row["rate"]}
            if best_lunar_row
            else None
        )

        # Recent runs (last 10)
        recent_rows = conn.execute(
            """
            SELECT r.id, p.name AS param_set_name, u.name AS owner_name,
                   r.test_type, r.status, r.total_eclipses, r.detected, r.created_at
            FROM runs r
            JOIN param_sets p ON r.param_set_id = p.id
            JOIN users u ON p.owner_id = u.id
            ORDER BY r.created_at DESC
            LIMIT 10
            """
        ).fetchall()
        recent_runs = [_row_to_dict(r) for r in recent_rows]

        # Leaderboard: param sets ordered by avg detection rate across done runs
        leader_rows = conn.execute(
            """
            SELECT p.name AS param_set_name, u.name AS owner_name,
                   AVG(CAST(r.detected AS REAL) / r.total_eclipses) AS avg_rate
            FROM runs r
            JOIN param_sets p ON r.param_set_id = p.id
            JOIN users u ON p.owner_id = u.id
            WHERE r.status = 'done' AND r.total_eclipses > 0
            GROUP BY p.id
            ORDER BY avg_rate DESC
            LIMIT 20
            """
        ).fetchall()
        leaderboard = [_row_to_dict(r) for r in leader_rows]

    return {
        "total_param_sets": total_param_sets,
        "best_solar": best_solar,
        "best_lunar": best_lunar,
        "recent_runs": recent_runs,
        "leaderboard": leaderboard,
    }

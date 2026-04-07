"""Dataset routes: list datasets and browse catalog data."""
from fastapi import APIRouter, HTTPException, Query

from server.db import get_async_db

router = APIRouter(prefix="/api/datasets")


@router.get("")
async def list_datasets():
    """Return all datasets with metadata."""
    async with get_async_db() as conn:
        cursor = await conn.execute("SELECT * FROM datasets ORDER BY id")
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]


@router.get("/summary")
async def dataset_summary():
    """Return summary stats for all datasets, keyed by slug."""
    async with get_async_db() as conn:
        ds_cursor = await conn.execute("SELECT id, slug FROM datasets ORDER BY id")
        datasets = await ds_cursor.fetchall()

        results = {}
        for ds in datasets:
            type_cursor = await conn.execute(
                """
                SELECT type AS catalog_type, COUNT(*) AS count
                FROM eclipse_catalog
                WHERE dataset_id = ?
                GROUP BY type
                ORDER BY count DESC
                """,
                (ds["id"],),
            )
            breakdown = [dict(r) for r in await type_cursor.fetchall()]

            count_cursor = await conn.execute(
                "SELECT COUNT(*) FROM eclipse_catalog WHERE dataset_id = ?",
                (ds["id"],),
            )
            total = (await count_cursor.fetchone())[0]

            results[ds["slug"]] = {"total": total, "breakdown": breakdown}

    return results


@router.get("/{slug}")
async def get_dataset_catalog(
    slug: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    catalog_type: str | None = Query(default=None),
):
    """Return paginated catalog data for a dataset by slug."""
    async with get_async_db() as conn:
        ds_cursor = await conn.execute(
            "SELECT id, slug, event_type FROM datasets WHERE slug = ?", (slug,)
        )
        ds = await ds_cursor.fetchone()
        if not ds:
            raise HTTPException(status_code=404, detail=f"Dataset '{slug}' not found")

        dataset_id = ds["id"]
        event_type = ds["event_type"]
        offset = (page - 1) * page_size

        conditions = ["dataset_id = ?"]
        values: list = [dataset_id]

        if catalog_type:
            conditions.append("type = ?")
            values.append(catalog_type)

        where = " AND ".join(conditions)

        count_cursor = await conn.execute(
            f"SELECT COUNT(*) FROM eclipse_catalog WHERE {where}", values
        )
        total = (await count_cursor.fetchone())[0]

        if event_type == "solar_eclipse":
            cols = """id, catalog_number, julian_day_tt, date, delta_t_s,
                      luna_num, saros_num, type_raw, type, qle, gamma,
                      magnitude, lat, lon, sun_alt_deg, path_width_km, duration_s"""
        else:
            cols = """id, catalog_number, julian_day_tt, date, delta_t_s,
                      luna_num, saros_num, type_raw, type, qse, gamma,
                      pen_mag, um_mag, magnitude,
                      pen_duration_min, par_duration_min, total_duration_min,
                      zenith_lat, zenith_lon"""

        cursor = await conn.execute(
            f"""
            SELECT {cols}
            FROM eclipse_catalog
            WHERE {where}
            ORDER BY julian_day_tt
            LIMIT ? OFFSET ?
            """,
            values + [page_size, offset],
        )
        rows = [dict(r) for r in await cursor.fetchall()]

    return {
        "eclipses": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "event_type": event_type,
    }

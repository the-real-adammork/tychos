"""Dataset routes: list datasets and browse catalog data."""
from fastapi import APIRouter, HTTPException, Query

from server.db import get_async_db

router = APIRouter(prefix="/api/datasets")


@router.get("")
async def list_datasets():
    """Return all datasets with metadata."""
    async with get_async_db() as conn:
        rows = await conn.fetch("SELECT * FROM datasets ORDER BY id")
    return [dict(r) for r in rows]


@router.get("/summary")
async def dataset_summary():
    """Return summary stats for all datasets, keyed by slug."""
    async with get_async_db() as conn:
        datasets = await conn.fetch("SELECT id, slug FROM datasets ORDER BY id")

        results = {}
        for ds in datasets:
            type_rows = await conn.fetch(
                """
                SELECT type AS catalog_type, COUNT(*) AS count
                FROM eclipse_catalog
                WHERE dataset_id = $1
                GROUP BY type
                ORDER BY count DESC
                """,
                ds["id"],
            )
            breakdown = [dict(r) for r in type_rows]

            total = await conn.fetchval(
                "SELECT COUNT(*) FROM eclipse_catalog WHERE dataset_id = $1",
                ds["id"],
            )

            results[ds["slug"]] = {"total": total, "breakdown": breakdown}

    return results


@router.get("/{slug}")
async def get_dataset_catalog(
    slug: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    catalog_type: str | None = Query(default=None),
    saros: int | None = Query(default=None),
):
    """Return paginated catalog data for a dataset by slug."""
    async with get_async_db() as conn:
        ds = await conn.fetchrow(
            "SELECT * FROM datasets WHERE slug = $1", slug
        )
        if not ds:
            raise HTTPException(status_code=404, detail=f"Dataset '{slug}' not found")

        ds_dict = dict(ds)
        dataset_id = ds_dict["id"]
        event_type = ds_dict["event_type"]
        offset = (page - 1) * page_size

        values: list = [dataset_id]
        conditions = [f"dataset_id = ${len(values)}"]

        if catalog_type:
            values.append(catalog_type)
            conditions.append(f"type = ${len(values)}")

        if saros is not None:
            values.append(saros)
            conditions.append(f"saros_num = ${len(values)}")

        where = " AND ".join(conditions)

        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM eclipse_catalog WHERE {where}", *values
        )

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

        paginated_values = values + [page_size, offset]
        limit_idx = len(values) + 1
        offset_idx = len(values) + 2
        rows = await conn.fetch(
            f"""
            SELECT {cols}
            FROM eclipse_catalog
            WHERE {where}
            ORDER BY julian_day_tt
            LIMIT ${limit_idx} OFFSET ${offset_idx}
            """,
            *paginated_values,
        )

    return {
        "dataset": {
            "name": ds_dict["name"],
            "description": ds_dict["description"],
            "source_url": ds_dict["source_url"],
            "event_type": event_type,
            "record_count": ds_dict["record_count"],
        },
        "eclipses": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "event_type": event_type,
    }


@router.get("/{slug}/{eclipse_id}")
async def get_dataset_eclipse(slug: str, eclipse_id: int):
    """Return a single eclipse catalog record + its predicted geometry."""
    async with get_async_db() as conn:
        ds = await conn.fetchrow(
            "SELECT * FROM datasets WHERE slug = $1", slug
        )
        if not ds:
            raise HTTPException(status_code=404, detail=f"Dataset '{slug}' not found")

        ds_dict = dict(ds)
        dataset_id = ds_dict["id"]
        event_type = ds_dict["event_type"]
        test_type = slug.replace("_eclipse", "")

        row = await conn.fetchrow(
            """
            SELECT ec.*,
                   pr.expected_separation_arcmin,
                   pr.moon_apparent_radius_arcmin,
                   pr.sun_apparent_radius_arcmin,
                   pr.umbra_radius_arcmin,
                   pr.penumbra_radius_arcmin,
                   pr.approach_angle_deg
            FROM eclipse_catalog ec
            LEFT JOIN predicted_reference pr ON pr.julian_day_tt = ec.julian_day_tt
                AND pr.test_type = $1
            WHERE ec.id = $2 AND ec.dataset_id = $3
            """,
            test_type, eclipse_id, dataset_id,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Eclipse not found")

        eclipse = dict(row)
        saros_num = eclipse.get("saros_num")

        saros_context = {
            "saros_total": None,
            "saros_position": None,
            "saros_year_start": None,
            "saros_year_end": None,
            "saros_neighbors": [],
        }
        if saros_num is not None:
            series_rows = await conn.fetch(
                """
                SELECT id, julian_day_tt, date, type
                FROM eclipse_catalog
                WHERE dataset_id = $1 AND saros_num = $2
                ORDER BY julian_day_tt
                """,
                dataset_id, saros_num,
            )
            series = [dict(r) for r in series_rows]
            position = next((i for i, s in enumerate(series) if s["id"] == eclipse_id), 0)

            saros_context["saros_total"] = len(series)
            saros_context["saros_position"] = position + 1
            saros_context["saros_year_start"] = series[0]["date"][:4] if series else None
            saros_context["saros_year_end"] = series[-1]["date"][:4] if series else None

            start = max(0, position - 5)
            end = min(len(series), position + 6)
            for i in range(start, end):
                s = series[i]
                saros_context["saros_neighbors"].append({
                    "id": s["id"],
                    "date": s["date"],
                    "catalog_type": s["type"],
                    "position": i + 1,
                    "is_self": s["id"] == eclipse_id,
                })

        eclipse.update(saros_context)

    return {
        "dataset": {
            "name": ds_dict["name"],
            "slug": slug,
            "event_type": event_type,
        },
        "test_type": test_type,
        "eclipse": eclipse,
    }

"""Persist param sets and versions as JSON files on disk.

Structure:
  params/
    {slug}/
      meta.json   — { name, description, forked_from }
      v1.json     — { version_number, parent, notes, params }
      v2.json     — ...

This allows the DB to be fully re-seeded from disk artifacts.
"""
import json
import re
from pathlib import Path

PARAMS_DIR = Path(__file__).parent.parent / "params"


def _slugify(name: str) -> str:
    """Convert a param set name to a filesystem-safe slug."""
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def save_param_set(name: str, description: str | None = None, forked_from: str | None = None):
    """Write (or overwrite) the meta.json for a param set."""
    slug = _slugify(name)
    d = PARAMS_DIR / slug
    d.mkdir(parents=True, exist_ok=True)

    meta = {"name": name, "description": description, "forked_from": forked_from}
    (d / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return slug


def save_param_version(
    param_set_name: str,
    version_number: int,
    params: dict,
    notes: str | None = None,
    parent_version: str | None = None,
):
    """Write a version file (e.g. v1.json) for a param set.

    parent_version is a human-readable reference like "v1-original/v2" or None.
    """
    slug = _slugify(param_set_name)
    d = PARAMS_DIR / slug
    d.mkdir(parents=True, exist_ok=True)

    version_data = {
        "version_number": version_number,
        "parent": parent_version,
        "notes": notes,
        "params": params,
    }
    filename = f"v{version_number}.json"
    (d / filename).write_text(json.dumps(version_data, indent=2) + "\n")


def load_all_param_sets() -> list[dict]:
    """Load all param sets from disk for re-seeding.

    Returns a list of dicts with keys: name, description, forked_from, versions.
    Versions are sorted by version_number ascending.
    """
    if not PARAMS_DIR.is_dir():
        return []

    results = []
    for d in sorted(PARAMS_DIR.iterdir()):
        if not d.is_dir():
            continue
        meta_path = d / "meta.json"
        if not meta_path.exists():
            continue

        meta = json.loads(meta_path.read_text())

        versions = []
        for vf in sorted(d.glob("v*.json")):
            if vf.name == "meta.json":
                continue
            version_data = json.loads(vf.read_text())
            versions.append(version_data)

        versions.sort(key=lambda v: v["version_number"])
        meta["versions"] = versions
        results.append(meta)

    return results

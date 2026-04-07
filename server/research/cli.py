"""CLI command implementations for `python -m server.research`."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from server.research.sandbox import (
    JobPaths,
    write_json,
    load_json,
    append_log,
    params_hash,
    read_log_tail,
)
from server.research.program_md import render_template, parse_frontmatter
from server.research.subset import select_subset, load_eclipses_for_dataset
from server.research.allowlist import (
    check_diff_against_allowlist,
    AllowlistViolation,
)
from server.research.objective import compute_objective, aux_stats, EmptyResults

# Map short --dataset arg to the dataset slug used in the DB and in scanner dispatch.
_DATASET_SLUG = {
    "solar": "solar_eclipse",
    "lunar": "lunar_eclipse",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_base_params(base_arg: str) -> dict:
    """Load the params dict from a versioned param file.

    `base_arg` is like 'v1-original/v2'. Resolves to params/<dir>/<file>.json.
    """
    repo_root = Path(__file__).parent.parent.parent
    parts = base_arg.split("/")
    if len(parts) != 2:
        raise ValueError(f"--base must be like 'v1-original/v2', got {base_arg!r}")
    version_dir, version_file = parts
    path = repo_root / "params" / version_dir / f"{version_file}.json"
    if not path.exists():
        raise FileNotFoundError(f"Base param version not found: {path}")
    raw = load_json(path)
    if "params" not in raw:
        raise ValueError(f"Param file {path} missing top-level 'params' key")
    return raw["params"]


def cmd_init(args) -> int:
    paths = JobPaths.for_job(args.job)
    if paths.root.exists():
        print(f"error: job directory already exists: {paths.root}", file=sys.stderr)
        return 2

    dataset_slug = _DATASET_SLUG[args.dataset]
    base_params = _resolve_base_params(args.base)

    paths.root.mkdir(parents=True, exist_ok=False)

    # baseline.json + current.json — identical at init time
    write_json(paths.baseline_json, base_params)
    write_json(paths.current_json, base_params)

    # subset.json — frozen stratified pick
    catalog = load_eclipses_for_dataset(dataset_slug)
    if not catalog:
        print(f"error: no eclipses found for dataset {dataset_slug}", file=sys.stderr)
        return 3
    chosen = select_subset(catalog, n=args.subset_size, seed=args.seed)
    write_json(paths.subset_json, {
        "dataset_slug": dataset_slug,
        "n_requested": args.subset_size,
        "seed": args.seed,
        "selected_at": _now_iso(),
        "events": chosen,
    })

    # program.md — render from template
    paths.program_md.write_text(
        render_template(
            job_name=args.job,
            dataset_slug=dataset_slug,
            base_param_version=args.base,
        )
    )

    # log.jsonl — empty file (touch)
    paths.log_jsonl.touch()

    print(f"Initialized job at {paths.root}")
    print(f"  dataset: {dataset_slug}")
    print(f"  base:    {args.base}")
    print(f"  subset:  {len(chosen)} events (seed={args.seed})")
    print()
    print(f"Next: open `claude` in this repo and point it at:")
    print(f"  {paths.program_md}")
    return 0


def cmd_iterate(args) -> int:
    raise NotImplementedError


def cmd_validate(args) -> int:
    raise NotImplementedError

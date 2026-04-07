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


def _load_job_state(job_name: str):
    """Load all sandbox files needed for iterate/validate. Returns a tuple."""
    paths = JobPaths.for_job(job_name)
    if not paths.root.exists():
        raise FileNotFoundError(
            f"Job directory not found: {paths.root}. Run `init` first."
        )
    current = load_json(paths.current_json)
    baseline = load_json(paths.baseline_json)
    program_md = paths.program_md.read_text()
    frontmatter = parse_frontmatter(program_md)
    subset_blob = load_json(paths.subset_json)
    return paths, current, baseline, frontmatter, subset_blob


def _run_scan(dataset_slug: str, params: dict, eclipses: list[dict]) -> list[dict]:
    """Dispatch to the right scanner for the dataset."""
    from server.services.scanner import scan_solar_eclipses, scan_lunar_eclipses
    if dataset_slug == "solar_eclipse":
        return scan_solar_eclipses(params, eclipses)
    if dataset_slug == "lunar_eclipse":
        return scan_lunar_eclipses(params, eclipses)
    raise ValueError(f"Unknown dataset_slug: {dataset_slug}")


def _next_iter_number(log_path) -> int:
    tail = read_log_tail(log_path, n=1)
    if not tail:
        return 1
    return int(tail[0].get("iter", 0)) + 1


def cmd_iterate(args) -> int:
    try:
        paths, current, baseline, frontmatter, subset_blob = _load_job_state(args.job)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    # Guardrail: allowlist diff
    try:
        check_diff_against_allowlist(
            current,
            baseline,
            allowlist_globs=frontmatter.get("allowlist", []),
            known_bodies=list(baseline.keys()),
        )
    except AllowlistViolation as e:
        print(f"error: allowlist violation: {e}", file=sys.stderr)
        return 4

    # Guardrail: hash dedup
    h = params_hash(current)
    tail = read_log_tail(paths.log_jsonl, n=1)
    if tail and tail[0].get("params_hash") == h and tail[0].get("kind") == "iterate":
        cached = tail[0]
        print(f"objective: {cached['objective']}")
        print(f"mean_separation_arcmin: {cached.get('mean_separation_arcmin')}")
        print(f"detected: {cached.get('n_detected')}/{cached.get('n_total')}")
        print("(cached — current.json identical to last iterate)")
        return 0

    dataset_slug = subset_blob["dataset_slug"]
    eclipses = subset_blob["events"]

    try:
        results = _run_scan(dataset_slug, current, eclipses)
        objective = compute_objective(results)
    except EmptyResults as e:
        print(f"error: {e}", file=sys.stderr)
        return 5

    aux = aux_stats(results)

    entry = {
        "iter": _next_iter_number(paths.log_jsonl),
        "ts": _now_iso(),
        "kind": "iterate",
        "params_hash": h,
        "objective": round(objective, 4),
        **aux,
    }
    append_log(paths.log_jsonl, entry)

    print(f"objective: {entry['objective']}")
    print(f"mean_separation_arcmin: {aux['mean_separation_arcmin']}")
    print(f"detected: {aux['n_detected']}/{aux['n_total']}")
    return 0


def cmd_validate(args) -> int:
    try:
        paths, current, baseline, frontmatter, subset_blob = _load_job_state(args.job)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    # Same guardrails as iterate
    try:
        check_diff_against_allowlist(
            current,
            baseline,
            allowlist_globs=frontmatter.get("allowlist", []),
            known_bodies=list(baseline.keys()),
        )
    except AllowlistViolation as e:
        print(f"error: allowlist violation: {e}", file=sys.stderr)
        return 4

    dataset_slug = subset_blob["dataset_slug"]
    full_catalog = load_eclipses_for_dataset(dataset_slug)
    if not full_catalog:
        print(f"error: no eclipses found for dataset {dataset_slug}", file=sys.stderr)
        return 3

    try:
        results = _run_scan(dataset_slug, current, full_catalog)
        objective = compute_objective(results)
    except EmptyResults as e:
        print(f"error: {e}", file=sys.stderr)
        return 5

    aux = aux_stats(results)

    entry = {
        "iter": _next_iter_number(paths.log_jsonl),
        "ts": _now_iso(),
        "kind": "validate",
        "params_hash": params_hash(current),
        "validation_objective": round(objective, 4),
        **aux,
    }
    append_log(paths.log_jsonl, entry)

    print(f"validation_objective: {entry['validation_objective']}")
    print(f"mean_separation_arcmin: {aux['mean_separation_arcmin']}")
    print(f"detected: {aux['n_detected']}/{aux['n_total']}")
    return 0

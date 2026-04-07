import json
from types import SimpleNamespace

from server.research import cli


def _init_args(job, base="v1-original/v1", dataset="solar"):
    return SimpleNamespace(
        job=job, base=base, dataset=dataset, subset_size=3, seed=42,
        # Explicit override avoids the dataset-default DB lookup path so
        # smoke tests stay isolated from the live datasets table.
        scan_window_hours=2.0,
    )


def _job_args(job):
    return SimpleNamespace(job=job)


def test_init_creates_all_sandbox_files(
    isolated_research_root, patched_catalog_loader, capsys
):
    rc = cli.cmd_init(_init_args("smoke-1"))
    assert rc == 0
    job_root = isolated_research_root / "smoke-1"
    assert job_root.exists()
    for name in ("baseline.json", "current.json", "subset.json", "program.md", "log.jsonl"):
        assert (job_root / name).exists(), f"missing {name}"
    # Sanity: subset has the requested 3 events + the explicit window override.
    subset = json.loads((job_root / "subset.json").read_text())
    assert subset["scan_window_hours"] == 2.0
    assert len(subset["events"]) == 3


def test_iterate_prints_objective_and_logs(
    isolated_research_root, patched_catalog_loader, capsys
):
    cli.cmd_init(_init_args("smoke-2"))
    capsys.readouterr()  # discard init output

    rc = cli.cmd_iterate(_job_args("smoke-2"))
    assert rc == 0
    out = capsys.readouterr().out
    assert "objective:" in out

    log_path = isolated_research_root / "smoke-2" / "log.jsonl"
    lines = [line for line in log_path.read_text().splitlines() if line.strip()]
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["kind"] == "iterate"
    assert "objective" in entry
    assert entry["n_total"] == 3


def test_iterate_dedups_on_unchanged_params(
    isolated_research_root, patched_catalog_loader, capsys
):
    cli.cmd_init(_init_args("smoke-3"))
    capsys.readouterr()

    cli.cmd_iterate(_job_args("smoke-3"))
    capsys.readouterr()

    cli.cmd_iterate(_job_args("smoke-3"))
    out = capsys.readouterr().out
    assert "cached" in out

    log_path = isolated_research_root / "smoke-3" / "log.jsonl"
    lines = [line for line in log_path.read_text().splitlines() if line.strip()]
    assert len(lines) == 1, "second iterate should not append a new log entry"


def test_validate_prints_validation_objective_and_logs(
    isolated_research_root, patched_catalog_loader, capsys
):
    cli.cmd_init(_init_args("smoke-4"))
    capsys.readouterr()

    rc = cli.cmd_validate(_job_args("smoke-4"))
    assert rc == 0
    out = capsys.readouterr().out
    assert "validation_objective:" in out

    log_path = isolated_research_root / "smoke-4" / "log.jsonl"
    entries = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
    assert len(entries) == 1
    assert entries[0]["kind"] == "validate"


def test_iterate_rejects_disallowed_param_change(
    isolated_research_root, patched_catalog_loader, capsys
):
    cli.cmd_init(_init_args("smoke-5"))
    capsys.readouterr()

    # Mutate a non-allowlisted body (mars) directly in current.json
    job_root = isolated_research_root / "smoke-5"
    current = json.loads((job_root / "current.json").read_text())
    current["mars"]["speed"] = current["mars"]["speed"] + 0.001
    (job_root / "current.json").write_text(json.dumps(current, indent=2))

    rc = cli.cmd_iterate(_job_args("smoke-5"))
    assert rc == 4
    err = capsys.readouterr().err
    assert "mars.speed" in err


def test_init_falls_back_to_dataset_scan_window(
    isolated_research_root, patched_catalog_loader, monkeypatch, capsys
):
    """When --scan-window-hours is None, init reads from get_dataset_scan_window."""
    from server.research import cli as cli_mod

    monkeypatch.setattr(cli_mod, "get_dataset_scan_window", lambda slug: 7.5)

    args = SimpleNamespace(
        job="smoke-6", base="v1-original/v1", dataset="solar",
        subset_size=3, seed=42, scan_window_hours=None,
    )
    rc = cli.cmd_init(args)
    assert rc == 0

    subset = json.loads((isolated_research_root / "smoke-6" / "subset.json").read_text())
    assert subset["scan_window_hours"] == 7.5

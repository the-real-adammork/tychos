import json
from pathlib import Path

import pytest

from server.research.sandbox import (
    JobPaths,
    params_hash,
    append_log,
    read_log_tail,
    load_json,
    write_json,
)


def test_job_paths_resolves_files(tmp_path: Path):
    paths = JobPaths(root=tmp_path / "myjob")
    assert paths.root == tmp_path / "myjob"
    assert paths.current_json == tmp_path / "myjob" / "current.json"
    assert paths.baseline_json == tmp_path / "myjob" / "baseline.json"
    assert paths.subset_json == tmp_path / "myjob" / "subset.json"
    assert paths.program_md == tmp_path / "myjob" / "program.md"
    assert paths.log_jsonl == tmp_path / "myjob" / "log.jsonl"


def test_params_hash_is_stable_across_dict_order():
    a = {"moon": {"speed": 83.0, "start_pos": 261.2}}
    b = {"moon": {"start_pos": 261.2, "speed": 83.0}}
    assert params_hash(a) == params_hash(b)


def test_params_hash_changes_with_value():
    a = {"moon": {"speed": 83.0}}
    b = {"moon": {"speed": 83.5}}
    assert params_hash(a) != params_hash(b)


def test_append_and_read_log_tail(tmp_path: Path):
    log = tmp_path / "log.jsonl"
    append_log(log, {"iter": 1, "objective": 5.0})
    append_log(log, {"iter": 2, "objective": 4.5})
    append_log(log, {"iter": 3, "objective": 4.0})
    tail = read_log_tail(log, n=2)
    assert len(tail) == 2
    assert tail[0]["iter"] == 2
    assert tail[1]["iter"] == 3


def test_read_log_tail_handles_missing_file(tmp_path: Path):
    assert read_log_tail(tmp_path / "missing.jsonl", n=5) == []


def test_write_and_load_json_roundtrip(tmp_path: Path):
    p = tmp_path / "x.json"
    write_json(p, {"a": 1, "b": [1, 2, 3]})
    assert load_json(p) == {"a": 1, "b": [1, 2, 3]}


def test_load_json_missing_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_json(tmp_path / "nope.json")

"""Sandbox directory layout, JSON I/O, content hashing, and JSONL log writer."""
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

PARAMS_RESEARCH_ROOT = Path(__file__).parent.parent.parent / "params" / "research"


@dataclass
class JobPaths:
    """Resolved file paths for a single research job."""
    root: Path

    @property
    def current_json(self) -> Path:
        return self.root / "current.json"

    @property
    def baseline_json(self) -> Path:
        return self.root / "baseline.json"

    @property
    def subset_json(self) -> Path:
        return self.root / "subset.json"

    @property
    def program_md(self) -> Path:
        return self.root / "program.md"

    @property
    def log_jsonl(self) -> Path:
        return self.root / "log.jsonl"

    @classmethod
    def for_job(cls, job_name: str) -> "JobPaths":
        return cls(root=PARAMS_RESEARCH_ROOT / job_name)


def load_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")


def params_hash(params: dict) -> str:
    """Stable content hash over the params dict (order-independent)."""
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def append_log(log_path: Path, entry: dict) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as f:
        f.write(json.dumps(entry) + "\n")


def read_log_tail(log_path: Path, n: int) -> list[dict]:
    if not log_path.exists():
        return []
    with open(log_path) as f:
        lines = [line for line in f if line.strip()]
    return [json.loads(line) for line in lines[-n:]]

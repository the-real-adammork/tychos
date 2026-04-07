"""program.md template rendering and frontmatter parsing.

We hand-parse a small subset of YAML to avoid adding PyYAML as a dependency:
  - Scalar key/value pairs: `key: value`
  - One list-of-strings: `allowlist:` followed by `  - item` lines
"""
from pathlib import Path

_TEMPLATE_PATH = Path(__file__).parent / "templates" / "program.md.tmpl"


def render_template(*, job_name: str, dataset_slug: str, base_param_version: str) -> str:
    raw = _TEMPLATE_PATH.read_text()
    return raw.format(
        job_name=job_name,
        dataset_slug=dataset_slug,
        base_param_version=base_param_version,
    )


def parse_frontmatter(md: str) -> dict:
    """Extract the YAML-ish frontmatter block delimited by `---` lines.

    Returns a dict with scalar values plus an `allowlist` list. Raises
    ValueError if no frontmatter is present.
    """
    lines = md.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("program.md must start with a '---' frontmatter block")
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        raise ValueError("Unterminated frontmatter block (missing closing ---)")

    body_lines = lines[1:end_idx]
    out: dict = {}
    i = 0
    while i < len(body_lines):
        line = body_lines[i]
        if not line.strip():
            i += 1
            continue
        if ":" not in line:
            raise ValueError(f"Malformed frontmatter line: {line!r}")
        key, _, rest = line.partition(":")
        key = key.strip()
        rest = rest.strip()
        if rest == "":
            # List follows
            items: list[str] = []
            j = i + 1
            while j < len(body_lines):
                next_line = body_lines[j]
                stripped = next_line.lstrip()
                if stripped.startswith("- "):
                    items.append(stripped[2:].strip())
                    j += 1
                elif not next_line.strip():
                    j += 1
                else:
                    break
            out[key] = items
            i = j
        else:
            out[key] = rest
            i += 1
    return out

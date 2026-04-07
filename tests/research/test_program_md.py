import pytest

from server.research.program_md import parse_frontmatter, render_template


def test_parse_frontmatter_extracts_allowlist():
    md = """---
job: test-1
dataset: solar_eclipse
base_param_version: v1-original/v2
allowlist:
  - moon.*
  - sun.speed
---

# body
"""
    fm = parse_frontmatter(md)
    assert fm["job"] == "test-1"
    assert fm["dataset"] == "solar_eclipse"
    assert fm["base_param_version"] == "v1-original/v2"
    assert fm["allowlist"] == ["moon.*", "sun.speed"]


def test_parse_frontmatter_missing_block_raises():
    with pytest.raises(ValueError):
        parse_frontmatter("# no frontmatter here\n")


def test_render_template_substitutes_placeholders():
    out = render_template(
        job_name="solar-fit-001",
        dataset_slug="solar_eclipse",
        base_param_version="v1-original/v2",
    )
    assert "job: solar-fit-001" in out
    assert "dataset: solar_eclipse" in out
    assert "base_param_version: v1-original/v2" in out
    assert "{job_name}" not in out
    assert "{dataset_slug}" not in out


def test_render_then_parse_roundtrip():
    out = render_template(
        job_name="lunar-fit-001",
        dataset_slug="lunar_eclipse",
        base_param_version="v1-original/v2",
    )
    fm = parse_frontmatter(out)
    assert fm["job"] == "lunar-fit-001"
    assert fm["dataset"] == "lunar_eclipse"
    assert "moon.*" in fm["allowlist"]

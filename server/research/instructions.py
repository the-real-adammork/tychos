"""Render research-job instructions from the template."""
from pathlib import Path

_TEMPLATE_PATH = Path(__file__).parent / "templates" / "instructions.md.tmpl"
_BACKGROUND_PATH = Path(__file__).parent / "templates" / "background.md"


def render_instructions(
    *,
    job_id: int,
    job_name: str,
    dataset_slug: str,
    view_name: str,
    allowlist: list[str],
    param_set_id: int,
    date_start: str | None,
    date_end: str | None,
) -> str:
    if date_start and date_end:
        date_range = f"{date_start} to {date_end}"
        date_range_sentence = f"(restricted to eclipses in {date_range})"
    else:
        date_range = "full catalog"
        date_range_sentence = "(full catalog)"
    allowlist_yaml = "\n".join(f"  - {a}" for a in allowlist)
    background = _BACKGROUND_PATH.read_text() if _BACKGROUND_PATH.exists() else ""
    return _TEMPLATE_PATH.read_text().format(
        job_id=job_id,
        job_name=job_name,
        dataset_slug=dataset_slug,
        view_name=view_name,
        date_range=date_range,
        date_range_sentence=date_range_sentence,
        allowlist_yaml=allowlist_yaml,
        param_set_id=param_set_id,
        background=background,
    )

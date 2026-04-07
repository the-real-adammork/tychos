"""Allowlist parsing, glob expansion, and diff validation."""
from numbers import Real


class AllowlistViolation(Exception):
    """Raised when current.json contains a change forbidden by the allowlist."""


_ORBIT_FIELDS = (
    "orbit_radius",
    "orbit_center_a",
    "orbit_center_b",
    "orbit_center_c",
    "orbit_tilt_a",
    "orbit_tilt_b",
    "start_pos",
    "speed",
)


def expand_globs(globs: list[str], bodies: list[str]) -> set[str]:
    """Expand `body.*` patterns to concrete `body.field` keys.

    `globs` is a list of strings like 'moon.*' or 'sun.speed'.
    `bodies` is the list of known body names from baseline params.
    Returns a set of fully-qualified `body.field` strings.
    """
    out: set[str] = set()
    for g in globs:
        if "." not in g:
            raise ValueError(f"Allowlist entry must be 'body.field' or 'body.*': {g!r}")
        body, field = g.split(".", 1)
        if body not in bodies:
            # Silently ignore unknown bodies — allowlist may be reused across param sets.
            continue
        if field == "*":
            for f in _ORBIT_FIELDS:
                out.add(f"{body}.{f}")
        else:
            out.add(f"{body}.{field}")
    return out


def check_diff_against_allowlist(
    current: dict,
    baseline: dict,
    allowlist_globs: list[str],
    known_bodies: list[str],
) -> None:
    """Raise AllowlistViolation if current diverges from baseline outside the allowlist.

    Validates:
      - No added or removed bodies.
      - No added or removed keys within any body.
      - All allowlisted values are numeric.
      - Any value that differs from baseline is in the allowlist.
    """
    allowed = expand_globs(allowlist_globs, known_bodies)

    base_bodies = set(baseline.keys())
    cur_bodies = set(current.keys())
    if cur_bodies - base_bodies:
        raise AllowlistViolation(
            f"Bodies added to current.json that don't exist in baseline: "
            f"{sorted(cur_bodies - base_bodies)}"
        )
    if base_bodies - cur_bodies:
        raise AllowlistViolation(
            f"Bodies removed from current.json: {sorted(base_bodies - cur_bodies)}"
        )

    for body in sorted(base_bodies):
        base_fields = set(baseline[body].keys())
        cur_fields = set(current[body].keys())
        added = cur_fields - base_fields
        removed = base_fields - cur_fields
        if added:
            raise AllowlistViolation(
                f"Fields added to {body}: {sorted(added)}"
            )
        if removed:
            raise AllowlistViolation(
                f"Fields removed from {body}: {sorted(removed)}"
            )

        for field in sorted(base_fields):
            key = f"{body}.{field}"
            base_val = baseline[body][field]
            cur_val = current[body][field]

            if cur_val != base_val:
                if key not in allowed:
                    raise AllowlistViolation(
                        f"Disallowed change to {key}: "
                        f"baseline={base_val!r} current={cur_val!r}. "
                        f"Add it to the allowlist in program.md if intended."
                    )
                if not isinstance(cur_val, Real) or isinstance(cur_val, bool):
                    raise AllowlistViolation(
                        f"{key} must be numeric, got {type(cur_val).__name__}: {cur_val!r}"
                    )

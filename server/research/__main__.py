"""Entry point: `python -m server.research <command>`."""
import argparse
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m server.research")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Create a new research job directory")
    p_init.add_argument("job", help="Job name (directory name under params/research/)")
    p_init.add_argument("--base", required=True, help="Base param version, e.g. v1-original/v2")
    p_init.add_argument("--dataset", required=True, choices=["solar", "lunar"])
    # Legacy args kept for backwards compat but ignored (full catalog always used now)
    p_init.add_argument("--subset-size", type=int, default=0, help=argparse.SUPPRESS)
    p_init.add_argument("--seed", type=int, default=0, help=argparse.SUPPRESS)
    p_init.add_argument(
        "--mode",
        choices=["combined", "solar_position", "lunar_position"],
        default="combined",
        help="Objective mode: 'combined' (sun+moon positional error), "
             "'solar_position' (sun position only), or "
             "'lunar_position' (moon position only). Default: combined.",
    )
    p_init.add_argument(
        "--scan-window-hours",
        type=float,
        default=None,
        help="± half-window for the min-separation search (hours). "
             "Defaults to the dataset's stored scan_window_hours. Override "
             "per-job when you want to try a wider/narrower window without "
             "changing the dataset default.",
    )

    p_iter = sub.add_parser("iterate", help="Run one subset experiment")
    p_iter.add_argument("job")

    p_val = sub.add_parser("validate", help="Run a full-catalog validation")
    p_val.add_argument("job")

    p_search = sub.add_parser(
        "search",
        help="Run Nelder-Mead joint multi-parameter search over the subset",
    )
    p_search.add_argument("job")
    p_search.add_argument(
        "--params",
        required=True,
        help="Comma-separated list of body.field keys to search "
             "(e.g. 'moon.start_pos,moon_def_a.speed'). Every key must be "
             "in the job's program.md allowlist.",
    )
    p_search.add_argument(
        "--budget",
        type=int,
        default=50,
        help="Max scanner evaluations (default 50). Must be ≥ n+1 for n params.",
    )
    p_search.add_argument(
        "--scale",
        type=float,
        default=0.01,
        help="Initial simplex step as fraction of each starting value "
             "(default 0.01 = ±1%%). Zero-valued starts use a 1e-4 floor.",
    )

    args = parser.parse_args(argv)

    from server.research import cli
    if args.command == "init":
        return cli.cmd_init(args)
    if args.command == "iterate":
        return cli.cmd_iterate(args)
    if args.command == "validate":
        return cli.cmd_validate(args)
    if args.command == "search":
        return cli.cmd_search(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())

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
    p_init.add_argument("--subset-size", type=int, default=25)
    p_init.add_argument("--seed", type=int, default=42)
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

    args = parser.parse_args(argv)

    from server.research import cli
    if args.command == "init":
        return cli.cmd_init(args)
    if args.command == "iterate":
        return cli.cmd_iterate(args)
    if args.command == "validate":
        return cli.cmd_validate(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())

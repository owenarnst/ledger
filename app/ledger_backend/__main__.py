from __future__ import annotations

import argparse
from pathlib import Path

from .api import app
from .hooks import DEFAULT_SPOOL_DIR, build_session_start_nudge, drain_spool, reset_ledger
from .repository import DEFAULT_DB_PATH, DEFAULT_SANDBOX_ROOT, LedgerRepository

__all__ = ["app", "main"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ledger")
    subcommands = parser.add_subparsers(dest="command", required=True)

    reset = subcommands.add_parser("reset", help="Recreate the local Ledger demo database.")
    reset.add_argument("--db", default=str(DEFAULT_DB_PATH))
    reset.add_argument("--sandbox-root", default=str(DEFAULT_SANDBOX_ROOT))
    reset.add_argument("--spool-dir", default=str(DEFAULT_SPOOL_DIR))

    nudge = subcommands.add_parser("nudge", help="Print the Claude SessionStart notification line.")
    nudge.add_argument("--db", default=str(DEFAULT_DB_PATH))
    nudge.add_argument("--sandbox-root", default=str(DEFAULT_SANDBOX_ROOT))
    nudge.add_argument("--cwd", required=True)
    nudge.add_argument("--base-url", default="http://127.0.0.1:4317")

    drain = subcommands.add_parser("drain-spool", help="Import queued hook events.")
    drain.add_argument("--db", default=str(DEFAULT_DB_PATH))
    drain.add_argument("--sandbox-root", default=str(DEFAULT_SANDBOX_ROOT))
    drain.add_argument("--spool-dir", default=str(DEFAULT_SPOOL_DIR))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "reset":
        result = reset_ledger(
            db_path=Path(args.db),
            sandbox_root=Path(args.sandbox_root),
            spool_dir=Path(args.spool_dir),
        )
        print(f"Reset Ledger at {result['db_path']}")
        return 0
    if args.command == "nudge":
        repo = LedgerRepository(db_path=Path(args.db), sandbox_root=Path(args.sandbox_root))
        repo.initialize()
        print(build_session_start_nudge(repo, cwd=args.cwd, base_url=args.base_url))
        return 0
    if args.command == "drain-spool":
        repo = LedgerRepository(db_path=Path(args.db), sandbox_root=Path(args.sandbox_root))
        repo.initialize()
        result = drain_spool(repo, spool_dir=Path(args.spool_dir))
        print(f"Imported {result['imported']} hook events")
        return 0
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())

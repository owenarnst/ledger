from __future__ import annotations

import argparse
from pathlib import Path

from .api import app
from .hooks import DEFAULT_SPOOL_DIR, build_session_start_nudge, drain_spool, reset_ledger
from .repository import (
    DEFAULT_DB_PATH,
    DEFAULT_SANDBOX_ROOT,
    LedgerRepository,
    RecipeValidationError,
)

__all__ = ["app", "main"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ledger")
    subcommands = parser.add_subparsers(dest="command", required=True)

    reset = subcommands.add_parser("reset", help="Recreate an empty local Ledger database.")
    reset.add_argument("--db", default=str(DEFAULT_DB_PATH))
    reset.add_argument("--sandbox-root", default=str(DEFAULT_SANDBOX_ROOT))
    reset.add_argument("--spool-dir", default=str(DEFAULT_SPOOL_DIR))

    seed_demo = subcommands.add_parser(
        "seed-demo", help="Explicitly install the curated demo project."
    )
    seed_demo.add_argument("--db", default=str(DEFAULT_DB_PATH))
    seed_demo.add_argument("--sandbox-root", default=str(DEFAULT_SANDBOX_ROOT))

    extract = subcommands.add_parser(
        "extract",
        help="Extract worklist topics from a real repository (deterministic; no checks).",
    )
    extract.add_argument("--db", default=str(DEFAULT_DB_PATH))
    extract.add_argument("--sandbox-root", default=str(DEFAULT_SANDBOX_ROOT))
    extract.add_argument("--repo", required=True, help="Path to the repository to extract from.")

    curate = subcommands.add_parser(
        "curate-hero",
        help="Install the curated, validated repo-derived tenant-isolation check.",
    )
    curate.add_argument("--db", default=str(DEFAULT_DB_PATH))
    curate.add_argument("--sandbox-root", default=str(DEFAULT_SANDBOX_ROOT))
    curate.add_argument("--repo", required=True, help="Path to the repository to curate against.")

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
    if args.command == "seed-demo":
        repo = LedgerRepository(db_path=Path(args.db), sandbox_root=Path(args.sandbox_root))
        project = repo.seed_demo()
        print(f"Seeded demo project '{project['slug']}' at {args.db}")
        return 0
    if args.command == "extract":
        repo = LedgerRepository(db_path=Path(args.db), sandbox_root=Path(args.sandbox_root))
        repo.initialize()
        result = repo.extract_or_refresh_topics(args.repo)
        print(
            f"Discovered {result['surfaced']} verified worklist topic(s) for "
            f"'{result['project']['slug']}' via the {result['analysis_source']} analyst "
            f"(from {result['considered']} candidate anchor(s); "
            f"{result['rejected']} citation(s) rejected). Topics are candidates — none is "
            f"checkable until a curated recipe is installed."
        )
        return 0
    if args.command == "curate-hero":
        repo = LedgerRepository(db_path=Path(args.db), sandbox_root=Path(args.sandbox_root))
        repo.initialize()
        try:
            result = repo.install_repo_check_recipe(args.repo)
        except RecipeValidationError as exc:
            print(f"Refused to install check: {exc}")
            return 1
        v = result["validation"]
        print(
            f"Installed curated check for '{result['topic_id']}' pinned at "
            f"{result['revision_sha'][:12]} "
            f"(baseline green={v['baseline_passed']}, mutant red={v['mutant_failed']}, "
            f"targeted test red={v['target_test_failed']})."
        )
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

"""ManhwaManiacs backend command-line interface."""

from __future__ import annotations

import argparse
import logging

logger = logging.getLogger(__name__)


def migrate_orphan_series() -> int:
    """Remove chapter folders that were incorrectly imported as standalone series."""
    from database.session import SessionLocal, init_db
    from services.import_cleanup import ImportCleanupService

    init_db()
    db = SessionLocal()
    try:
        removed = ImportCleanupService(db).merge_all_orphans_global()
        db.commit()
        return removed
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="manhwamaniacs",
        description="ManhwaManiacs backend utilities",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    migrate = subparsers.add_parser(
        "migrate-orphans",
        help="Merge and remove chapter folders imported as standalone series",
    )
    migrate.set_defaults(handler="migrate-orphans")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.handler == "migrate-orphans":
        removed = migrate_orphan_series()
        logger.info("Removed %d orphan series.", removed)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""One-time cleanup script: remove non-US jobs from the database.

Re-runs the fixed is_us_location() filter against all jobs in the DB.
Jobs that fail the US location gate are deleted.

Usage:
    python -m src.pipeline.1_discovery.clean_non_us_jobs
    python -m src.pipeline.1_discovery.clean_non_us_jobs --dry-run
"""

import argparse
import importlib
import logging
import sqlite3
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

_scanner_mod = importlib.import_module("src.pipeline.1_discovery.scanner")
JobScanner = _scanner_mod.JobScanner

log = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean non-US jobs from database")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without actually deleting")
    parser.add_argument("--db", default="data/careergraph.db", help="Path to SQLite database")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    db_path = Path(args.db)
    if not db_path.exists():
        log.error("Database not found: %s", db_path)
        sys.exit(1)

    scanner = JobScanner()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Get total count
    cursor.execute("SELECT COUNT(*) FROM jobs")
    total = cursor.fetchone()[0]
    log.info("Total jobs in DB: %d", total)

    # Get all jobs with locations
    cursor.execute("SELECT id, location FROM jobs")
    rows = cursor.fetchall()

    to_delete = []
    for job_id, location in rows:
        if not scanner.is_us_location(location):
            to_delete.append((job_id, location))

    log.info("Non-US jobs to remove: %d / %d", len(to_delete), total)

    if to_delete:
        # Show sample
        log.info("Sample non-US locations being removed:")
        seen_locs = set()
        for _, loc in to_delete[:100]:
            if loc and loc not in seen_locs and len(seen_locs) < 20:
                seen_locs.add(loc)
                log.info("  - %s", loc)

    if args.dry_run:
        log.info("[DRY RUN] Would delete %d jobs. Re-run without --dry-run to execute.", len(to_delete))
    else:
        if to_delete:
            ids_to_delete = [row[0] for row in to_delete]
            # Batch delete in chunks of 1000
            for i in range(0, len(ids_to_delete), 1000):
                chunk = ids_to_delete[i:i+1000]
                placeholders = ",".join("?" for _ in chunk)
                cursor.execute(f"DELETE FROM jobs WHERE id IN ({placeholders})", chunk)
            conn.commit()
            log.info("Deleted %d non-US jobs from database.", len(to_delete))

            # Verify
            cursor.execute("SELECT COUNT(*) FROM jobs")
            remaining = cursor.fetchone()[0]
            log.info("Remaining jobs: %d", remaining)
        else:
            log.info("No non-US jobs found. Database is clean.")

    conn.close()


if __name__ == "__main__":
    main()

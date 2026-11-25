"""Mark saved briefings as public samples for the demo (Phase 6, D39 §2).

Sample briefings (`briefings.is_sample = true`) are what visitors without the access code see. Briefings are
immutable; `is_sample` is the only column the trigger lets change. Uses the service key.

Run from the backend folder:
    python mark_sample.py --list                 # current samples + the latest briefings with their IDs
    python mark_sample.py <briefing_id>          # mark as sample
    python mark_sample.py <briefing_id> --off    # unmark
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.config import ConfigError  # noqa: E402

COLUMNS = "id, company, language, meeting_type, is_partial, is_sample, created_at"


def set_sample(db, briefing_id: str, on: bool = True) -> dict:
    """Returns the updated row. Raises LookupError if no briefing has this ID."""
    rows = db.table("briefings").update({"is_sample": on}).eq("id", briefing_id).execute().data
    if not rows:
        raise LookupError(f"no briefing with id {briefing_id}")
    return rows[0]


def list_briefings(db, limit: int = 15) -> list[dict]:
    return db.table("briefings").select(COLUMNS).order("created_at", desc=True).limit(limit).execute().data


def line(row: dict) -> str:
    mark = "SAMPLE " if row.get("is_sample") else "       "
    partial = " (partial)" if row.get("is_partial") else ""
    return (f"{mark}{row['id']}  {str(row.get('created_at', ''))[:16]}  {row.get('company')} · "
            f"{str(row.get('language', '')).upper()} · {row.get('meeting_type')}{partial}")


def main(argv: list[str] | None = None, db=None) -> int:
    ap = argparse.ArgumentParser(description="Mark / unmark demo sample briefings")
    ap.add_argument("briefing_id", nargs="?")
    ap.add_argument("--off", action="store_true", help="unmark instead of mark")
    ap.add_argument("--list", action="store_true", help="list the latest briefings")
    args = ap.parse_args(argv)
    if not args.list and not args.briefing_id:
        ap.error("give a briefing ID or --list")
    try:
        if db is None:
            from app.db.clients import get_admin_client
            db = get_admin_client()
        if args.briefing_id:
            row = set_sample(db, args.briefing_id, on=not args.off)
            print(("marked: " if not args.off else "unmarked: ") + line(row))
        if args.list:
            for row in list_briefings(db):
                print(line(row))
    except LookupError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

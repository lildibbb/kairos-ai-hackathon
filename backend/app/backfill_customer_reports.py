"""Repair staff links for historical assigned customer reports."""

import argparse
import json

from sqlalchemy.orm import Session

from app.db.engine import get_engine
from app.services.customer_dispatch import backfill_report_tickets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Commit the repaired ticket links.")
    args = parser.parse_args()
    with Session(get_engine()) as session:
        counts = backfill_report_tickets(session)
        if args.apply:
            session.commit()
        else:
            session.rollback()
    print(json.dumps({**counts, "applied": args.apply}))


if __name__ == "__main__":
    main()

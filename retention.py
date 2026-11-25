"""Deletes accounts that have been inactive for too long (storage limitation).
    python retention.py                 shows which accounts would be deleted
    python retention.py --apply         really deletes them
    python retention.py --days 90       use a different limit than INACTIVITY_DAYS"""
import argparse
import datetime as dt
import config
import db


def inactive_accounts(con, days, today=None):
    """Accounts whose latest activity (account creation or newest entry date) is older than `days`."""
    today = today or dt.date.today()
    cutoff = (today - dt.timedelta(days=days)).isoformat()
    rows = con.execute("SELECT s.student_id, s.username, substr(s.created_at, 1, 10) AS created, "
                       "MAX(d.entry_date) AS last_entry FROM students s "
                       "LEFT JOIN daily_entries d ON d.student_id = s.student_id GROUP BY s.student_id").fetchall()
    out = []
    for r in rows:
        last = max(r["created"], r["last_entry"] or "")
        if last < cutoff:
            out.append((r["student_id"], r["username"], last))
    return out


def purge_inactive(con, days, apply=False, today=None):
    found = inactive_accounts(con, days, today)
    if apply:
        for sid, _, _ in found:
            db.delete_student(con, sid)
    return found


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=config.INACTIVITY_DAYS)
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()
    con = db.connect()
    db.init_db(con)
    found = purge_inactive(con, args.days, apply=args.apply)
    for _, user, last in found:
        print(f"{'Deleted' if args.apply else 'Would delete'}: {user} (last activity {last})")
    print(f"{len(found)} inactive account(s) older than {args.days} days.")

"""Data protection tests: consent, access, erasure, storage limitation, notice."""
import datetime as dt
import json
import config
import db
import privacy
import retention
from helpers import make_student


def test_consent_is_recorded_at_registration(con, sid):
    row = db.get_student_by_username(con, "asha_1")
    assert row["consent_version"] == config.CONSENT_VERSION and row["consent_at"]


def test_old_accounts_can_give_consent_later(con, sid):
    con.execute("UPDATE students SET consent_at=NULL, consent_version=NULL")
    con.commit()
    db.record_consent(con, sid, config.CONSENT_VERSION)
    assert db.get_student_by_username(con, "asha_1")["consent_version"] == config.CONSENT_VERSION


def test_export_contains_only_the_students_own_data(con):
    a, b = make_student(con, "asha_1"), make_student(con, "ravi")
    db.upsert_daily(con, a, "2026-10-01", dict(sleep_hours=5, study_hours=1, mood=4, screen_time=9))
    db.upsert_daily(con, b, "2026-10-01", dict(sleep_hours=8, study_hours=4, mood=9, screen_time=2))
    db.save_attendance_table(con, a, [("Maths", 60)])
    out = db.export_student_data(con, a)
    assert out["profile"]["username"] == "asha_1"
    assert len(out["daily_entries"]) == 1 and out["daily_entries"][0]["sleep_hours"] == 5
    assert out["attendance"][0]["subject"] == "Maths"
    text = json.dumps(out, default=str)
    assert "ravi" not in text


def test_export_never_contains_password_data(con, sid):
    row = db.get_student_by_username(con, "asha_1")
    text = json.dumps(db.export_student_data(con, sid), default=str)
    assert row["pw_hash"] not in text and row["salt"] not in text and "pw_hash" not in text


def test_export_handles_missing_values(con, sid):
    db.upsert_daily(con, sid, "2026-10-01", dict(sleep_hours=5))     # other fields stay empty
    json.dumps(db.export_student_data(con, sid), default=str, allow_nan=False)   # must be valid JSON


def test_erasure_leaves_nothing_behind(con, sid):
    db.upsert_daily(con, sid, "2026-10-01", dict(sleep_hours=5))
    db.delete_student(con, sid)
    assert db.export_student_data(con, sid) == {}
    assert con.execute("SELECT COUNT(*) FROM daily_entries").fetchone()[0] == 0


def test_inactive_accounts_are_found_and_deleted(con):
    old, active = make_student(con, "old_user"), make_student(con, "active_user")
    con.execute("UPDATE students SET created_at='2025-01-01T00:00:00' WHERE student_id=?", (old,))
    con.commit()
    today = dt.date(2026, 11, 8)
    db.upsert_daily(con, active, "2026-11-01", dict(sleep_hours=7))
    assert [u for _, u, _ in retention.purge_inactive(con, 180, apply=False, today=today)] == ["old_user"]
    assert con.execute("SELECT COUNT(*) FROM students").fetchone()[0] == 2        # dry run deletes nothing
    retention.purge_inactive(con, 180, apply=True, today=today)
    assert [r["username"] for r in con.execute("SELECT username FROM students")] == ["active_user"]


def test_a_new_account_with_old_dated_entries_is_not_purged(con, sid):
    db.upsert_daily(con, sid, "2020-01-01", dict(sleep_hours=7))     # a past day entered today
    assert retention.inactive_accounts(con, 180) == []


def test_notice_covers_the_required_points():
    text = privacy.notice_markdown().lower()
    for word in ("what we collect", "why", "how long", "delete", "download", "18", config.PRIVACY_CONTACT.lower()):
        assert word in text

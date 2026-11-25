"""Unit tests: database functions."""
import datetime as dt
import pytest
import config
import db
from helpers import make_student


def test_upsert_updates_the_same_day(con, sid):
    db.upsert_daily(con, sid, "2026-10-01", dict(sleep_hours=6, study_hours=2, mood=5, screen_time=4))
    db.upsert_daily(con, sid, "2026-10-01", dict(sleep_hours=8, study_hours=2, mood=5, screen_time=4))
    d = db.get_daily(con, sid)
    assert len(d) == 1 and d.sleep_hours[0] == 8


@pytest.mark.parametrize("field,given,expected", [
    ("sleep_hours", 99, 24), ("sleep_hours", -5, 0), ("mood", 15, 10), ("mood", -3, 1), ("screen_time", 30, 24)])
def test_values_are_clipped_to_valid_range(con, sid, field, given, expected):
    db.upsert_daily(con, sid, "2026-10-01", {field: given})
    assert db.get_daily(con, sid)[field][0] == expected


def test_unknown_field_is_rejected(con, sid):
    with pytest.raises(ValueError, match="Unknown field"):
        db.upsert_daily(con, sid, "2026-10-01", {"evil; DROP TABLE students": 1})


def test_empty_history_is_an_empty_table(con, sid):
    d = db.get_daily(con, sid)
    assert d.empty and "sleep_hours" in d.columns


def test_a_new_daily_field_needs_only_a_config_entry(con, sid):
    config.DAILY_FIELDS.append(dict(name="exercise_minutes", label="Exercise", min=0.0, max=300.0,
                                    default=20.0, step=5.0))
    try:
        db.init_db(con)
        db.upsert_daily(con, sid, "2026-10-03", dict(sleep_hours=7, exercise_minutes=30))
        assert db.get_daily(con, sid)["exercise_minutes"][0] == 30
    finally:
        config.DAILY_FIELDS.pop()


def good_row(day, **kw):
    r = dict(date=day, sleep_hours=7, study_hours=3, mood=7, screen_time=4)
    r.update(kw)
    return r


def test_save_several_days_at_once(con, sid):
    rows = [good_row("2026-09-01"), good_row("2026-09-02"), dict(date=None, sleep_hours=None)]
    assert db.save_daily_rows(con, sid, rows) == (2, [])
    assert len(db.get_daily(con, sid)) == 2
    assert db.save_daily_rows(con, sid, [good_row("2026-09-01", sleep_hours=9)]) == (1, [])
    assert len(db.get_daily(con, sid)) == 2          # updated, not duplicated


@pytest.mark.parametrize("bad", [
    good_row("2999-01-01"),                 # future
    good_row("not a date"),
    dict(date="2026-09-03", sleep_hours=7),  # missing columns
])
def test_invalid_days_save_nothing(con, sid, bad):
    count, problems = db.save_daily_rows(con, sid, [good_row("2026-09-05"), bad])
    assert count == 0 and problems
    assert db.get_daily(con, sid).empty


def test_attendance_table_adds_updates_and_removes(con, sid):
    db.save_attendance_table(con, sid, [("Maths", 80), ("Python", 90), ("Physics", 70), ("", 50), ("Bad", None)])
    assert sorted(db.get_attendance(con, sid).subject) == ["Maths", "Physics", "Python"]
    db.save_attendance_table(con, sid, [("Maths", 85), ("Chemistry", 120)])
    got = db.get_attendance(con, sid).set_index("subject").attendance_pct.to_dict()
    assert got == {"Maths": 85.0, "Chemistry": 100.0}      # 120 is capped at 100
    db.save_attendance_table(con, sid, [])
    assert db.get_attendance(con, sid).empty


def test_marks_allow_two_tests_on_one_day_and_none_at_all(con, sid):
    rows = [("Maths", "Quiz 1", 8, 10, "2026-10-01"), ("Maths", "Quiz 2", 9, 10, "2026-10-01"),
            ("Python", "Lab", 15, 20, None), (None, None, None, None, None)]
    assert db.save_marks_table(con, sid, rows) == []
    assert len(db.get_marks(con, sid)) == 3
    assert db.save_marks_table(con, sid, []) == [] and db.get_marks(con, sid).empty


@pytest.mark.parametrize("row", [
    ("Maths", "Q", 12, 10, "2026-10-01"),    # obtained above total
    ("Maths", "Q", -1, 10, "2026-10-01"),
    ("Maths", "Q", 5, 0, "2026-10-01"),      # total zero
    ("", "Q", 5, 10, None),                  # missing subject
])
def test_invalid_marks_save_nothing(con, sid, row):
    db.save_marks_table(con, sid, [("Python", "Lab", 15, 20, None)])
    assert db.save_marks_table(con, sid, [row])
    assert len(db.get_marks(con, sid)) == 1          # the earlier valid data is untouched


def test_deadlines_done_flag_delete_and_bad_date(con, sid):
    rows = [("A", "Maths", "2026-10-20", False), ("B", "", "2026-10-25", True), ("", None, None, None)]
    assert db.save_deadlines_table(con, sid, rows) == []
    assert len(db.get_deadlines(con, sid, only_open=False)) == 2
    assert len(db.get_deadlines(con, sid)) == 1       # only the open one
    assert db.save_deadlines_table(con, sid, [("A", "", "not a date", False)])
    assert len(db.get_deadlines(con, sid, only_open=False)) == 2
    assert db.save_deadlines_table(con, sid, [("A", "Maths", "2026-10-20", False)]) == []
    assert len(db.get_deadlines(con, sid, only_open=False)) == 1


def test_text_with_sql_in_it_is_stored_as_plain_text(con, sid):
    nasty = "Maths'); DROP TABLE students;--"
    db.save_attendance_table(con, sid, [(nasty, 80)])
    db.save_marks_table(con, sid, [(nasty, nasty, 5, 10, None)])
    assert con.execute("SELECT COUNT(*) FROM students").fetchone()[0] == 1
    assert db.get_attendance(con, sid).subject[0] == nasty


def test_each_student_only_sees_their_own_rows(con):
    a, b = make_student(con, "asha_1"), make_student(con, "ravi")
    db.upsert_daily(con, a, "2026-10-01", dict(sleep_hours=5))
    db.save_attendance_table(con, a, [("Maths", 60)])
    db.save_marks_table(con, a, [("Maths", "Q1", 5, 10, None)])
    assert db.get_daily(con, b).empty and db.get_attendance(con, b).empty and db.get_marks(con, b).empty
    assert len(db.get_daily(con, a)) == 1


def test_deleting_a_student_removes_all_their_data(con):
    a, b = make_student(con, "asha_1"), make_student(con, "ravi")
    for s in (a, b):
        db.upsert_daily(con, s, "2026-10-01", dict(sleep_hours=5))
        db.save_attendance_table(con, s, [("Maths", 60)])
        db.save_marks_table(con, s, [("Maths", "Q1", 5, 10, None)])
        db.save_deadlines_table(con, s, [("A", "", "2026-10-20", False)])
        db.save_rec_feedback(con, s, "low_sleep", True)
        db.save_feedback(con, s, 4, 4, "ok")
    db.delete_student(con, a)
    for table in ("daily_entries", "attendance", "marks", "deadlines", "rec_feedback", "feedback"):
        assert con.execute(f"SELECT COUNT(*) FROM {table} WHERE student_id=?", (a,)).fetchone()[0] == 0
        assert con.execute(f"SELECT COUNT(*) FROM {table} WHERE student_id=?", (b,)).fetchone()[0] == 1


def test_indexes_exist_for_per_student_lookups(con):
    names = {r["name"] for r in con.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert {"idx_marks_student", "idx_deadlines_student"} <= names


def test_wal_mode_is_on(con):
    assert con.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"

"""Unit tests: every tip rule, including values exactly on the limit."""
import datetime as dt
import pandas as pd
import pytest
import recommend

TODAY = dt.date(2026, 11, 8)
NO_ATT = pd.DataFrame(columns=["subject", "attendance_pct"])
NO_MARKS = pd.DataFrame(columns=["subject", "test_name", "obtained", "total", "test_date"])
NO_DL = pd.DataFrame(columns=["deadline_id", "title", "subject", "due_date", "done"])


def frame(n=7, **cols):
    base = dict(sleep_hours=7.5, study_hours=3.0, mood=7.0, screen_time=4.0)
    base.update(cols)
    d = pd.DataFrame({k: (v if isinstance(v, list) else [v] * n) for k, v in base.items()})
    d.insert(0, "date", pd.date_range("2026-10-01", periods=n))
    return d


def codes(daily=None, att=NO_ATT, marks=NO_MARKS, dl=NO_DL):
    daily = frame() if daily is None else daily
    return [r["code"] for r in recommend.generate(daily, att, marks, dl, TODAY)]


@pytest.mark.parametrize("sleep,expected", [(6.4, True), (6.5, False), (8.0, False)])
def test_low_sleep_boundary(sleep, expected):
    assert ("low_sleep" in codes(frame(sleep_hours=sleep))) == expected


@pytest.mark.parametrize("screen,expected", [(7.1, True), (7.0, False), (3.0, False)])
def test_high_screen_boundary(screen, expected):
    assert ("high_screen" in codes(frame(screen_time=screen))) == expected


@pytest.mark.parametrize("study,expected", [(1.9, True), (2.0, False), (4.0, False)])
def test_low_study_boundary(study, expected):
    assert ("low_study" in codes(frame(study_hours=study))) == expected


def test_habit_tips_need_at_least_three_entries():
    assert "low_sleep" not in codes(frame(n=2, sleep_hours=4.0))
    assert "low_sleep" in codes(frame(n=3, sleep_hours=4.0))


@pytest.mark.parametrize("last3,expected", [
    ([6.0, 6.0, 6.0], True),      # drop of 2.0
    ([6.5, 6.5, 6.5], True),      # drop of exactly 1.5
    ([7.0, 7.0, 7.0], False),     # drop of 1.0
])
def test_mood_drop_boundary(last3, expected):
    daily = frame(mood=[8.0, 8.0, 8.0, 8.0] + last3)
    assert ("mood_drop" in codes(daily)) == expected


def test_sleep_and_mood_link_needs_14_days_and_correlation():
    rising = list(range(1, 15))
    assert "sleep_mood" in codes(frame(n=14, sleep_hours=[5 + x * 0.2 for x in rising], mood=[float(x) for x in rising]))
    assert "sleep_mood" not in codes(frame(n=13, sleep_hours=[5 + x * 0.2 for x in rising[:13]], mood=[float(x) for x in rising[:13]]))
    assert "sleep_mood" not in codes(frame(n=14))     # constant columns: no correlation, and no crash


@pytest.mark.parametrize("pct,expected", [
    (74.9, ["attendance_maths"]), (75.0, ["attendance_maths_near"]), (79.9, ["attendance_maths_near"]), (80.0, [])])
def test_attendance_boundaries(pct, expected):
    att = pd.DataFrame(dict(subject=["Maths"], attendance_pct=[pct]))
    assert [c for c in codes(att=att) if c.startswith("attendance")] == expected


@pytest.mark.parametrize("obtained,expected", [(9, True), (10, False), (19, False)])
def test_weak_subject_boundary(obtained, expected):
    marks = pd.DataFrame(dict(subject=["Maths"], test_name=["Q"], obtained=[float(obtained)], total=[20.0], test_date=["2026-10-01"]))
    assert ("weak_maths" in codes(marks=marks)) == expected


@pytest.mark.parametrize("due,expected", [
    ("2026-11-07", "overdue_1"), ("2026-11-08", "due_1"), ("2026-11-11", "due_1"), ("2026-11-12", None)])
def test_deadline_windows(due, expected):
    dl = pd.DataFrame(dict(deadline_id=[1], title=["A"], subject=[""], due_date=[due], done=[0]))
    got = [c for c in codes(dl=dl) if c.startswith(("due_", "overdue_"))]
    assert got == ([expected] if expected else [])


def test_empty_data_gives_a_start_logging_tip():
    r = recommend.generate(pd.DataFrame(), None, None, None, TODAY)
    assert [x["code"] for x in r] == ["start_logging"]


def test_alerts_come_before_warnings_before_info():
    att = pd.DataFrame(dict(subject=["Maths"], attendance_pct=[50.0]))
    r = recommend.generate(frame(sleep_hours=5.0, study_hours=1.0), att, NO_MARKS, NO_DL, TODAY)
    order = [x["severity"] for x in r]
    assert order == sorted(order, key={"alert": 0, "warn": 1, "info": 2}.get)


def test_subject_names_with_odd_characters_make_safe_codes():
    att = pd.DataFrame(dict(subject=["Data Science & AI (Lab)"], attendance_pct=[40.0]))
    assert "attendance_data_science_ai_lab" in codes(att=att)

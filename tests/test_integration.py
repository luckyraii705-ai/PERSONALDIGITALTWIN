"""Integration tests: several modules working together, parallel users, and the real Streamlit screens."""
import json
import os
import tempfile
import threading
import pytest
import auth
import config
import db
import ml
import recommend
from helpers import make_student

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_full_student_journey(con):
    sid = make_student(con)
    student = auth.login(con, "asha_1", "password123")
    assert student["consent_version"] == config.CONSENT_VERSION
    rows = [dict(date=f"2026-10-{d:02d}", sleep_hours=5.5 + d % 3, study_hours=2 + d % 4,
                 mood=5 + d % 4, screen_time=6 + d % 3) for d in range(1, 31)]
    assert db.save_daily_rows(con, sid, rows) == (30, [])
    db.save_attendance_table(con, sid, [("Maths", 72), ("Python", 90)])
    db.save_marks_table(con, sid, [("Maths", "Quiz 1", 6, 20, "2026-10-10")])
    db.save_deadlines_table(con, sid, [("Assignment", "Maths", "2026-10-31", False)])

    daily = db.get_daily(con, sid)
    tips = recommend.generate(daily, db.get_attendance(con, sid), db.get_marks(con, sid), db.get_deadlines(con, sid))
    assert {"attendance_maths", "weak_maths"} <= {t["code"] for t in tips}
    assert ml.cluster_profile(daily)["k"] == 3
    assert "mean_rmse" in ml.compare_baselines(daily)
    db.save_rec_feedback(con, sid, "attendance_maths", True)
    json.dumps(db.export_student_data(con, sid), default=str)
    db.delete_student(con, sid)
    assert auth.login(con, "asha_1", "password123") is None


def test_twenty_students_at_the_same_time_with_their_own_connections():
    folder = tempfile.mkdtemp()
    path = os.path.join(folder, "parallel.db")
    setup = db.connect(path)
    db.init_db(setup)
    errors = []

    def one_student(i):
        try:
            c = db.connect(path)
            s = auth.register(c, f"user_{i}", f"User {i}", "AI", 1, "password123", consent=True, confirmed_adult=True)
            for d in range(1, 11):
                db.upsert_daily(c, s, f"2026-10-{d:02d}", dict(sleep_hours=7, study_hours=3, mood=7, screen_time=4))
            c.close()
        except Exception as e:   # any failure is a test failure
            errors.append(repr(e))

    threads = [threading.Thread(target=one_student, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert setup.execute("SELECT COUNT(*) FROM students").fetchone()[0] == 20
    assert setup.execute("SELECT COUNT(*) FROM daily_entries").fetchone()[0] == 200
    setup.close()


# ---- the real app, run without a browser (needs streamlit installed) ----
@pytest.fixture
def app_db():
    st = pytest.importorskip("streamlit")
    pytest.importorskip("streamlit.testing.v1")
    folder = tempfile.mkdtemp()
    path = os.path.join(folder, "app.db")
    old = config.DB_PATH
    config.DB_PATH = path
    st.cache_resource.clear()
    c = db.connect(path)
    db.init_db(c)
    yield c
    c.close()
    config.DB_PATH = old
    st.cache_resource.clear()


def run_app(student=None):
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=60)
    if student:
        at.session_state["student"] = student
    return at.run()


def test_app_shows_login_and_register_when_logged_out(app_db):
    at = run_app()
    assert not at.exception
    assert len(at.tabs) == 2


def test_app_shows_all_six_tabs_to_a_student_who_agreed(app_db):
    sid = make_student(app_db)
    at = run_app(auth.login(app_db, "asha_1", "password123"))
    assert not at.exception
    assert len(at.tabs) == 6


def test_app_blocks_a_student_who_has_not_agreed_to_the_privacy_notice(app_db):
    sid = make_student(app_db)
    app_db.execute("UPDATE students SET consent_at=NULL, consent_version=NULL")
    app_db.commit()
    at = run_app(auth.login(app_db, "asha_1", "password123"))
    assert not at.exception
    assert len(at.tabs) == 0
    assert any("Privacy notice" in s.value for s in at.subheader)

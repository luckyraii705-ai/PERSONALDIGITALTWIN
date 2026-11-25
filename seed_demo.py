"""Creates 5 DEMO students (usernames demo_1..demo_5, password demo12345) with 35 days of fake data,
so you can try the app and take screenshots. Remove them BEFORE the real pilot:
    python seed_demo.py            add demo students
    python seed_demo.py --remove   delete them again"""
import datetime as dt
import sys
import numpy as np
import auth
import db


def seed(con, days=35):
    rng = np.random.default_rng(7)
    today = dt.date.today()
    for i in range(1, 6):
        user = f"demo_{i}"
        if db.get_student_by_username(con, user):
            continue
        sid = auth.register(con, user, f"Demo Student {i}", "AI and Data Science", 1, "demo12345",
                            consent=True, confirmed_adult=True)
        for d in range(days, 0, -1):
            sleep = float(np.clip(rng.normal(6.4 + 0.2 * i, 1.0), 4, 9))
            study = float(np.clip(rng.normal(3, 1.3), 0, 8))
            screen = float(np.clip(rng.normal(5.5, 1.8), 1, 11))
            mood = float(np.clip(3.5 + 0.55 * sleep - 0.12 * screen + rng.normal(0, 0.8), 1, 10))
            db.upsert_daily(con, sid, today - dt.timedelta(days=d),
                            dict(sleep_hours=round(sleep, 1), study_hours=round(study, 1),
                                 mood=round(mood), screen_time=round(screen, 1)))
        for subj, pct in [("Maths", 82 - 4 * i), ("Python", 90 - 3 * i), ("Physics", 70 + 2 * i)]:
            db.upsert_attendance(con, sid, subj, pct)
        for subj, ob in [("Maths", min(10 + 2 * i, 20)), ("Python", 18), ("Physics", 9 + 2 * i)]:
            db.add_mark(con, sid, subj, "Quiz 1", ob, 20, today - dt.timedelta(days=10))
        db.add_deadline(con, sid, "Assignment 2", "Maths", today + dt.timedelta(days=2))
        db.add_deadline(con, sid, "Lab record", "Python", today + dt.timedelta(days=9))


def remove(con):
    for i in range(1, 6):
        row = db.get_student_by_username(con, f"demo_{i}")
        if row:
            db.delete_student(con, row["student_id"])


if __name__ == "__main__":
    con = db.connect()
    db.init_db(con)
    if "--remove" in sys.argv:
        remove(con)
        print("Demo students removed.")
    else:
        seed(con)
        print("Demo students added. Log in as demo_1 with password demo12345.")

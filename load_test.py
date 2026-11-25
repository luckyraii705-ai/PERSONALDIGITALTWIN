"""Load test: many students use the app's back end at the same time.

    python load_test.py                          compare the two designs at 10 and 50 students
    python load_test.py --students 200           one run, a separate connection per student
    python load_test.py --students 50 --shared   one shared connection (how the app worked before Milestone 4)
    python load_test.py --students 50 --no-wal   without WAL mode

Each simulated student registers, logs in, saves 30 daily entries, adds attendance and marks, reads their
history, gets tips, gets day types and exports their data. The time of every action is recorded."""
import argparse
import csv
import datetime as dt
import os
import tempfile
import threading
import time

import numpy as np

import auth
import db
import ml
import recommend

ACTIONS = ["register", "login", "save_entry", "save_tables", "read_history", "tips", "day_types", "export"]


def one_student(i, make_con, timings, errors, lock, barrier, days=30):
    rng = np.random.default_rng(i)
    con = make_con()

    def timed(name, fn):
        start = time.perf_counter()
        try:
            out = fn()
        except Exception as e:  # a failed action is counted, not hidden
            with lock:
                errors.append((name, repr(e)[:90]))
            return None
        with lock:
            timings[name].append((time.perf_counter() - start) * 1000)
        return out

    barrier.wait()  # every student starts at the same moment
    sid = timed("register", lambda: auth.register(con, f"load_{i}", f"Load {i}", "AI", 1, "password123",
                                                  consent=True, confirmed_adult=True))
    if sid is None:
        return
    timed("login", lambda: auth.login(con, f"load_{i}", "password123"))
    today = dt.date.today()
    for d in range(days, 0, -1):
        values = dict(sleep_hours=float(np.clip(rng.normal(7, 1), 4, 9)), study_hours=float(rng.uniform(0, 6)),
                      mood=float(rng.integers(3, 10)), screen_time=float(rng.uniform(2, 9)))
        timed("save_entry", lambda d=d, v=values: db.upsert_daily(con, sid, today - dt.timedelta(days=d), v))
    timed("save_tables", lambda: (
        db.save_attendance_table(con, sid, [("Maths", 80), ("Python", 90), ("Physics", 70)]),
        db.save_marks_table(con, sid, [("Maths", "Quiz 1", 12, 20, None), ("Python", "Quiz 1", 18, 20, None)])))
    daily = timed("read_history", lambda: db.get_daily(con, sid))
    if daily is None:
        return
    timed("tips", lambda: recommend.generate(daily, db.get_attendance(con, sid), db.get_marks(con, sid),
                                              db.get_deadlines(con, sid)))
    timed("day_types", lambda: ml.cluster_profile(daily))
    timed("export", lambda: db.export_student_data(con, sid))


def run(students, shared=False, wal=True):
    folder = tempfile.mkdtemp()
    path = os.path.join(folder, "load.db")
    first = db.connect(path, wal=wal)
    db.init_db(first)
    make_con = (lambda: first) if shared else (lambda: db.connect(path, wal=wal))
    timings = {a: [] for a in ACTIONS}
    errors, lock, barrier = [], threading.Lock(), threading.Barrier(students)
    threads = [threading.Thread(target=one_student, args=(i, make_con, timings, errors, lock, barrier))
               for i in range(students)]
    start = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    total = time.perf_counter() - start
    done = sum(len(v) for v in timings.values())
    saved = first.execute("SELECT COUNT(*) FROM daily_entries").fetchone()[0]
    return dict(students=students, shared=shared, wal=wal, total_s=total, actions=done,
                actions_per_s=done / total, errors=errors, timings=timings, entries_saved=saved)


def pct(values, p):
    return float(np.percentile(values, p)) if values else float("nan")


def show(r):
    mode = ("one shared connection" if r["shared"] else "connection per student") + (", WAL" if r["wal"] else ", no WAL")
    print(f"\n=== {r['students']} students at once | {mode} ===")
    print(f"total time {r['total_s']:.1f} s | {r['actions']} actions | {r['actions_per_s']:.0f} actions/s | "
          f"errors {len(r['errors'])} | entries saved {r['entries_saved']} of {r['students'] * 30}")
    print(f"{'action':<14}{'count':>7}{'p50 ms':>10}{'p95 ms':>10}{'max ms':>10}")
    for a in ACTIONS:
        v = r["timings"][a]
        print(f"{a:<14}{len(v):>7}{pct(v, 50):>10.1f}{pct(v, 95):>10.1f}{(max(v) if v else float('nan')):>10.1f}")
    if r["errors"]:
        kinds = {}
        for name, msg in r["errors"]:
            kinds[(name, msg)] = kinds.get((name, msg), 0) + 1
        print("errors:")
        for (name, msg), n in list(kinds.items())[:5]:
            print(f"  {n} x {name}: {msg}")


def save_csv(results, path="load_test_results.csv"):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["students", "design", "total_s", "actions_per_s", "errors", "entries_saved",
                    "save_entry_p50_ms", "save_entry_p95_ms", "tips_p95_ms", "day_types_p95_ms"])
        for r in results:
            t = r["timings"]
            w.writerow([r["students"], ("shared" if r["shared"] else "per_student") + ("" if r["wal"] else "_nowal"),
                        round(r["total_s"], 2), round(r["actions_per_s"]), len(r["errors"]), r["entries_saved"],
                        round(pct(t["save_entry"], 50), 1), round(pct(t["save_entry"], 95), 1),
                        round(pct(t["tips"], 95), 1), round(pct(t["day_types"], 95), 1)])
    print(f"\nResults saved to {path}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--students", type=int)
    p.add_argument("--shared", action="store_true")
    p.add_argument("--no-wal", action="store_true")
    a = p.parse_args()
    results = []
    if a.students:
        results.append(run(a.students, shared=a.shared, wal=not a.no_wal))
    else:
        for n in (10, 50):
            results.append(run(n, shared=True, wal=False))    # the old design
            results.append(run(n, shared=False, wal=True))    # the new design
    for r in results:
        show(r)
    save_csv(results)

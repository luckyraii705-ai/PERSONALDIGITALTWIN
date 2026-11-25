"""Measures how long the main actions take and shows the effect of each optimization.
    python benchmark.py
Results are printed and saved to benchmark_results.csv. The LSTM rows appear only if TensorFlow is installed."""
import csv
import os
import statistics
import tempfile
import time

import numpy as np

import config
import db
import ml
import recommend
import seed_demo


def timeit(fn, repeat=5):
    """Average and worst time in milliseconds over several runs."""
    times = []
    for _ in range(repeat):
        t = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t) * 1000)
    return statistics.mean(times), max(times)


rows = []


def record(group, name, ms, worst=None, note=""):
    rows.append([group, name, round(ms, 2), round(worst, 2) if worst is not None else "", note])
    print(f"{group:<16}{name:<44}{ms:>10.2f} ms  {note}")


def main():
    folder = tempfile.mkdtemp()
    con = db.connect(os.path.join(folder, "bench.db"))
    db.init_db(con)
    seed_demo.seed(con, days=60)
    sid = db.get_student_by_username(con, "demo_1")["student_id"]
    daily = db.get_daily(con, sid)
    print(f"Data: one student with {len(daily)} days of entries\n")

    # 1. everyday actions
    m, w = timeit(lambda: db.get_daily(con, sid), 20); record("everyday", "read history", m, w)
    att, marks, dl = db.get_attendance(con, sid), db.get_marks(con, sid), db.get_deadlines(con, sid)
    m, w = timeit(lambda: recommend.generate(daily, att, marks, dl), 20); record("everyday", "generate tips", m, w)
    m, w = timeit(lambda: db.export_student_data(con, sid), 10); record("everyday", "export my data", m, w)
    m, w = timeit(lambda: ml.compare_baselines(daily), 5); record("everyday", "compare baselines", m, w)

    # 2. clustering: fewer restarts
    slow, sw = timeit(lambda: ml.cluster_profile(daily, n_init=10), 5)
    fast, fw = timeit(lambda: ml.cluster_profile(daily, n_init=config.KMEANS_N_INIT), 5)
    s10 = ml.cluster_profile(daily, n_init=10)["silhouette"]
    s3 = ml.cluster_profile(daily, n_init=config.KMEANS_N_INIT)["silhouette"]
    record("optimization", "day types, 10 restarts (before)", slow, sw, f"silhouette {s10:.3f}")
    record("optimization", f"day types, {config.KMEANS_N_INIT} restarts (after)", fast, fw,
           f"silhouette {s3:.3f}, {slow / fast:.1f}x faster")

    # 3. database index
    path = os.path.join(folder, "index.db")
    big = db.connect(path)
    db.init_db(big)
    ids = []
    with big:
        for i in range(3000):
            cur = big.execute("INSERT INTO students (username, name, pw_hash, salt, created_at) VALUES (?,?,?,?,?)",
                              (f"u{i}", "U", "h", "s", "2026-01-01T00:00:00"))
            ids.append(cur.lastrowid)
        big.executemany("INSERT INTO marks (student_id, subject, test_name, obtained, total, test_date) "
                        "VALUES (?,?,?,?,?,?)", [(s, "Maths", f"Q{k}", 5, 10, "2026-10-01") for s in ids for k in range(5)])
    rng = np.random.default_rng(1)
    picks = rng.choice(ids, 300)

    def lookups():
        for s in picks:
            db.get_marks(big, int(s))
    with_idx, _ = timeit(lookups, 3)
    big.execute("DROP INDEX idx_marks_student"); big.commit()
    without_idx, _ = timeit(lookups, 3)
    record("optimization", "300 marks lookups, 15000 rows, no index (before)", without_idx)
    record("optimization", "300 marks lookups, 15000 rows, with index (after)", with_idx,
           note=f"{without_idx / with_idx:.1f}x faster")

    # 4. prediction model
    try:
        import tensorflow  # noqa: F401
    except ImportError:
        print("\nTensorFlow is not installed, so the LSTM timings are skipped.")
    else:
        t = time.perf_counter()
        r = ml.train_lstm(daily, epochs=60)
        total = (time.perf_counter() - t) * 1000
        record("model", "LSTM: first click (train + predict)", total, note=f"train {r['train_seconds']:.1f} s")
        record("optimization", "next-day prediction with model.predict (before)", r["predict_api_ms"])
        record("optimization", "next-day prediction with a direct call (after)", r["inference_ms"],
               note=f"{r['predict_api_ms'] / max(r['inference_ms'], 0.01):.1f}x faster")
        cache = {(sid, len(daily), str(daily['date'].iloc[-1].date())): r}
        m, _ = timeit(lambda: cache[(sid, len(daily), str(daily['date'].iloc[-1].date()))], 1000)
        record("optimization", "LSTM: repeat click, saved result (after)", m, note=f"was {total:.0f} ms each time")

    with open("benchmark_results.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["group", "action", "avg_ms", "worst_ms", "note"])
        w.writerows(rows)
    print("\nSaved benchmark_results.csv")


if __name__ == "__main__":
    main()

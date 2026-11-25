"""Pilot-test numbers for the Milestone 3 report.
    python pilot_report.py           usage + feedback summary
    python pilot_report.py --lstm    also checks the LSTM on students with 30+ days (needs TensorFlow)"""
import sys
import pandas as pd
import db
import ml


def summary(con):
    q = lambda sql: pd.read_sql_query(sql, con)
    out = {}
    out["students"] = int(q("SELECT COUNT(*) n FROM students WHERE username NOT LIKE 'demo\\_%' ESCAPE '\\'").n[0])
    per = q("SELECT s.username, COUNT(d.entry_date) days FROM students s LEFT JOIN daily_entries d "
            "ON d.student_id=s.student_id WHERE s.username NOT LIKE 'demo\\_%' ESCAPE '\\' GROUP BY s.student_id")
    out["entries_total"] = int(per["days"].sum()) if len(per) else 0
    out["avg_days_per_student"] = round(float(per["days"].mean()), 1) if len(per) else 0.0
    out["active_students_5plus_days"] = int((per["days"] >= 5).sum()) if len(per) else 0
    fb = q("SELECT ease, usefulness FROM feedback f JOIN students s ON s.student_id=f.student_id "
           "WHERE s.username NOT LIKE 'demo\\_%' ESCAPE '\\'")
    out["feedback_responses"] = len(fb)
    out["avg_ease_1to5"] = round(float(fb.ease.mean()), 2) if len(fb) else None
    out["avg_usefulness_1to5"] = round(float(fb.usefulness.mean()), 2) if len(fb) else None
    rf = q("SELECT rec_code, helpful FROM rec_feedback r JOIN students s ON s.student_id=r.student_id "
           "WHERE s.username NOT LIKE 'demo\\_%' ESCAPE '\\'")
    out["tip_ratings"] = len(rf)
    out["tips_helpful_pct"] = round(float(rf.helpful.mean() * 100), 1) if len(rf) else None
    if len(rf):
        rf["rule"] = rf["rec_code"].str.replace(r"_\d+$", "", regex=True)
        out["helpful_by_rule"] = (rf.groupby("rule")["helpful"].agg(["mean", "count"])
                                  .assign(mean=lambda d: (d["mean"] * 100).round(1)).rename(
                                      columns={"mean": "helpful_pct", "count": "ratings"}))
    return out


if __name__ == "__main__":
    con = db.connect()
    db.init_db(con)
    s = summary(con)
    by_rule = s.pop("helpful_by_rule", None)
    for k, v in s.items():
        print(f"{k}: {v}")
    if by_rule is not None:
        print("\nTips rated helpful, by rule (low % = refine that rule):\n", by_rule)
        by_rule.to_csv("pilot_helpful_by_rule.csv")
    if "--lstm" in sys.argv:
        rows = []
        for r in con.execute("SELECT student_id, username FROM students WHERE username NOT LIKE 'demo\\_%' ESCAPE '\\'"):
            d = db.get_daily(con, r["student_id"])
            if len(d) >= 30:
                try:
                    m = ml.train_lstm(d)
                    rows.append(dict(student=r["username"], days=m["n_days"], rmse=round(m["rmse"], 2),
                                     baseline=round(m["baseline_rmse"], 2), beats=m["beats_baseline"]))
                except Exception as e:
                    print("LSTM skipped for", r["username"], "-", e)
        print("\nLSTM per student:\n", pd.DataFrame(rows) if rows else "no student has 30+ days yet")

"""Prints the error of three simple baseline methods on DEMO (synthetic) data.
It uses a temporary database, so your real pilot data is never touched. Run: python baseline_check.py"""
import os
import tempfile
import db
import ml
import seed_demo

con = db.connect(os.path.join(tempfile.mkdtemp(), "demo.db"))
db.init_db(con)
seed_demo.seed(con)
daily = db.get_daily(con, db.get_student_by_username(con, "demo_1")["student_id"])
b = ml.compare_baselines(daily)
print(f"Demo student: {len(daily)} days of synthetic data, {b['n_test']} test days")
print(f"Average (mean) baseline:        RMSE {b['mean_rmse']:.2f}")
print(f"Same as yesterday (naive):      RMSE {b['naive_rmse']:.2f}")
print(f"Linear regression (ridge):      RMSE {b['linear_rmse']:.2f}")

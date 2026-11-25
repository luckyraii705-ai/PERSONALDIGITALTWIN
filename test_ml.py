"""Unit tests: clustering, baselines and (when TensorFlow is installed) the LSTM."""
import pytest
import db
import ml
import seed_demo


@pytest.fixture
def history(con):
    seed_demo.seed(con, days=40)
    return db.get_daily(con, db.get_student_by_username(con, "demo_1")["student_id"])


@pytest.mark.parametrize("days,expected_k", [(20, None), (21, 2), (29, 2), (30, 3), (40, 3)])
def test_clustering_switches_on_with_enough_data(history, days, expected_k):
    prof = ml.cluster_profile(history.head(days))
    assert (prof["k"] if prof else None) == expected_k


def test_cluster_summary_counts_every_day(history):
    prof = ml.cluster_profile(history)
    assert prof["summary"]["days"].sum() == len(history)
    assert -1 <= prof["silhouette"] <= 1 and prof["today"] in prof["summary"].index


def test_clustering_survives_a_constant_column(history):
    history = history.assign(study_hours=3.0)
    assert ml.cluster_profile(history)["k"] == 3


def test_clustering_survives_missing_values(history):
    history.loc[3:6, "mood"] = None
    assert ml.cluster_profile(history) is not None


def test_fewer_restarts_keep_the_same_quality(history):
    fast, slow = ml.cluster_profile(history, n_init=3), ml.cluster_profile(history, n_init=10)
    assert abs(fast["silhouette"] - slow["silhouette"]) < 0.1


def test_baselines_are_positive_numbers(history):
    b = ml.compare_baselines(history)
    assert all(b[k] > 0 for k in ("mean_rmse", "naive_rmse", "linear_rmse")) and b["n_test"] >= 5


def test_baselines_refuse_too_little_data(history):
    with pytest.raises(ValueError):
        ml.compare_baselines(history.head(12))


def test_lstm_returns_result_and_timings(history):
    pytest.importorskip("tensorflow")
    r = ml.train_lstm(history, epochs=3)
    for key in ("next_value", "rmse", "mae", "baseline_rmse", "train_seconds", "inference_ms", "predict_api_ms"):
        assert r[key] >= 0
    assert 1 <= r["next_value"] <= 10


def test_lstm_refuses_too_little_data(history):
    pytest.importorskip("tensorflow")
    with pytest.raises(ValueError):
        ml.train_lstm(history.head(25), epochs=1)

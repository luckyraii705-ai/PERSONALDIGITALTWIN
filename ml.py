"""Models that switch on as a student's history grows: clustering (21+ days) and LSTM (30+ days)."""
import time

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import MinMaxScaler, StandardScaler
import config


def _field_names(daily):
    return [f["name"] for f in config.DAILY_FIELDS if f["name"] in daily.columns]


def _filled(daily, fields):
    x = daily[fields].astype(float)
    return x.fillna(x.mean()).dropna()


def cluster_profile(daily, n_init=None):
    """Groups the student's days into types (e.g. low, typical, best days). None if too little data."""
    fields = _field_names(daily)
    if len(daily) < config.MIN_DAYS_CLUSTER or len(fields) < 2:
        return None
    x = _filled(daily, fields)
    if len(x) < config.MIN_DAYS_CLUSTER:
        return None
    k = 3 if len(x) >= 30 else 2
    scaled = StandardScaler().fit_transform(x)  # scale once, used for both clustering and the score
    labels = KMeans(k, n_init=n_init or config.KMEANS_N_INIT, random_state=0).fit_predict(scaled)
    sil = float(silhouette_score(scaled, labels))
    d = x.copy()
    d["cluster"] = labels
    key = config.TARGET if config.TARGET in fields else fields[0]
    order = d.groupby("cluster")[key].mean().sort_values().index.tolist()
    tags = ["Low days", "Typical days", "Best days"] if k == 3 else ["Lower days", "Better days"]
    names = {c: tags[i] for i, c in enumerate(order)}
    d["day_type"] = d["cluster"].map(names)
    summary = d.groupby("day_type")[fields].mean().round(2)
    summary["days"] = d.groupby("day_type").size()
    return dict(summary=summary, today=d["day_type"].iloc[-1], silhouette=sil, k=k)


def _series(daily, fields):
    s = daily.set_index("date")[fields].astype(float)
    s = s[~s.index.duplicated()].asfreq("D").interpolate(limit=3, limit_direction="both")
    return s.dropna()


def compare_baselines(daily, target=None):
    """Test-set RMSE of three simple methods on the same chronological split the LSTM uses:
    mean = always the training average, naive = same as yesterday, linear = ridge regression
    on the last WINDOW days. The LSTM should beat the best of these to be worth using."""
    from sklearn.linear_model import Ridge
    target = target or config.TARGET
    fields = _field_names(daily)
    s = _series(daily, fields)
    w = config.WINDOW
    n_seq = len(s) - w
    if n_seq < 10:
        raise ValueError("Not enough days to compare methods")
    split = int(0.8 * n_seq)
    t = s[target].values
    X = np.array([s.values[i:i + w].ravel() for i in range(n_seq)])
    y = np.array([t[i + w] for i in range(n_seq)])
    y_test = y[split:]
    rmse = lambda p: float(np.sqrt(np.mean((np.asarray(p) - y_test) ** 2)))
    lin = Ridge(alpha=1.0).fit(X[:split], y[:split])
    return dict(mean_rmse=rmse(np.full(len(y_test), y[:split].mean())),
                naive_rmse=rmse([t[i + w - 1] for i in range(split, n_seq)]),
                linear_rmse=rmse(lin.predict(X[split:])), n_test=len(y_test))


def train_lstm(daily, target=None, epochs=150, seed=0):
    """Predicts tomorrow's target from the last WINDOW days. Needs TensorFlow and 30+ days.
    Also reports a baseline (predict the training average) so the result can be judged honestly."""
    import tensorflow as tf
    target = target or config.TARGET
    fields = _field_names(daily)
    s = _series(daily, fields)
    if len(s) < config.MIN_DAYS_LSTM:
        raise ValueError(f"Need at least {config.MIN_DAYS_LSTM} days of data ({len(s)} so far)")
    tf.random.set_seed(seed)
    np.random.seed(seed)
    w, t_idx = config.WINDOW, fields.index(target)
    n_seq = len(s) - w
    split = int(0.8 * n_seq)
    scaler = MinMaxScaler().fit(s.iloc[:split + w].values)  # scale using training days only
    arr = scaler.transform(s.values)
    X = np.array([arr[i:i + w] for i in range(n_seq)], dtype="float32")
    y = np.array([arr[i + w, t_idx] for i in range(n_seq)], dtype="float32")
    model = tf.keras.Sequential([tf.keras.layers.Input(shape=(w, len(fields))),
                                 tf.keras.layers.LSTM(16), tf.keras.layers.Dropout(0.2),
                                 tf.keras.layers.Dense(1)])
    model.compile(optimizer=tf.keras.optimizers.Adam(0.005), loss="mse")
    stop = tf.keras.callbacks.EarlyStopping(patience=15, restore_best_weights=True)
    t0 = time.perf_counter()
    model.fit(X[:split], y[:split], validation_split=0.2, epochs=epochs, batch_size=8,
              shuffle=False, callbacks=[stop], verbose=0)
    train_s = time.perf_counter() - t0
    lo, hi = scaler.data_min_[t_idx], scaler.data_max_[t_idx]
    inv = lambda v: v * (hi - lo) + lo
    pred, actual = inv(model.predict(X[split:], verbose=0).ravel()), inv(y[split:])
    rmse = float(np.sqrt(np.mean((pred - actual) ** 2)))
    b = compare_baselines(daily, target)
    base_rmse = min(b["mean_rmse"], b["naive_rmse"], b["linear_rmse"])  # best simple method
    last_window = arr[-w:][None].astype("float32")
    t1 = time.perf_counter()
    nxt_scaled = float(model(last_window, training=False).numpy()[0, 0])  # direct call: no per-call overhead
    infer_ms = (time.perf_counter() - t1) * 1000
    t2 = time.perf_counter()
    model.predict(last_window, verbose=0)            # the old way, timed only so benchmark.py can compare
    predict_api_ms = (time.perf_counter() - t2) * 1000
    nxt = inv(nxt_scaled)
    return dict(target=target, next_value=float(np.clip(nxt, 1, 10)) if target == "mood" else float(nxt),
                rmse=rmse, mae=float(np.mean(np.abs(pred - actual))), baseline_rmse=base_rmse, mean_rmse=b["mean_rmse"], naive_rmse=b["naive_rmse"],
                linear_rmse=b["linear_rmse"],
                beats_baseline=bool(rmse < base_rmse), n_days=len(s), n_test=len(actual),
                train_seconds=train_s, inference_ms=infer_ms, predict_api_ms=predict_api_ms)

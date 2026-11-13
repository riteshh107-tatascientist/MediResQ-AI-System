"""Demand forecasting: baselines + ETS-style smoothing + Random Forest + Gradient Boosting.
Chronological splits only. Metrics are computed from real hold-out forecasts (never invented)."""
from datetime import date, timedelta
import hashlib

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor

from . import config

LAGS = [1, 2, 7, 14, 21, 28]


# ---------------- data prep ----------------
def load_series(db, facility_id, medicine_id, as_of, days=365):
    end = pd.Timestamp(as_of) - pd.Timedelta(days=1)
    idx = pd.date_range(end - pd.Timedelta(days=days - 1), end)
    if facility_id in (None, "ALL"):
        df = db.df("SELECT date, SUM(qty) qty FROM consumption WHERE medicine_id=? GROUP BY date", (medicine_id,))
    else:
        df = db.df("SELECT date, qty FROM consumption WHERE facility_id=? AND medicine_id=?", (facility_id, medicine_id))
    s = pd.Series(df.qty.values, index=pd.to_datetime(df.date)).reindex(idx)
    return s


def clean_series(s):
    """Missing days -> median of same weekday over previous 8 weeks (fallback overall median).
    Outliers capped at Q3+3*IQR (counted). True zeros are kept as demand."""
    info = {"missing": int(s.isna().sum()), "zero_days": int((s == 0).sum())}
    s = s.copy()
    med = s.median() if s.notna().any() else 0.0
    for i in np.where(s.isna())[0]:
        past = s.iloc[max(0, i - 56):i]
        same = past[past.index.dayofweek == s.index[i].dayofweek].dropna()
        s.iloc[i] = same.median() if len(same) else med
    q1, q3 = np.percentile(s, [25, 75])
    cap = q3 + 3 * (q3 - q1)
    info["outliers_capped"] = int((s > cap).sum()) if cap > 0 else 0
    if cap > 0:
        s = s.clip(upper=cap)
    return s, info


def seasonality(s):
    s = s.dropna()
    dow = (s.groupby(s.index.dayofweek).mean() / max(s.mean(), 1e-9)).round(3)
    dow.index = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    mon = (s.groupby(s.index.month).mean() / max(s.mean(), 1e-9)).round(3)
    x = s.values - s.values.mean()
    acf7 = float(np.sum(x[7:] * x[:-7]) / max(np.sum(x * x), 1e-9))
    return dow, mon, acf7


# ---------------- models: f(y_array, start_dow, h) -> array ----------------
def _dow_next(last_index, h):
    return np.array([(last_index.dayofweek + 1 + i) % 7 for i in range(h)])


def m_moving_avg(y, idx, h, w=7):
    return np.full(h, float(np.mean(y[-w:])))


def m_seasonal_naive(y, idx, h, p=7):
    last = y[-p:]
    return np.array([last[i % p] for i in range(h)], dtype=float)


def _ets_fit(y, idx, weeks=8):
    n = len(y)
    use = y[-7 * weeks:]
    dows = idx.dayofweek.values[-7 * weeks:]
    if use.mean() <= 1e-9:          # all-zero history: no seasonality, zero level
        return 0.0, np.ones(7), 0.1
    m = use.mean()
    ind = np.array([use[dows == d].mean() / m if (dows == d).any() else 1.0 for d in range(7)])
    ind = ind / max(ind.mean(), 1e-9)
    ds = y / ind[idx.dayofweek.values]
    best = (None, 1e18)
    for a in (0.03, 0.05, 0.1, 0.2, 0.3, 0.5):
        lv, sse = ds[:7].mean(), 0.0
        for v in ds[7:]:
            sse += (v - lv) ** 2
            lv = a * v + (1 - a) * lv
        if sse < best[1]:
            best = ((a, lv), sse)
    return best[0][1], ind, best[0][0]


def m_ets(y, idx, h):
    lv, ind, _ = _ets_fit(y, idx)
    return np.maximum(0, lv * ind[_dow_next(idx[-1], h)])


def m_holt_winters(y, idx, h):  # optional (statsmodels); returns None if unavailable
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
        fit = ExponentialSmoothing(y + 1e-3, trend=None, seasonal="add", seasonal_periods=7,
                                   initialization_method="estimated").fit()
        return np.maximum(0, fit.forecast(h))
    except Exception:
        return None


def _feat(hist, date_):
    n = len(hist)
    f = [hist[-l] if n >= l else hist[0] for l in LAGS]
    f += [np.mean(hist[-7:]), np.mean(hist[-28:])]
    dw = date_.dayofweek
    doy = date_.dayofyear
    f += [np.sin(2 * np.pi * dw / 7), np.cos(2 * np.pi * dw / 7), np.sin(2 * np.pi * doy / 365.25), np.cos(2 * np.pi * doy / 365.25)]
    return f


def _ml(model):
    def fn(y, idx, h):
        X, t = [], []
        for i in range(28, len(y)):
            X.append(_feat(y[:i], idx[i]))
            t.append(y[i])
        model.fit(np.array(X), np.array(t))
        hist = list(y)
        out = []
        for k in range(h):
            d = idx[-1] + pd.Timedelta(days=k + 1)
            p = max(0.0, float(model.predict(np.array([_feat(np.array(hist), d)]))[0]))
            out.append(p)
            hist.append(p)
        return np.array(out)
    return fn


def model_registry(seed=None):
    seed = config.SEED if seed is None else seed
    reg = {
        "Moving Average (7d)": m_moving_avg,
        "Seasonal Naive (7d)": m_seasonal_naive,
        "Exponential Smoothing (SES + weekly index)": m_ets,
        "Random Forest": _ml(RandomForestRegressor(n_estimators=120, max_depth=8, min_samples_leaf=3, random_state=seed, n_jobs=1)),
        "Gradient Boosting": _ml(GradientBoostingRegressor(n_estimators=150, max_depth=3, learning_rate=0.05, subsample=0.8, random_state=seed)),
    }
    return reg


BASELINES = {"Moving Average (7d)", "Seasonal Naive (7d)"}


def metrics(y_true, y_pred):
    e = np.asarray(y_true) - np.asarray(y_pred)
    s = float(np.sum(np.abs(y_true)))
    return {"MAE": float(np.mean(np.abs(e))), "RMSE": float(np.sqrt(np.mean(e ** 2))),
            "WAPE": float(np.sum(np.abs(e)) / s) if s > 0 else float("nan")}


def evaluate_series(s_clean, h=30, with_hw=False):
    """Train / validation / test chronological evaluation.
    models fit on [0:n-2h] -> validation (selection); fit on [0:n-h] -> test (reporting)."""
    y = s_clean.values.astype(float)
    idx = s_clean.index
    n = len(y)
    reg = model_registry()
    if with_hw:
        reg["Holt-Winters (statsmodels)"] = m_holt_winters
    rows, preds = [], {}
    for name, fn in reg.items():
        for split, cut in (("validation", n - 2 * h), ("test", n - h)):
            p = fn(y[:cut], idx[:cut], h)
            if p is None:
                break
            yt = y[cut:cut + h]
            row = {"model": name, "split": split, **metrics(yt, p)}
            for hh in (7, 14, 30):
                row[f"WAPE@{hh}"] = metrics(yt[:hh], p[:hh])["WAPE"]
            rows.append(row)
            if split == "test":
                preds[name] = p
    tab = pd.DataFrame(rows)
    val = tab[tab.split == "validation"].set_index("model").WAPE
    best = val.idxmin()
    test = tab[tab.split == "test"].set_index("model")
    best_base = test.loc[[m for m in test.index if m in BASELINES]].WAPE.min()
    return {"table": tab, "best_model": best, "test_preds": preds,
            "improvement_vs_best_baseline_pct": float((best_base - test.WAPE[best]) / best_base * 100) if best_base > 0 else float("nan"),
            "test_dates": idx[n - h:], "test_actual": y[n - h:], "best_test_rmse": float(test.RMSE[best])}


def final_forecast(s_clean, model_name, rmse, h=30):
    reg = model_registry()
    fn = reg.get(model_name, m_ets)
    p = fn(s_clean.values.astype(float), s_clean.index, h)
    dates = pd.date_range(s_clean.index[-1] + pd.Timedelta(days=1), periods=h)
    z = 1.2816  # ~80% two-sided under a normal-residual ASSUMPTION
    return pd.DataFrame({"date": dates, "forecast": p, "lower_80": np.maximum(0, p - z * rmse), "upper_80": p + z * rmse})


def run_forecast(db, facility_id, medicine_id, as_of, h=30, use_cache=True):
    s = load_series(db, facility_id, medicine_id, as_of)
    key = hashlib.md5(f"{facility_id}|{medicine_id}|{as_of}|{int(s.notna().sum())}|{round(float(s.sum(skipna=True)), 1)}".encode()).hexdigest()
    cf = config.CACHE_DIR / f"fc_{key}.joblib"
    if use_cache and cf.exists():
        try:
            return joblib.load(cf)
        except Exception:
            pass
    clean, info = clean_series(s)
    ev = evaluate_series(clean, h)
    fc = final_forecast(clean, ev["best_model"], ev["best_test_rmse"], h)
    dow, mon, acf7 = seasonality(clean)
    out = {"clean": clean, "info": info, "eval": ev, "forecast": fc, "dow": dow, "month": mon, "acf7": acf7}
    if use_cache:
        config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump(out, cf)
    return out


# ---------------- fast forecasts for operational use (all hospital x medicine) ----------------
def fast_forecast_all(db, as_of, horizon=30):
    """ETS-style forecasts for every hospital-medicine series + residual sigma. Returns dict[(f,m)]->{mean,sigma}."""
    c = db.df("SELECT date, facility_id, medicine_id, qty FROM consumption WHERE date>=? AND date<?",
              (str(pd.Timestamp(as_of) - pd.Timedelta(days=120)), str(pd.Timestamp(as_of))))
    out = {}
    end = pd.Timestamp(as_of) - pd.Timedelta(days=1)
    idx = pd.date_range(end - pd.Timedelta(days=119), end)
    for (f, m), g in c.groupby(["facility_id", "medicine_id"]):
        s = pd.Series(g.qty.values, index=pd.to_datetime(g.date)).reindex(idx)
        s, _ = clean_series(s)
        y = s.values.astype(float)
        lv, ind, _a = _ets_fit(y, idx)
        fit_res = y[-56:] - (np.mean(y[-56:]) * ind[idx.dayofweek.values[-56:]] / max(ind.mean(), 1e-9))
        out[(f, m)] = {"mean": np.maximum(0, lv * ind[_dow_next(idx[-1], horizon)]), "sigma": float(np.std(fit_res))}
    return out

"""Self-calibrating cloud detection from the sky-facing sensors.

Pure numpy, no Django imports: the same code runs in the web app
(`update_cloud_status` command) and in the offline validation against DWD
reference data (`cloud_eval/validate_detector.py`).

Method
------
Raw rows are reduced to 10-min medians. Per bin, one or more features are
computed depending on the sun elevation:

* night (sun below 0 deg): IR sky temperature minus the MLX90614 die
  temperature (or minus the air temperature); clouds raise it.
* day (sun above 5 deg): illuminance relative to a clear-sky model (lux index)
  and the solar heating of the sensor box; clouds lower both.
* in between (twilight) no statement is made.

Thresholds, smoothing and period limits were chosen by validating against DWD
Potsdam (cloud_eval/validate_detector.py).

No fixed thresholds are used. Each feature is rescaled with percentiles of the
same feature over the preceding ``window_days`` (same period type, only data
since the active calibration epoch), giving a score of 0 for the clearest and
1 for the cloudiest conditions seen recently. Hardware changes, window soiling
and seasonal drifts are absorbed this way; after a hardware change a new
calibration epoch makes the detector start from scratch.
"""
from dataclasses import dataclass, field

import numpy as np

JD_UNIX_EPOCH = 2440587.5

PERIOD_NIGHT = 'night'
PERIOD_DAY = 'day'
PERIOD_TWILIGHT = 'twilight'

LABEL_CLEAR = 'clear'
LABEL_PARTLY = 'partly'
LABEL_CLOUDY = 'cloudy'
LABEL_CALIBRATING = 'calibrating'
LABEL_UNKNOWN = 'unknown'

# Old TSL2591 driver (firmware < 1.6): 53000 lx at night, 0 on ADC overflow in sun
LEGACY_LUX_ARTEFACT = 53000.0

# feature -> (percentile representing clear sky, percentile representing overcast)
FEATURE_PERCENTILES = {
    'ir': (5.0, 95.0),
    'lux': (90.0, 10.0),
    'box': (90.0, 10.0),
    'uv': (90.0, 10.0),
}
# Minimum spread between the two percentiles; below it the window holds only one
# kind of sky (or a dead sensor) and no statement is possible.
FEATURE_MIN_SPREAD = {
    'ir': 0.2,     # K
    'lux': 0.1,    # log10 units
    'box': 0.1,    # K / sqrt(W m^-2)
    'uv': 0.1,
}


@dataclass(frozen=True)
class Config:
    window_days: float = 30.0
    night_max_sun_el: float = 0.0
    day_min_sun_el: float = 5.0
    clear_max: float = 0.35
    cloudy_min: float = 0.65
    min_calibration_periods: int = 7
    min_bins_per_period: int = 12
    ir_reference: str = 'box'  # 'box' (MLX die temperature) or 'air'
    night_features: tuple = ('ir',)
    day_features: tuple = ('lux', 'box')
    # Causal running median over this many bins of the same period (1 = off)
    smooth_bins: int = 3
    bin_seconds: int = 600
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Astronomy
# ---------------------------------------------------------------------------
def unix_to_jd(unix_seconds):
    return np.asarray(unix_seconds, float) / 86400.0 + JD_UNIX_EPOCH


def jd_to_unix(jd):
    return (np.asarray(jd, float) - JD_UNIX_EPOCH) * 86400.0


def solar_elevation(unix_seconds, lat_deg, lon_deg):
    """Geometric solar elevation in degrees (low-precision almanac, ~0.1 deg)."""
    n = unix_to_jd(unix_seconds) - 2451545.0
    mean_lon = np.mod(280.460 + 0.9856474 * n, 360.0)
    g = np.radians(np.mod(357.528 + 0.9856003 * n, 360.0))
    ecl_lon = np.radians(mean_lon + 1.915 * np.sin(g) + 0.020 * np.sin(2 * g))
    eps = np.radians(23.439 - 4e-7 * n)
    ra = np.arctan2(np.cos(eps) * np.sin(ecl_lon), np.cos(ecl_lon))
    dec = np.arcsin(np.sin(eps) * np.sin(ecl_lon))
    gmst_h = np.mod(18.697374558 + 24.06570982441908 * n, 24.0)
    hour_angle = np.radians(gmst_h * 15.0 + lon_deg) - ra
    lat = np.radians(lat_deg)
    sin_el = np.sin(lat) * np.sin(dec) + np.cos(lat) * np.cos(dec) * np.cos(hour_angle)
    return np.degrees(np.arcsin(np.clip(sin_el, -1.0, 1.0)))


def clearsky_ghi(sun_el_deg):
    """Clear-sky global horizontal irradiance in W/m^2 (Haurwitz 1945)."""
    cz = np.sin(np.radians(np.asarray(sun_el_deg, float)))
    up = cz > 0
    safe = np.where(up, cz, 1.0)
    return np.where(up, 1098.0 * safe * np.exp(-0.057 / safe), 0.0)


def period_of(sun_el, cfg=Config()):
    sun_el = np.asarray(sun_el, float)
    return np.where(sun_el < cfg.night_max_sun_el, PERIOD_NIGHT,
                    np.where(sun_el > cfg.day_min_sun_el, PERIOD_DAY, PERIOD_TWILIGHT))


def period_group(unix_seconds, period):
    """Integer id of the night/day a bin belongs to (nights counted from noon)."""
    t = np.asarray(unix_seconds, float)
    shift = np.where(np.asarray(period) == PERIOD_NIGHT, 43200.0, 0.0)
    return np.floor((t - shift) / 86400.0).astype(np.int64)


# ---------------------------------------------------------------------------
# Binning and features
# ---------------------------------------------------------------------------
def bin_rows(unix_seconds, columns, bin_seconds=600):
    """Median of each column per bin; bins are labelled by their end time.

    ``columns`` maps names to arrays aligned with ``unix_seconds`` (NaN = missing).
    Returns (bin_end, n_rows, {name: median}).
    """
    t = np.asarray(unix_seconds, float)
    if t.size == 0:
        return np.empty(0), np.empty(0, int), {k: np.empty(0) for k in columns}
    # (end - bin, end] belongs to the bin labelled `end`
    idx = np.ceil(t / bin_seconds).astype(np.int64)
    order = np.argsort(idx, kind='stable')
    idx_sorted = idx[order]
    uniq, start = np.unique(idx_sorted, return_index=True)
    stop = np.append(start[1:], idx_sorted.size)
    out = {}
    for name, values in columns.items():
        v = np.asarray(values, float)[order]
        med = np.full(uniq.size, np.nan)
        for k, (a, b) in enumerate(zip(start, stop)):
            chunk = v[a:b]
            chunk = chunk[np.isfinite(chunk)]
            if chunk.size:
                med[k] = np.median(chunk)
        out[name] = med
    return uniq.astype(float) * bin_seconds, stop - start, out


def clean_illuminance(lux, sun_el):
    """Drop known artefacts of the pre-1.6 TSL2591 driver (NaN = unusable)."""
    lux = np.asarray(lux, float).copy()
    sun_el = np.asarray(sun_el, float)
    lux[lux == LEGACY_LUX_ARTEFACT] = np.nan
    lux[(lux == 0) & (sun_el > 5)] = np.nan  # ADC overflow reported as 0
    return lux


def compute_features(bin_end, med, lat_deg, lon_deg, cfg=Config()):
    """Feature arrays per bin from binned medians (keys as in ``bin_rows``)."""
    mid = np.asarray(bin_end, float) - cfg.bin_seconds / 2.0
    sun_el = solar_elevation(mid, lat_deg, lon_deg)
    ghi = clearsky_ghi(sun_el)
    sky = med.get('sky_temp')
    box = med.get('box_temp')
    air = med.get('temperature')
    reference = box if cfg.ir_reference == 'box' else air
    features = {
        'ir': sky - reference,
        'lux': np.log10((med['illuminance'] + 100.0) / (ghi + 10.0)),
        'box': (box - air) / np.sqrt(ghi + 50.0),
        'uv': med.get('uv_index', np.full(len(mid), np.nan)),
    }
    return sun_el, features


def raw_to_features(unix_seconds, rows, lat_deg, lon_deg, cfg=Config()):
    """Raw station rows -> (bin_end, n_rows, sun_el, features)."""
    t = np.asarray(unix_seconds, float)
    rows = dict(rows)
    if 'illuminance' in rows:
        rows['illuminance'] = clean_illuminance(rows['illuminance'], solar_elevation(t, lat_deg, lon_deg))
    # MLX90614 reports 0/0 when it is unavailable
    sky = np.asarray(rows['sky_temp'], float).copy()
    box = np.asarray(rows['box_temp'], float).copy()
    dead = (sky == 0) & (box == 0)
    sky[dead] = np.nan
    box[dead] = np.nan
    rows['sky_temp'], rows['box_temp'] = sky, box
    bin_end, n, med = bin_rows(t, rows, cfg.bin_seconds)
    sun_el, features = compute_features(bin_end, med, lat_deg, lon_deg, cfg)
    return bin_end, n, sun_el, features


# ---------------------------------------------------------------------------
# Calibration and classification
# ---------------------------------------------------------------------------
@dataclass
class Calibration:
    """Calibration state of one feature at one point in time."""
    p_clear: float = np.nan
    p_cloudy: float = np.nan
    n_periods: int = 0
    ready: bool = False
    degenerate: bool = False


def calibrate(values, groups, feature, cfg=Config()):
    """Percentile calibration from the history of one feature (same period type)."""
    ok = np.isfinite(values)
    values = values[ok]
    groups = groups[ok]
    cal = Calibration()
    if values.size == 0:
        return cal
    _, counts = np.unique(groups, return_counts=True)
    cal.n_periods = int(np.sum(counts >= cfg.min_bins_per_period))
    q_clear, q_cloudy = FEATURE_PERCENTILES[feature]
    cal.p_clear, cal.p_cloudy = np.percentile(values, [q_clear, q_cloudy])
    cal.ready = cal.n_periods >= cfg.min_calibration_periods
    cal.degenerate = abs(cal.p_cloudy - cal.p_clear) < FEATURE_MIN_SPREAD[feature]
    return cal


def feature_score(x, cal):
    if not np.isfinite(x) or not cal.ready or cal.degenerate:
        return np.nan
    return float(np.clip((x - cal.p_clear) / (cal.p_cloudy - cal.p_clear), 0.0, 1.0))


def label_for(score, cfg=Config()):
    if not np.isfinite(score):
        return LABEL_UNKNOWN
    if score < cfg.clear_max:
        return LABEL_CLEAR
    if score > cfg.cloudy_min:
        return LABEL_CLOUDY
    return LABEL_PARTLY


@dataclass
class BinResult:
    period: str
    score: float      # after smoothing; NaN if no statement
    score_raw: float  # before smoothing
    label: str
    n_periods: int  # calibration periods available (minimum over used features)


def classify_series(bin_end, sun_el, features, cfg=Config(), epoch_starts=(),
                    targets=None, prior_raw_scores=None):
    """Causal classification of a time-ordered series of bins.

    Each bin is calibrated only with bins *before* it, within ``window_days`` and
    not before the latest calibration epoch start <= its own time.
    ``targets`` (index array) restricts which bins are classified; all bins
    serve as history. ``prior_raw_scores`` (aligned with the bins, NaN where
    unknown) supplies unsmoothed scores of bins classified in earlier runs, for
    the running median. Returns a list of BinResult (one per target).
    """
    t = np.asarray(bin_end, float)
    period = period_of(sun_el, cfg)
    groups = period_group(t, period)
    epochs = np.sort(np.asarray(list(epoch_starts), float))
    window = cfg.window_days * 86400.0
    if targets is None:
        targets = np.arange(t.size)

    # history per period type, kept in time order for searchsorted
    by_period = {}
    for p in (PERIOD_NIGHT, PERIOD_DAY):
        idx = np.flatnonzero(period == p)
        by_period[p] = (idx, t[idx])

    raw_scores = (np.full(t.size, np.nan) if prior_raw_scores is None
                  else np.asarray(prior_raw_scores, float).copy())
    results = {}
    for i in targets:
        p = period[i]
        if p == PERIOD_TWILIGHT:
            results[i] = BinResult(p, np.nan, np.nan, LABEL_UNKNOWN, 0)
            continue
        epoch = epochs[epochs <= t[i]].max() if np.any(epochs <= t[i]) else -np.inf
        start = max(t[i] - window, epoch)
        idx, tp = by_period[p]
        lo = np.searchsorted(tp, start, side='left')
        hi = np.searchsorted(tp, t[i], side='left')
        hist = idx[lo:hi]
        names = cfg.night_features if p == PERIOD_NIGHT else cfg.day_features
        scores, n_periods, calibrating = [], [], False
        for name in names:
            cal = calibrate(features[name][hist], groups[hist], name, cfg)
            n_periods.append(cal.n_periods)
            if not cal.ready:
                calibrating = True
                continue
            s = feature_score(features[name][i], cal)
            if np.isfinite(s):
                scores.append(s)
        n_cal = min(n_periods) if n_periods else 0
        if calibrating and not scores:
            results[i] = BinResult(p, np.nan, np.nan, LABEL_CALIBRATING, n_cal)
            continue
        raw = float(np.mean(scores)) if scores else np.nan
        raw_scores[i] = raw
        score = raw
        if cfg.smooth_bins > 1 and np.isfinite(raw):
            prev = hist[-(cfg.smooth_bins - 1):]
            prev = prev[t[i] - t[prev] <= cfg.smooth_bins * cfg.bin_seconds]
            score = float(np.nanmedian(np.append(raw_scores[prev], raw)))
        results[i] = BinResult(p, score, raw, label_for(score, cfg), n_cal)
    return [results[i] for i in targets]

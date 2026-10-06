"""Django side of the cloud detection: incremental updates and current status."""
import dataclasses
import math
from datetime import datetime, timedelta, timezone as dt_timezone

import numpy as np
from django.conf import settings
from django.utils import timezone

from . import cloud_detection as cd
from .models import CalibrationEpoch, CloudBin, Dataset

FEATURES = ('ir', 'lux', 'box', 'uv')
RAW_COLUMNS = ('sky_temp', 'box_temp', 'temperature', 'illuminance', 'uv_index')
# Rows arrive in 60 s bursts: a bin is processed once it ended this long ago
SETTLE_SECONDS = 120
FETCH_CHUNK_DAYS = 1.0

LABEL_TEXT = {
    cd.LABEL_CLEAR: 'Clear',
    cd.LABEL_PARTLY: 'Partly cloudy',
    cd.LABEL_CLOUDY: 'Cloudy',
    cd.LABEL_CALIBRATING: 'Calibrating',
    cd.LABEL_UNKNOWN: 'Unknown',
}


def detector_config():
    return dataclasses.replace(cd.Config(), **getattr(settings, 'CLOUD_DETECTION', {}))


def station_location():
    return settings.STATION_LATITUDE, settings.STATION_LONGITUDE


def epoch_starts():
    return [e.timestamp() for e in CalibrationEpoch.objects.values_list('start', flat=True)]


def _to_db(value):
    return None if value is None or not math.isfinite(value) else float(value)


def _to_np(value):
    return np.nan if value is None else value


def _new_bins(start_unix, end_unix, cfg):
    """Feature bins for raw rows with start < t <= end (unsaved CloudBin objects)."""
    lat, lon = station_location()
    bins = []
    chunk = FETCH_CHUNK_DAYS * 86400.0
    t0 = start_unix
    while t0 < end_unix:
        t1 = min(t0 + chunk, end_unix)
        rows = np.array(
            Dataset.objects
            .filter(jd__gt=cd.unix_to_jd(t0), jd__lte=cd.unix_to_jd(t1))
            .order_by('jd')
            .values_list('jd', *RAW_COLUMNS),
            dtype=float,
        ).reshape(-1, 1 + len(RAW_COLUMNS))
        if len(rows):
            unix = cd.jd_to_unix(rows[:, 0])
            columns = {name: rows[:, k + 1] for k, name in enumerate(RAW_COLUMNS)}
            bin_end, n, sun_el, feats = cd.raw_to_features(unix, columns, lat, lon, cfg)
            period = cd.period_of(sun_el, cfg)
            for k in range(len(bin_end)):
                # floating point jd can put a row of the boundary bin into the next chunk
                if not (start_unix < bin_end[k] <= end_unix):
                    continue
                bins.append(CloudBin(
                    time=datetime.fromtimestamp(bin_end[k], tz=dt_timezone.utc),
                    jd=float(cd.unix_to_jd(bin_end[k])),
                    n_samples=int(n[k]),
                    sun_el=float(sun_el[k]),
                    period=str(period[k]),
                    **{f: _to_db(feats[f][k]) for f in FEATURES},
                ))
        t0 = t1
    # a bin split across two chunks appears twice; keep the one with more rows
    unique = {}
    for b in bins:
        if b.time not in unique or b.n_samples > unique[b.time].n_samples:
            unique[b.time] = b
    return [unique[k] for k in sorted(unique)]


def classify(bins_to_classify, cfg):
    """Score and label the given (saved) bins, using stored bins as history."""
    if not bins_to_classify:
        return 0
    first = min(b.time for b in bins_to_classify)
    history_start = first - timedelta(days=cfg.window_days)
    history = list(CloudBin.objects.filter(time__gte=history_start).order_by('time'))
    target_pks = {b.pk for b in bins_to_classify}
    t = np.array([b.time.timestamp() for b in history])
    sun_el = np.array([b.sun_el for b in history])
    feats = {f: np.array([_to_np(getattr(b, f)) for b in history], float) for f in FEATURES}
    targets = np.array([i for i, b in enumerate(history) if b.pk in target_pks], int)
    prior = np.array([
        np.nan if b.pk in target_pks else _to_np(b.score_raw) for b in history
    ], float)
    results = cd.classify_series(t, sun_el, feats, cfg, epoch_starts(), targets, prior)
    updated = []
    for i, r in zip(targets, results):
        b = history[i]
        b.period = r.period
        b.score = _to_db(r.score)
        b.score_raw = _to_db(r.score_raw)
        b.label = r.label
        b.calibration_periods = r.n_periods
        updated.append(b)
    CloudBin.objects.bulk_update(
        updated, ['period', 'score', 'score_raw', 'label', 'calibration_periods'], batch_size=500)
    return len(updated)


def update(now=None, backfill_days=30.0, recompute_days=0.0):
    """Aggregate new raw data into CloudBins and classify them.

    Returns (number of new bins, number of classified bins).
    """
    cfg = detector_config()
    now = now or timezone.now()
    end = math.floor((now.timestamp() - SETTLE_SECONDS) / cfg.bin_seconds) * cfg.bin_seconds
    last = CloudBin.objects.order_by('-time').first()
    if last is not None:
        start = last.time.timestamp()
    else:
        start = math.floor((end - backfill_days * 86400.0) / cfg.bin_seconds) * cfg.bin_seconds

    new = _new_bins(start, end, cfg) if end > start else []
    CloudBin.objects.bulk_create(new, batch_size=500, ignore_conflicts=True)
    to_classify = list(CloudBin.objects.filter(
        time__gt=datetime.fromtimestamp(start, tz=dt_timezone.utc),
        time__lte=datetime.fromtimestamp(end, tz=dt_timezone.utc),
    )) if new else []
    if recompute_days > 0:
        since = now - timedelta(days=recompute_days)
        to_classify = list(CloudBin.objects.filter(time__gte=since))
    # Classify in time order so that smoothing sees the scores of earlier bins
    to_classify.sort(key=lambda b: b.time)
    classified = 0
    if recompute_days > 0:
        for b in to_classify:
            b.score_raw = None
        CloudBin.objects.bulk_update(to_classify, ['score_raw'], batch_size=500)
    for k in range(0, len(to_classify), 500):
        classified += classify(to_classify[k:k + 500], cfg)
    return len(new), classified


def current_status(now=None):
    """Latest cloud status for display, or None if there is no recent result."""
    now = now or timezone.now()
    max_age = timedelta(minutes=getattr(settings, 'CLOUD_STATUS_MAX_AGE_MINUTES', 30))
    latest = CloudBin.objects.filter(time__gte=now - max_age).order_by('-time').first()
    if latest is None:
        return None
    cfg = detector_config()
    status = {
        'label': latest.label,
        'text': LABEL_TEXT.get(latest.label, latest.label),
        'score': None if latest.score is None else round(latest.score, 3),
        'period': latest.period,
        'time': latest.time.isoformat(),
    }
    if latest.label == cd.LABEL_CALIBRATING:
        unit = 'nights' if latest.period == cd.PERIOD_NIGHT else 'days'
        status['calibration'] = {
            'periods': latest.calibration_periods,
            'required': cfg.min_calibration_periods,
            'unit': unit,
        }
        status['text'] = (
            f'Calibrating ({latest.calibration_periods}/{cfg.min_calibration_periods} {unit})'
        )
    return status

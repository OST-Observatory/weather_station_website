import hashlib
import json

from django.conf import settings
from django.core.cache import cache
from django.db.models import Count, Max

from .models import Dataset


def plot_cache_enabled(*, time_resolution, fresh: bool) -> bool:
    if fresh:
        return False
    min_res = getattr(settings, 'PLOT_CACHE_MIN_RESOLUTION_SECONDS', 60)
    return float(time_resolution) >= min_res


def compute_range_days(plot_range, start_dt=None, end_dt=None):
    if start_dt is not None and end_dt is not None:
        return (end_dt - start_dt).total_seconds() / 86400.0
    return float(plot_range)


def data_fingerprint(start_jd, end_jd):
    return Dataset.objects.filter(jd__range=[start_jd, end_jd]).aggregate(
        max_added_on=Max('added_on'),
        max_pk=Max('pk'),
        row_count=Count('id'),
    )


def build_cache_key(
        *,
        plot_range,
        start_jd,
        end_jd,
        start_dt,
        end_dt,
        time_resolution,
        plot_set,
        fingerprint,
        cache_namespace,
):
    if start_dt is not None and end_dt is not None:
        range_part = {'start_jd': start_jd, 'end_jd': end_jd}
    else:
        range_part = {'plot_range': float(plot_range)}
    payload = {
        'namespace': cache_namespace,
        **range_part,
        'time_resolution': float(time_resolution),
        'plot_set': sorted(plot_set),
        'timezone': getattr(settings, 'PLOT_DISPLAY_TIMEZONE', 'Europe/Berlin'),
        'fp': fingerprint,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()
    return f'plot_cache:{digest}'


def get_cached_plots(cache_key):
    return cache.get(cache_key)


def store_cached_plots(cache_key, script, div):
    ttl = getattr(settings, 'PLOT_CACHE_TTL_SECONDS', 30)
    cache.set(cache_key, (script, div), ttl)

"""PostgreSQL time-binning for large historical plot ranges."""

from django.conf import settings
from django.db import connection

import numpy as np

from .models import Dataset

MEDIAN_COLUMNS = frozenset({
    'temperature',
    'pressure',
    'humidity',
    'illuminance',
    'wind_speed',
    'sky_temp',
    'box_temp',
    'co2_ppm',
    'tvoc_ppb',
})
SUM_COLUMNS = frozenset({'rain'})
AVG_COLUMNS = frozenset({'is_raining'})

ALLOWED_COLUMNS = MEDIAN_COLUMNS | SUM_COLUMNS | AVG_COLUMNS


def is_postgresql():
    return connection.vendor == 'postgresql'


def range_days(plot_range, start_dt=None, end_dt=None):
    if start_dt is not None and end_dt is not None:
        return (end_dt - start_dt).total_seconds() / 86400.0
    return float(plot_range)


def should_use_postgres_binning(plot_range, start_dt=None, end_dt=None):
    if not is_postgresql():
        return False
    min_days = getattr(settings, 'PLOT_PG_BIN_MIN_DAYS', 1.0)
    return range_days(plot_range, start_dt, end_dt) > min_days


def _agg_expression(column):
    if column not in ALLOWED_COLUMNS:
        raise ValueError(f'Unsupported plot column for binning: {column}')
    if column in MEDIAN_COLUMNS:
        if column in {'co2_ppm', 'tvoc_ppb'}:
            return (
                f'percentile_cont(0.5) WITHIN GROUP '
                f'(ORDER BY {column}::double precision)'
            )
        return f'percentile_cont(0.5) WITHIN GROUP (ORDER BY {column})'
    if column in SUM_COLUMNS:
        return f'SUM({column})'
    return f'AVG({column}::double precision)'


def fetch_binned_rows(start_jd, end_jd, time_resolution, columns):
    """Return binned rows as a numpy array (bin_jd + requested columns)."""
    if not columns:
        return np.array([])

    bin_width = float(time_resolution) / 86400.0
    if bin_width <= 0:
        raise ValueError('time_resolution must be positive')

    table = Dataset._meta.db_table
    select_parts = [
        '(floor((jd - %s) / %s) * %s + %s)::double precision AS bin_jd',
    ]
    params = [start_jd, bin_width, bin_width, start_jd]
    for column in columns:
        select_parts.append(f'{_agg_expression(column)} AS {column}')

    sql = f"""
        SELECT {', '.join(select_parts)}
        FROM {table}
        WHERE jd >= %s AND jd <= %s
        GROUP BY 1
        ORDER BY 1
    """
    params.extend([start_jd, end_jd])

    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        rows = cursor.fetchall()

    if not rows:
        return np.array([])

    return np.array(rows, dtype=float)

import datetime
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo

import astropy.units as u
from astropy.time import Time
from astropy.timeseries import TimeSeries, aggregate_downsample

import numpy as np

from bokeh import models as mpl
from bokeh import plotting as bpl
from bokeh.embed import components
from bokeh.resources import Resources

from .models import Dataset
from .plot_db import fetch_binned_rows, should_use_postgres_binning
from .plot_cache import (
    build_cache_key,
    data_fingerprint,
    get_cached_plots,
    plot_cache_enabled,
    store_cached_plots,
)


# Constants
WIND_ROTATIONS_TO_MPS = 0.14
# Convert rain collector depth (mm) to equivalent depth per m².
# Gauge: 130 mm diameter → area π×65² mm² ≈ 132730 mm²; factor = 10000/132730.
RAIN_TO_MM_PER_M2_FACTOR = 0.07534
RAIN_FLAG_THRESHOLD = 0.5
MAX_PLOT_ROWS = 500_000
BERLIN_TZ = ZoneInfo('Europe/Berlin')
# Bokeh JS is loaded once from templates/bokeh.html (local static files).
BOKEH_RESOURCES = Resources(mode='inline', components=[])

ADDITIONAL_PG_COLUMNS = [
    'temperature',
    'humidity',
    'sky_temp',
    'box_temp',
    'pm1_0',
    'pm2_5',
    'pm10',
    'uv_index',
]


def _berlin_axis_label(sample_dt):
    if sample_dt is not None and sample_dt.dst() != datetime.timedelta(0):
        return 'Time [CEST]'
    return 'Time [CET]'


def jd_array_to_local_dt(x_jd):
    """Convert Julian dates to timezone-aware Europe/Berlin datetimes."""
    x_arr = np.atleast_1d(x_jd)
    if x_arr.size == 0:
        return np.array([], dtype=object)
    datetimes = Time(x_arr, format='jd').datetime
    if isinstance(datetimes, datetime.datetime):
        datetimes = [datetimes]
    else:
        datetimes = np.atleast_1d(datetimes).ravel()
    return np.array([
        dt.replace(tzinfo=dt_timezone.utc).astimezone(BERLIN_TZ)
        for dt in datetimes
    ])


def _empty_plot(y_identifier, x_identifier='jd'):
    tools = [mpl.PanTool(), mpl.WheelZoomTool(), mpl.BoxZoomTool(), mpl.ResetTool()]
    fig = bpl.figure(sizing_mode='scale_width', aspect_ratio=2, tools=tools)
    fig.toolbar.active_drag = None
    fig.toolbar.logo = None
    fig.background_fill_alpha = 0.
    fig.border_fill_alpha = 0.
    if x_identifier == 'jd':
        fig.xaxis.formatter = mpl.DatetimeTickFormatter()
        fig.xaxis.formatter.context = mpl.RELATIVE_DATETIME_CONTEXT()
    return fig


def _plots_too_large_note(row_count):
    return (
        f'Too many data points ({row_count:,}) for the selected range. '
        f'Please choose a shorter time range (max {MAX_PLOT_ROWS:,} raw points).'
    )


def _jd_range(plot_range=1., start_dt=None, end_dt=None):
    jd_current = Time(datetime.datetime.now(datetime.timezone.utc)).jd
    if start_dt is not None and end_dt is not None:
        return float(Time(start_dt).jd), float(Time(end_dt).jd)
    return float(jd_current - float(plot_range)), float(jd_current)


MAIN_PLOT_IDENTIFIERS = [
    'temperature',
    'pressure',
    'humidity',
    'illuminance',
    'wind_speed',
    'rain',
]

ADDITIONAL_PLOT_IDENTIFIERS = [
    'temp_combined',
    'temp_sky_diff',
    'air_quality',
    'uv_index',
]


def _render_with_cache(
        *,
        cache_namespace,
        plot_identifiers,
        build_figures,
        fresh=False,
        plot_range=1.,
        time_resolution=120.,
        start_dt=None,
        end_dt=None,
        **kwargs,
):
    start_jd, end_jd = _jd_range(plot_range, start_dt, end_dt)
    use_cache = plot_cache_enabled(
        time_resolution=time_resolution,
        fresh=fresh,
    )
    meta = {'cache_hit': False, 'cache_enabled': use_cache}

    plot_kwargs = {
        'plot_range': plot_range,
        'time_resolution': time_resolution,
        'start_dt': start_dt,
        'end_dt': end_dt,
    }

    if use_cache:
        fingerprint = data_fingerprint(start_jd, end_jd)
        cache_key = build_cache_key(
            plot_range=plot_range,
            start_jd=start_jd,
            end_jd=end_jd,
            start_dt=start_dt,
            end_dt=end_dt,
            time_resolution=time_resolution,
            plot_set=plot_identifiers,
            fingerprint=fingerprint,
            cache_namespace=cache_namespace,
        )
        cached = get_cached_plots(cache_key)
        if cached is not None:
            meta['cache_hit'] = True
            return cached[0], cached[1], meta

    figs = build_figures(**plot_kwargs)
    note = figs.pop('note', None)
    script, div = components(figs, BOKEH_RESOURCES)
    if note is not None:
        div['note'] = note

    if use_cache:
        store_cached_plots(cache_key, script, div)

    return script, div, meta

def main_plots(
        x_identifier,
        y_identifier_list,
        plot_range=1.,
        time_resolution=120.,
        start_dt=None,
        end_dt=None,
        **_unused,
    ):
    """
        Create main plots for the weather station dashboard

        Parameters
        ----------
        x_identifier        : `string`
            String that characterizes the model parameter field

        y_identifier_list   : `list`
            List with strings that characterizes the model parameter fields

        plot_range          : `float`, optional
            Time to plot in days.
            Default is ``1``.

        time_resolution     : `float`, optional
            Time resolution of the plot in seconds. The data is binned
            accordingly.
            Default is ``60``.

        Returns
        -------
        fig_dict            : `dictionary` {`y_identifier`:`bokeh.plotting.figure`}
            Figure dictionary
    """
    start_jd, end_jd = _jd_range(plot_range, start_dt, end_dt)

    #   Get requested range of data (include is_raining once if rain is requested)
    include_flags = 'rain' in y_identifier_list
    base_fields = [x_identifier, *y_identifier_list]
    if include_flags:
        base_fields.append('is_raining')

    pre_binned = False
    if should_use_postgres_binning(plot_range, start_dt, end_dt):
        pg_columns = list(y_identifier_list)
        if include_flags and 'is_raining' not in pg_columns:
            pg_columns.append('is_raining')
        data = fetch_binned_rows(start_jd, end_jd, time_resolution, pg_columns)
        pre_binned = data.size > 0
    else:
        rows = list(
            Dataset.objects.filter(jd__range=[start_jd, end_jd])
            .order_by('jd')
            .values_list(*base_fields)[:MAX_PLOT_ROWS + 1]
        )
        if len(rows) > MAX_PLOT_ROWS:
            fig_dict = {
                y_identifier: _empty_plot(y_identifier, x_identifier)
                for y_identifier in y_identifier_list
            }
            fig_dict['note'] = _plots_too_large_note(len(rows))
            return fig_dict
        data = np.array(rows) if rows else np.array([])

    #   Verify that data was returned
    if data.size == 0:
        no_data = True
        x_data_original = None
        flag_series_raw = None
    else:
        no_data = False
        x_data_original = data[:, 0]
        flag_series_raw = None
        if include_flags:
            flag_series_raw = data[:, len(y_identifier_list) + 1]

    #   Set Y range - use extrema or data range
    # y_range_extrema = {
    #     'temperature': (-40., 60.),
    #     'pressure': (900., 1080.),
    #     'humidity': (0., 100.),
    #     'illuminance': (0., 13000.),
    #     'wind_speed': (0., 300.),
    #     'rain': (0., 500.),
    # }

    #   Figure dictionary
    fig_dict = {}

    #   Make time series
    for i, y_identifier in enumerate(y_identifier_list):
        if no_data:
            x_data = y_data = data
        else:
            time_series = TimeSeries(
                time=Time(x_data_original, format='jd'),
                data={'data': data[:, i + 1]}
            )

            #   Binned time series (skip Python downsample when PostgreSQL already binned)
            if pre_binned:
                x_data = x_data_original
                y_data = data[:, i + 1]
                if y_identifier == 'rain':
                    y_data = y_data * RAIN_TO_MM_PER_M2_FACTOR
                    flag_data = flag_series_raw
                elif y_identifier == 'wind_speed':
                    y_data = y_data * WIND_ROTATIONS_TO_MPS
            elif len(time_series) > 1:
                if y_identifier == 'rain':
                    # Use already-fetched aligned data and downsample in-memory (single DB query overall)
                    y_series_raw = data[:, i + 1]
                    ts_rain = TimeSeries(
                        time=Time(x_data_original, format='jd'),
                        data={'rain': y_series_raw}
                    )
                    # Flag series may be None on legacy schemas
                    if flag_series_raw is not None:
                        ts_flag = TimeSeries(
                            time=Time(x_data_original, format='jd'),
                            data={'is_raining': flag_series_raw}
                        )
                    else:
                        ts_flag = None

                    ts_rain_sum = aggregate_downsample(
                        ts_rain,
                        time_bin_size=float(time_resolution) * u.s,
                        aggregate_func=np.nansum,
                    )
                    x_data = ts_rain_sum['time_bin_start'].value
                    y_data = ts_rain_sum['rain'].value

                    if ts_flag is not None:
                        ts_flag_mean = aggregate_downsample(
                            ts_flag,
                            time_bin_size=float(time_resolution) * u.s,
                            aggregate_func=np.nanmean,
                        )
                        flag_data = ts_flag_mean['is_raining'].value
                    else:
                        flag_data = np.zeros_like(y_data)

                    # Convert rain to mm/m^2 (see note below)
                    y_data = y_data * RAIN_TO_MM_PER_M2_FACTOR

                    # Apply mask
                    mask_local = np.invert(y_data.mask) if hasattr(y_data, 'mask') else np.ones_like(y_data, dtype=bool)
                    if hasattr(flag_data, 'mask'):
                        mask_local = mask_local & np.invert(flag_data.mask)
                    x_data = x_data[mask_local]
                    y_data = y_data[mask_local]
                    flag_data = flag_data[mask_local]
                else:
                    time_series_average = aggregate_downsample(
                        time_series,
                        time_bin_size=float(time_resolution) * u.s,
                        aggregate_func=np.nanmedian,
                    )
                    x_data = time_series_average['time_bin_start'].value

                    y_data = time_series_average['data'].value

                #   Wind gust: convert rotation to m/s
                if y_identifier == 'wind_speed':
                    y_data = y_data * WIND_ROTATIONS_TO_MPS
                # Robust mask handling (works for masked and plain ndarrays)
                mask = np.invert(y_data.mask) if hasattr(y_data, 'mask') else np.ones_like(y_data, dtype=bool)
                x_data = x_data[mask]
                y_data = y_data[mask]
            else:
                x_data = x_data_original
                y_data = data[:, i + 1]

        #   Tools attached to the figure
        tools = [
            mpl.PanTool(),
            mpl.WheelZoomTool(),
            mpl.BoxZoomTool(),
            mpl.ResetTool(),
        ]

        #   Calculate plot ranges
        if len(y_data):
            y_data_max = np.max(y_data)
            y_data_min = np.min(y_data)
        else:
            y_data_max, y_data_min = 0, 0

        #   TODO: Generalize or remove, since currently not used
        # y_extrema = y_range_extrema[y_identifier]

        # y_range = (
        #     max(y_extrema[0], y_data_min), min(y_extrema[1], y_data_max)
        # )
        # y_range = (
        #     y_range[0] - 0.01 * y_range[0], y_range[1] + 0.01 * y_range[1]
        # )

        #   Setup figure
        fig = bpl.figure(
            sizing_mode='scale_width',
            aspect_ratio=2,
            tools=tools,
            # y_range=y_range,
        )

        #   Convert JD to datetime object and set x-axis formatter
        if x_identifier == 'jd':
            x_data = jd_array_to_local_dt(x_data)
            fig.xaxis.formatter = mpl.DatetimeTickFormatter()
            fig.xaxis.formatter.context = mpl.RELATIVE_DATETIME_CONTEXT()
            sample_dt = x_data[0] if len(x_data) else None
            x_label = _berlin_axis_label(sample_dt)
        else:
            x_label = 'Date'

        #   Plot data
        if y_identifier in ['temperature', 'pressure', 'humidity']:
            fig.line(
                x_data,
                y_data,
                line_width=2,
                color="powderblue",
            )

        if y_identifier == 'rain' and 'flag_data' in locals():
            # Split points by rain drop sensor flag (≥ threshold) AND only mark when summed rain == 0 (drizzle)
            try:
                flagged_raw = flag_data.astype(float) >= RAIN_FLAG_THRESHOLD
            except Exception:
                flagged_raw = np.zeros_like(y_data, dtype=bool)

            # Only highlight bins with drop sensor ≥ threshold and no measured rain amount
            drizzle_mask = flagged_raw & (y_data <= 0.0)

            # Base rain points (all), styled in subtle blue
            cr_no = fig.scatter(
                x_data,
                y_data,
                color='powderblue',
                fill_alpha=0.3,
                line_alpha=0.3,
                size=8,
                line_width=1.,
                hover_fill_color="midnightblue",
                hover_alpha=0.5,
                hover_line_color="white",
                legend_label='Rain'
            )

            # Drizzle overlay (subtle blue accent), only if any
            if np.any(drizzle_mask):
                cr_yes = fig.scatter(
                    x_data[drizzle_mask],
                    y_data[drizzle_mask],
                    color='#B2B0E8',  
                    fill_alpha=0.7,
                    line_alpha=0.7,
                    size=8,
                    line_width=1.,
                    hover_fill_color="#90CAF9",
                    hover_alpha=0.8,
                    hover_line_color="white",
                    legend_label='Drizzle'
                )
                fig.add_tools(
                    mpl.HoverTool(tooltips=None, renderers=[cr_yes], mode='hline')
                )

            fig.add_tools(
                mpl.HoverTool(tooltips=None, renderers=[cr_no], mode='hline')
            )

            # Legend styling
            fig.legend.location = 'top_left'
            fig.legend.label_text_color = 'white'
            fig.legend.background_fill_color = 'black'
            fig.legend.background_fill_alpha = 0.2
            fig.legend.border_line_color = 'white'
            fig.legend.border_line_alpha = 0.15
            cr = cr_no
        else:
            cr = fig.scatter(
                x_data,
                y_data,
                color='powderblue',
                fill_alpha=0.3,
                line_alpha=0.3,
                size=8,
                line_width=1.,
                hover_fill_color="midnightblue",
                hover_alpha=0.5,
                hover_line_color="white",
            )

        #   Add hover
        fig.add_tools(
            mpl.HoverTool(tooltips=None, renderers=[cr], mode='hline')
        )

        # x_labels = {'jd':'JD [d]', 'data':'Date'}
        # x_labels = {'jd':'Time', 'date':'Date'}
        y_labels = {
            'temperature': 'Temperature [°C]',
            'pressure': 'Pressure [hPa]',
            'humidity': 'Humidity [%]',
            'illuminance': 'Illuminance [lx]',
            'wind_speed': 'Wind speed [m/s]',
            'rain': 'Rain [mm/m/m]',
        }

        #   Deactivate default drag behaviour
        fig.toolbar.active_drag = None

        #   Set labels etc.
        fig.toolbar.logo = None

        fig.background_fill_alpha = 0.
        fig.border_fill_alpha = 0.

        fig.xgrid.grid_line_alpha = 0.3
        fig.ygrid.grid_line_alpha = 0.3
        fig.xgrid.grid_line_dash = [6, 4]
        fig.ygrid.grid_line_dash = [6, 4]

        fig.yaxis.axis_label = y_labels[y_identifier]
        fig.xaxis.axis_label = x_label
        # fig.xaxis.axis_label = x_labels[x_identifier]

        fig.yaxis.axis_label_text_font_size = '11pt'
        fig.xaxis.axis_label_text_font_size = '11pt'
        fig.xaxis.axis_label_text_color = "white"
        fig.yaxis.axis_label_text_color = "white"
        fig.xaxis.major_label_text_color = "white"
        fig.yaxis.major_label_text_color = "white"
        fig.xaxis.axis_line_color = "white"
        fig.yaxis.axis_line_color = "white"
        fig.xaxis.minor_tick_line_color = "white"
        fig.yaxis.minor_tick_line_color = "white"
        fig.xaxis.major_tick_line_color = "white"
        fig.yaxis.major_tick_line_color = "white"

        fig.min_border = 5

        fig_dict[y_identifier] = fig

    return fig_dict


def additional_plots(plot_range=1., time_resolution=120., start_dt=None, end_dt=None):
    """
        Create additional plots that are hidden by default on the dashboard.

        - Combined temperature plot: ambient, sky_temp, box_temp
        - Temperature difference plot: (ambient - sky_temp)
    """
    start_jd, end_jd = _jd_range(plot_range, start_dt, end_dt)

    pre_binned = False
    if should_use_postgres_binning(plot_range, start_dt, end_dt):
        data = fetch_binned_rows(
            start_jd, end_jd, time_resolution, ADDITIONAL_PG_COLUMNS,
        )
        pre_binned = data.size > 0
    else:
        rows = list(
            Dataset.objects.filter(jd__range=[start_jd, end_jd])
            .order_by('jd')
            .values_list(
                'jd', *ADDITIONAL_PG_COLUMNS,
            )[:MAX_PLOT_ROWS + 1]
        )
        figs = {}
        if len(rows) > MAX_PLOT_ROWS:
            figs['note'] = _plots_too_large_note(len(rows))
            return figs
        data = np.array(rows) if rows else np.array([])

    figs = {}
    if data.size == 0:
        return figs

    jd_vals = data[:, 0]
    temp_vals = data[:, 1]
    humi_vals = data[:, 2]
    sky_vals = data[:, 3]
    box_vals = data[:, 4]

    #   Helper to bin a single series
    def bin_series(x_jd, y_values, agg_func):
        if pre_binned:
            return x_jd, y_values
        ts = TimeSeries(time=Time(x_jd, format='jd'), data={'data': y_values})
        if len(ts) > 1:
            ts_binned = aggregate_downsample(
                ts,
                time_bin_size=float(time_resolution) * u.s,
                aggregate_func=agg_func,
            )
            x_binned = ts_binned['time_bin_start'].value
            y_binned = ts_binned['data'].value
            mask = np.invert(y_binned.mask)
            return x_binned[mask], y_binned[mask]
        return x_jd, y_values

    #   Bin series (median for temps)
    x_t, y_temp = bin_series(jd_vals, temp_vals, np.nanmedian)
    x_h, y_humi = bin_series(jd_vals, humi_vals, np.nanmedian)
    x_s, y_sky = bin_series(jd_vals, sky_vals, np.nanmedian)
    x_b, y_box = bin_series(jd_vals, box_vals, np.nanmedian)

    #   Convert x to localized datetimes for plotting
    x_t_dt = jd_array_to_local_dt(x_t)
    x_h_dt = jd_array_to_local_dt(x_h)
    x_s_dt = jd_array_to_local_dt(x_s)
    x_b_dt = jd_array_to_local_dt(x_b)

    #   Combined temperature plot
    tools = [
        mpl.PanTool(), mpl.WheelZoomTool(), mpl.BoxZoomTool(), mpl.ResetTool()
    ]
    fig_temp = bpl.figure(
        sizing_mode='scale_width', aspect_ratio=2, tools=tools,
    )

    #   Styles
    ambient_color = "#4FC3F7"  # light blue
    sky_color = "#FF7043"      # orange
    box_color = "#BDBDBD"      # grey (less prominent)

    fig_temp.line(x_t_dt, y_temp, line_width=2, color=ambient_color, legend_label='Ambient')
    fig_temp.line(x_s_dt, y_sky, line_width=2, color=sky_color, legend_label='Sky')
    fig_temp.line(x_b_dt, y_box, line_width=1, color=box_color, alpha=0.8, legend_label='Box')

    #   Dew point (computed from temperature and humidity)
    def align_series(x1, y1, x2, y2):
        if len(x1) == len(x2) and np.allclose(x1, x2, equal_nan=False):
            return x1, y1, y2
        common, idx1, idx2 = np.intersect1d(x1, x2, assume_unique=False, return_indices=True)
        return common, y1[idx1], y2[idx2]

    x_common, temp_common, humi_common = align_series(x_t, y_temp, x_h, y_humi)
    if len(x_common):
        # Magnus formula (over water)
        a = 17.62
        b = 243.12
        humi_safe = np.clip(humi_common, 0.1, 100.0)
        gamma = (a * temp_common) / (b + temp_common) + np.log(humi_safe / 100.0)
        dew_point = (b * gamma) / (a - gamma)
        x_dp_dt = jd_array_to_local_dt(x_common)
        fig_temp.line(x_dp_dt, dew_point, line_width=2, color="#80DEEA", line_dash="dashed", legend_label='Dew point')

    #   Axis/formatting
    fig_temp.xaxis.formatter = mpl.DatetimeTickFormatter()
    fig_temp.xaxis.formatter.context = mpl.RELATIVE_DATETIME_CONTEXT()
    fig_temp.yaxis.axis_label = 'Temperature [°C]'
    fig_temp.toolbar.active_drag = None
    fig_temp.toolbar.logo = None
    fig_temp.background_fill_alpha = 0.
    fig_temp.border_fill_alpha = 0.
    fig_temp.xgrid.grid_line_alpha = 0.3
    fig_temp.ygrid.grid_line_alpha = 0.3
    fig_temp.xgrid.grid_line_dash = [6, 4]
    fig_temp.ygrid.grid_line_dash = [6, 4]
    fig_temp.xaxis.axis_label_text_color = "white"
    fig_temp.yaxis.axis_label_text_color = "white"
    fig_temp.xaxis.major_label_text_color = "white"
    fig_temp.yaxis.major_label_text_color = "white"
    fig_temp.xaxis.axis_line_color = "white"
    fig_temp.yaxis.axis_line_color = "white"
    fig_temp.xaxis.minor_tick_line_color = "white"
    fig_temp.yaxis.minor_tick_line_color = "white"
    fig_temp.xaxis.major_tick_line_color = "white"
    fig_temp.yaxis.major_tick_line_color = "white"
    fig_temp.min_border = 5
    fig_temp.legend.location = 'top_left'
    fig_temp.legend.label_text_color = 'white'
    # Make legend background semi-transparent and subtle
    fig_temp.legend.background_fill_color = 'black'
    fig_temp.legend.background_fill_alpha = 0.25
    fig_temp.legend.border_line_color = 'white'
    fig_temp.legend.border_line_alpha = 0.2

    figs['temp_combined'] = fig_temp

    #   Difference plot (ambient - sky)
    x_d, y_d = bin_series(jd_vals, (temp_vals - sky_vals), np.nanmedian)
    x_d_dt = jd_array_to_local_dt(x_d)

    fig_diff = bpl.figure(
        sizing_mode='scale_width', aspect_ratio=2, tools=tools,
    )
    fig_diff.line(x_d_dt, y_d, line_width=2, color="#66BB6A")
    fig_diff.xaxis.formatter = mpl.DatetimeTickFormatter()
    fig_diff.xaxis.formatter.context = mpl.RELATIVE_DATETIME_CONTEXT()
    fig_diff.yaxis.axis_label = 'Ambient - Sky [°C]'
    fig_diff.toolbar.active_drag = None
    fig_diff.toolbar.logo = None
    fig_diff.background_fill_alpha = 0.
    fig_diff.border_fill_alpha = 0.
    fig_diff.xgrid.grid_line_alpha = 0.3
    fig_diff.ygrid.grid_line_alpha = 0.3
    fig_diff.xgrid.grid_line_dash = [6, 4]
    fig_diff.ygrid.grid_line_dash = [6, 4]
    fig_diff.xaxis.axis_label_text_color = "white"
    fig_diff.yaxis.axis_label_text_color = "white"
    fig_diff.xaxis.major_label_text_color = "white"
    fig_diff.yaxis.major_label_text_color = "white"
    fig_diff.xaxis.axis_line_color = "white"
    fig_diff.yaxis.axis_line_color = "white"
    fig_diff.xaxis.minor_tick_line_color = "white"
    fig_diff.yaxis.minor_tick_line_color = "white"
    fig_diff.xaxis.major_tick_line_color = "white"
    fig_diff.yaxis.major_tick_line_color = "white"
    fig_diff.min_border = 5

    figs['temp_sky_diff'] = fig_diff

    if data.size:
        jd_aq = data[:, 0]
        pm1_vals = data[:, 5]
        pm25_vals = data[:, 6]
        pm10_vals = data[:, 7]

        x_1, y_pm1 = bin_series(jd_aq, pm1_vals, np.nanmedian)
        x_25, y_pm25 = bin_series(jd_aq, pm25_vals, np.nanmedian)
        x_10, y_pm10 = bin_series(jd_aq, pm10_vals, np.nanmedian)

        x_1_dt = jd_array_to_local_dt(x_1)
        x_25_dt = jd_array_to_local_dt(x_25)
        x_10_dt = jd_array_to_local_dt(x_10)

        tools_aq = [mpl.PanTool(), mpl.WheelZoomTool(), mpl.BoxZoomTool(), mpl.ResetTool()]
        fig_aq = bpl.figure(
            sizing_mode='scale_width', aspect_ratio=2, tools=tools_aq,
        )

        pm1_color = "#81C784"    # green
        pm25_color = "#FFB74D"   # orange
        pm10_color = "#4DD0E1"   # teal

        fig_aq.line(x_1_dt, y_pm1, line_width=2, color=pm1_color, legend_label='PM1.0 [ug/m3]')
        fig_aq.line(x_25_dt, y_pm25, line_width=2, color=pm25_color, legend_label='PM2.5 [ug/m3]')
        fig_aq.line(x_10_dt, y_pm10, line_width=2, color=pm10_color, legend_label='PM10 [ug/m3]')

        # Formatting
        fig_aq.xaxis.formatter = mpl.DatetimeTickFormatter()
        fig_aq.xaxis.formatter.context = mpl.RELATIVE_DATETIME_CONTEXT()
        if fig_aq.yaxis:
            fig_aq.yaxis[0].axis_label = 'Particulate Matter [ug/m3]'
        fig_aq.toolbar.active_drag = None
        fig_aq.toolbar.logo = None
        fig_aq.background_fill_alpha = 0.
        fig_aq.border_fill_alpha = 0.
        fig_aq.xgrid.grid_line_alpha = 0.3
        fig_aq.ygrid.grid_line_alpha = 0.3
        fig_aq.xgrid.grid_line_dash = [6, 4]
        fig_aq.ygrid.grid_line_dash = [6, 4]
        fig_aq.xaxis.axis_label_text_color = "white"
        fig_aq.yaxis.axis_label_text_color = "white"
        fig_aq.xaxis.major_label_text_color = "white"
        fig_aq.yaxis.major_label_text_color = "white"
        fig_aq.xaxis.axis_line_color = "white"
        fig_aq.yaxis.axis_line_color = "white"
        fig_aq.xaxis.minor_tick_line_color = "white"
        fig_aq.yaxis.minor_tick_line_color = "white"
        fig_aq.xaxis.major_tick_line_color = "white"
        fig_aq.yaxis.major_tick_line_color = "white"
        fig_aq.min_border = 5
        fig_aq.legend.location = 'top_left'
        fig_aq.legend.label_text_color = 'white'
        fig_aq.legend.background_fill_color = 'black'
        fig_aq.legend.background_fill_alpha = 0.25
        fig_aq.legend.border_line_color = 'white'
        fig_aq.legend.border_line_alpha = 0.2

        figs['air_quality'] = fig_aq

        uv_vals = data[:, 8]
        x_uv, y_uv = bin_series(jd_aq, uv_vals, np.nanmedian)
        x_uv_dt = jd_array_to_local_dt(x_uv)

        fig_uv = bpl.figure(
            sizing_mode='scale_width', aspect_ratio=2, tools=tools_aq,
        )
        fig_uv.line(x_uv_dt, y_uv, line_width=2, color="#FFD54F", legend_label='UV Index')
        fig_uv.xaxis.formatter = mpl.DatetimeTickFormatter()
        fig_uv.xaxis.formatter.context = mpl.RELATIVE_DATETIME_CONTEXT()
        if fig_uv.yaxis:
            fig_uv.yaxis[0].axis_label = 'UV Index'
        fig_uv.toolbar.active_drag = None
        fig_uv.toolbar.logo = None
        fig_uv.background_fill_alpha = 0.
        fig_uv.border_fill_alpha = 0.
        fig_uv.xgrid.grid_line_alpha = 0.3
        fig_uv.ygrid.grid_line_alpha = 0.3
        fig_uv.xgrid.grid_line_dash = [6, 4]
        fig_uv.ygrid.grid_line_dash = [6, 4]
        fig_uv.xaxis.axis_label_text_color = "white"
        fig_uv.yaxis.axis_label_text_color = "white"
        fig_uv.xaxis.major_label_text_color = "white"
        fig_uv.yaxis.major_label_text_color = "white"
        fig_uv.xaxis.axis_line_color = "white"
        fig_uv.yaxis.axis_line_color = "white"
        fig_uv.xaxis.minor_tick_line_color = "white"
        fig_uv.yaxis.minor_tick_line_color = "white"
        fig_uv.xaxis.major_tick_line_color = "white"
        fig_uv.yaxis.major_tick_line_color = "white"
        fig_uv.min_border = 5
        fig_uv.legend.location = 'top_left'
        fig_uv.legend.label_text_color = 'white'
        fig_uv.legend.background_fill_color = 'black'
        fig_uv.legend.background_fill_alpha = 0.25
        fig_uv.legend.border_line_color = 'white'
        fig_uv.legend.border_line_alpha = 0.2

        figs['uv_index'] = fig_uv

    return figs


def default_plots(*, fresh=False, **kwargs):
    """
    Render main dashboard plots (Bokeh script + div dict).

    Additional plots are loaded lazily via the API endpoint.
    """
    def build_figures(**plot_kwargs):
        return main_plots('jd', MAIN_PLOT_IDENTIFIERS, **plot_kwargs)

    return _render_with_cache(
        cache_namespace='main',
        plot_identifiers=MAIN_PLOT_IDENTIFIERS,
        build_figures=build_figures,
        fresh=fresh,
        **kwargs,
    )


def additional_plots_components(*, fresh=False, **kwargs):
    """Render additional dashboard plots (lazy-loaded in the UI)."""
    def build_figures(**plot_kwargs):
        return additional_plots(**plot_kwargs)

    return _render_with_cache(
        cache_namespace='additional',
        plot_identifiers=ADDITIONAL_PLOT_IDENTIFIERS,
        build_figures=build_figures,
        fresh=fresh,
        **kwargs,
    )

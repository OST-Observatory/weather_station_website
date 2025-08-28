import os

import datetime

import time

import astropy.units as u
from astropy.time import Time
from astropy.timeseries import TimeSeries, aggregate_downsample

import numpy as np

from bokeh import models as mpl
from bokeh import plotting as bpl
from bokeh.embed import components
from bokeh.resources import CDN

from .models import Dataset


# Constants
WIND_ROTATIONS_TO_MPS = 0.14
RAIN_TO_MM_PER_M2_FACTOR = 0.07534
RAIN_FLAG_THRESHOLD = 0.5

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
    #   Determine JD range from preset or custom datetimes
    #   Current JD
    jd_current = Time(datetime.datetime.now(datetime.timezone.utc)).jd
    if start_dt is not None and end_dt is not None:
        start_jd = Time(start_dt).jd
        end_jd = Time(end_dt).jd
    else:
        start_jd = jd_current - float(plot_range)
        end_jd = jd_current

    #   Get requested range of data (include is_raining once if rain is requested)
    include_flags = 'rain' in y_identifier_list
    base_fields = [x_identifier, *y_identifier_list]
    if include_flags:
        base_fields.append('is_raining')

    data_range = Dataset.objects.filter(
        jd__range=[start_jd, end_jd]
    ).order_by('jd')
    data = np.array(data_range.values_list(*base_fields))

    #   Verify that data was returned
    if data.size == 0:
        no_data = True
        x_data_original = None
    else:
        no_data = False
        x_data_original = data[:, 0]
        # If we included flags, last column is is_raining aligned with x_data_original
        flag_series_raw = None
        if include_flags:
            flag_series_raw = data[:, len(y_identifier_list) + 1 - 0]  # last column

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

            #   Binned time series
            if len(time_series) > 1:
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
            os.environ['TZ'] = 'Europe/Berlin'
            time.tzset()
            daylight_saving_time_correction = time.localtime().tm_isdst
            delta = datetime.timedelta(
                hours=time.timezone / 3600 * -1 + daylight_saving_time_correction
            )
            x_data = Time(x_data, format='jd').datetime + delta
            fig.xaxis.formatter = mpl.DatetimeTickFormatter()
            fig.xaxis.formatter.context = mpl.RELATIVE_DATETIME_CONTEXT()
            if daylight_saving_time_correction:
                x_label = 'Time [CEST]'
            else:
                x_label = 'Time [CET]'
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
    #   Determine JD range
    jd_current = Time(datetime.datetime.now(datetime.timezone.utc)).jd
    if start_dt is not None and end_dt is not None:
        start_jd = Time(start_dt).jd
        end_jd = Time(end_dt).jd
    else:
        start_jd = jd_current - float(plot_range)
        end_jd = jd_current

    #   Retrieve data range
    data_qs = Dataset.objects.filter(
        jd__range=[start_jd, end_jd]
    ).order_by('jd').values_list(
        'jd', 'temperature', 'humidity', 'sky_temp', 'box_temp'
    )

    data = np.array(list(data_qs)) if data_qs else np.array([])

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
    os.environ['TZ'] = 'Europe/Berlin'
    time.tzset()
    dst = time.localtime().tm_isdst
    delta = datetime.timedelta(hours=time.timezone / 3600 * -1 + dst)

    def jd_to_local_dt(x):
        return Time(x, format='jd').datetime + delta

    x_t_dt = jd_to_local_dt(x_t)
    x_h_dt = jd_to_local_dt(x_h)
    x_s_dt = jd_to_local_dt(x_s)
    x_b_dt = jd_to_local_dt(x_b)

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
        x_dp_dt = jd_to_local_dt(x_common)
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
    x_d_dt = jd_to_local_dt(x_d)

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

    #   Air quality plot: CO2 (left axis, ppm) and TVOC (right axis, ppb)
    aq_qs = Dataset.objects.filter(
        jd__range=[start_jd, end_jd]
    ).order_by('jd').values_list('jd', 'co2_ppm', 'tvoc_ppb')
    aq_data = np.array(list(aq_qs)) if aq_qs else np.array([])

    if aq_data.size:
        jd_aq = aq_data[:, 0]
        co2_vals = aq_data[:, 1]
        tvoc_vals = aq_data[:, 2]

        x_c, y_co2 = bin_series(jd_aq, co2_vals, np.nanmedian)
        x_v, y_tvoc = bin_series(jd_aq, tvoc_vals, np.nanmedian)

        x_c_dt = jd_to_local_dt(x_c)
        x_v_dt = jd_to_local_dt(x_v)

        tools_aq = [mpl.PanTool(), mpl.WheelZoomTool(), mpl.BoxZoomTool(), mpl.ResetTool()]
        fig_aq = bpl.figure(
            sizing_mode='scale_width', aspect_ratio=2, tools=tools_aq,
        )

        # Colors
        co2_color = "#81C784"   # green
        tvoc_color = "#4DD0E1"  # teal

        # Left axis: CO2 [ppm]
        fig_aq.line(x_c_dt, y_co2, line_width=2, color=co2_color, legend_label='CO2 [ppm]')

        # Right axis: TVOC [ppb]
        fig_aq.extra_y_ranges = {"tvoc": mpl.Range1d(start=float(np.nanmin(y_tvoc)) if len(y_tvoc) else 0.0,
                                                       end=float(np.nanmax(y_tvoc)) if len(y_tvoc) else 1.0)}
        fig_aq.add_layout(mpl.LinearAxis(y_range_name="tvoc", axis_label="TVOC [ppb]",
                                         axis_label_text_color="white",
                                         major_label_text_color="white",
                                         axis_line_color="white",
                                         major_tick_line_color="white",
                                         minor_tick_line_color="white"), 'right')
        fig_aq.line(x_v_dt, y_tvoc, line_width=2, color=tvoc_color, y_range_name="tvoc", legend_label='TVOC [ppb]')

        # Formatting
        fig_aq.xaxis.formatter = mpl.DatetimeTickFormatter()
        fig_aq.xaxis.formatter.context = mpl.RELATIVE_DATETIME_CONTEXT()
        # Set left axis label explicitly (avoid overwriting right axis label)
        if fig_aq.yaxis:
            fig_aq.yaxis[0].axis_label = 'CO2 [ppm]'
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

    return figs


def default_plots(**kwargs):
    """
        Wrapper that crates all default plots and returns the html and js

        Parameters
        ----------
        kwargs              :
            Keyword arguments to pass to the next function


        Returns
        -------
        script              : UTF-8 encoded HTML

        div                 : UTF-8 encoded javascript
    """
    #   Parameters to plot
    y_identifier = [
        'temperature',
        'pressure',
        'humidity',
        'illuminance',
        'wind_speed',
        'rain',
    ]

    #   Create plots
    figs = main_plots('jd', y_identifier, **kwargs)

    #   Create additional plots (appended, hidden by default in UI)
    figs.update(additional_plots(
        plot_range=kwargs.get('plot_range', 1.),
        time_resolution=kwargs.get('time_resolution', 120.),
        start_dt=kwargs.get('start_dt'),
        end_dt=kwargs.get('end_dt'),
    ))

    #   Create HTML and JS content
    return components(figs, CDN)

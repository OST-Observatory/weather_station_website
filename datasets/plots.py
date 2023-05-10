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

from .models import dataset


def scatter_plot(x_identifier, y_identifier, plot_range=1.,
                 time_resolution=60.):
    '''
        Scatter plot

        Parameters
        ----------
        x_identifier        : `string`
            String that characterizes the model parameter field

        y_identifier        : `string`
            String that characterizes the model parameter field

        plot_range          : `float`, optional
            Time to plot in days.
            Default is ``1``.

        time_resolution     : `float`, optional
            Time resolution of the plot in seconds. The data is binned
            accordingly.
            Default is ``60``.


        Returns
        -------
        fig                 : `bokeh.plotting.figure`
            Figure
    '''
    #   Current JD
    # jd_current = Time(datetime.datetime.now()).jd
    jd_current = Time(datetime.datetime.now(datetime.timezone.utc)).jd

    #   Get requested range of data
    data_range = dataset.objects.filter(
        jd__range=[jd_current - float(plot_range), jd_current]
        )
    x_data = np.array(data_range.values_list(x_identifier, flat = True))
    y_data = np.array(data_range.values_list(y_identifier, flat = True))


    #   Make time series
    ts = TimeSeries(
        time=Time(x_data, format='jd'),
        data={'data': y_data}
        )

    #   Binned time series
    if len(ts):
        ts_average = aggregate_downsample(
            ts,
            time_bin_size = float(time_resolution) * u.s,
            )
        x_data = ts_average['time_bin_start'].value
        y_data = ts_average['data'].value

        mask = np.invert(y_data.mask)

        x_data = x_data[mask]
        y_data = y_data[mask]

    #   Tools attached to the figure
    tools = [
        mpl.PanTool(),
        mpl.WheelZoomTool(),
        mpl.BoxZoomTool(),
        mpl.ResetTool(),
        ]

    #   Set Y range - use extrema or data range
    y_range_extrema = {
        'temperature':(-40., 60.),
        'pressure':(900., 1080.),
        'humidity':(-5., 105.),
        'illuminance':(0.0001, 15000.),
        'wind_speed':(-10., 305.),
        'rain':(-5., 10005.),
        }

    y_data_max = np.max(y_data)
    y_data_min = np.min(y_data)
    y_data_max = y_data_max + 0.05 * y_data_max
    y_data_min = y_data_min - 0.05 * y_data_min

    y_extrema = y_range_extrema[y_identifier]

    y_range = (
        max(y_extrema[0], y_data_min), min(y_extrema[1], y_data_max)
        )

    #   Setup figure
    fig = bpl.figure(
        sizing_mode='scale_width',
        aspect_ratio=2,
        tools=tools,
        y_range=y_range,
        )

    #   Convert JD to datetime object and set x-axis formatter
    if x_identifier == 'jd':
        os.environ['TZ'] = 'Europe/Berlin'
        time.tzset()
        delta = datetime.timedelta(hours=time.timezone/3600*-1+time.daylight)
        x_data = Time(x_data, format='jd').datetime + delta
        fig.xaxis.formatter = mpl.DatetimeTickFormatter()
        fig.xaxis.formatter.context = mpl.RELATIVE_DATETIME_CONTEXT()
        if time.daylight:
            x_label = 'Time [CEST]'
        else:
            x_label = 'Time [CET]'
    else:
        x_label = 'Date'

    if y_identifier in ['temperature', 'pressure', 'humidity', 'rain']:
        fig.line(
            x_data,
            y_data,
            line_width=2,
            color="powderblue",
            )
    else:
        #   Prepare hover...
        fig.circle(x_data, y_data, size=3, color='white', alpha=0.1, name='hover')

        #   Plot data
        fig.circle(
            x_data,
            y_data,
            color='powderblue',
            fill_alpha=0.3,
            line_alpha=1.0,
            size=4,
            line_width=1.,
            )

    # x_labels = {'jd':'JD [d]', 'data':'Date'}
    # x_labels = {'jd':'Time', 'date':'Date'}
    y_labels = {
        'temperature':'Temperature [°C]',
        'pressure':'Pressure [hPa]',
        'humidity':'Humidity [%]',
        'illuminance':'Illuminance [lx]',
        # 'wind_speed':'Wind velocity [m/s]',
        'wind_speed':'Wind velocity [rotations]',
        'rain':'Rain [arbitrary]',
        }

    #   Set labels etc.
    fig.toolbar.logo = None

    fig.background_fill_alpha = 0.
    fig.border_fill_color = "rgba(0,0,0,0.)"

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

    return fig


def default_plots(**kwargs):
    '''
        Wrapper that crates all default plots and returns the html and js

        Parameters
        ----------
        kwargs              :
            Keyword arguments to pass to the next function


        Returns
        -------
        script              : UTF-8 encoded HTML

        div                 : UTF-8 encoded javascript
    '''
    #   Parameters to plot
    y_identifier=[
        'temperature',
        'pressure',
        'humidity',
        'illuminance',
        'wind_speed',
        'rain',
        ]

    #   Create plots
    figs = {}
    for y_id in y_identifier:
        fig = scatter_plot(
            x_identifier='jd',
            y_identifier=y_id,
            **kwargs,
            )

        figs[y_id] = fig


    #   Create HTML and JS content
    return components(figs, CDN)


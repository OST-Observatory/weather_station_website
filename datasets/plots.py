import datetime

from astropy.time import Time
from astropy.timeseries import TimeSeries

import numpy as np

from bokeh import models as mpl
from bokeh import plotting as bpl
from bokeh.embed import components
from bokeh.resources import CDN

from .models import dataset


def scatter_plot(x_identifier, y_identifier, plot_range=1.,
                 timezone_hour_delta=1):
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

        timezone_hour_delta : `integer`, optional
            Delta time in h between display timezone and UTC

        Returns
        -------
        fig                 : `bokeh.plotting.figure`
            Figure
    '''
    #   Current JD
    jd_current = Time(datetime.datetime.now()).jd
    # jd_current = Time(datetime.datetime.now(datetime.timezone.utc)).jd

    #   Get requested range of data
    data_range = dataset.objects.filter(
        jd__range=[jd_current - plot_range, jd_current]
        )
    x_data = np.array(data_range.values_list(x_identifier, flat = True))
    y_data = np.array(data_range.values_list(y_identifier, flat = True))

    #   Tools attached to the figure
    tools = [
        mpl.PanTool(),
        mpl.WheelZoomTool(),
        mpl.BoxZoomTool(),
        mpl.ResetTool(),
        ]

    #   Setup figure
    fig = bpl.figure(sizing_mode='scale_width', aspect_ratio=2, tools=tools)

    #   Convert JD to datetime object and set x-axis formatter
    if x_identifier == 'jd':
        delta = datetime.timedelta(hours=timezone_hour_delta)
        x_data = Time(x_data, format='jd').datetime + delta
        fig.xaxis.formatter = mpl.DatetimeTickFormatter()
        fig.xaxis.formatter.context = mpl.RELATIVE_DATETIME_CONTEXT()

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
    x_labels = {'jd':'Time', 'data':'Date'}
    y_labels = {
        'temperature':'Temperature [°C]',
        'pressure':'Pressure [hPa]',
        'humidity':'Humidity [g/m3]',
        'illuminance':'Illuminance [lx]',
        'wind_speed':'Wind velocity [m/s]',
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
    fig.xaxis.axis_label = x_labels[x_identifier]

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


def default_plots(plot_range=1., timezone_hour_delta=1):
    '''
        Wrapper that crates all default plots and returns the html and js

        Parameters
        ----------
        plot_range          : `float`, optional
            Time to plot in days.
            Default is ``1``.

        timezone_hour_delta : `integer`, optional
            Delta time in h between display timezone and UTC


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
        ]

    #   Create plots
    figs = {}
    for y_id in y_identifier:
        fig = scatter_plot(
            x_identifier='jd',
            y_identifier=y_id,
            plot_range=plot_range,
            timezone_hour_delta=timezone_hour_delta,
            )

        figs[y_id] = fig


    #   Create HTML and JS content
    return components(figs, CDN)


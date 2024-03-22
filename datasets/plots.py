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


def main_plots(x_identifier, y_identifier_list, plot_range=1.,
               time_resolution=120.):
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
    #   Current JD
    # jd_current = Time(datetime.datetime.now()).jd
    jd_current = Time(datetime.datetime.now(datetime.timezone.utc)).jd

    #   Get requested range of data
    data_range = Dataset.objects.filter(
        jd__range=[jd_current - float(plot_range), jd_current]
    )
    data = np.array(data_range.values_list(x_identifier, *y_identifier_list))

    #   Verify that data was returned
    if data.size == 0:
        no_data = True
        x_data_original = None
    else:
        no_data = False
        x_data_original = data[:, 0]

    #   Set Y range - use extrema or data range
    y_range_extrema = {
        'temperature': (-40., 60.),
        'pressure': (900., 1080.),
        'humidity': (0., 100.),
        'illuminance': (0., 13000.),
        'wind_speed': (0., 300.),
        'rain': (0., 500.),
    }

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
                    time_series_sum = aggregate_downsample(
                        time_series,
                        time_bin_size=float(time_resolution) * u.s,
                        aggregate_func=np.nansum,
                    )
                    x_data = time_series_sum['time_bin_start'].value
                    y_data = time_series_sum['data'].value
                    #   Convert rain to mm/m^2
                    #   In the database, the amount of rain is given in units of
                    #   1.25 ml (each dipper change is approximately 1.25 ml). The
                    #   diameter of the rain gauge is about 130 mm. So the surface
                    #   pi*r^2 is 132.73 cm^2. So per m^2 (=10000cm^2) we have
                    #   to multiply by a factor of about 75.34. The conversion factor from ml/m^2 to mm/m^2 is 1/1000.
                    y_data = y_data * 0.07534
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
                    y_data = y_data * 1.4

                mask = np.invert(y_data.mask)

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
        y_extrema = y_range_extrema[y_identifier]

        y_range = (
            max(y_extrema[0], y_data_min), min(y_extrema[1], y_data_max)
        )
        y_range = (
            y_range[0] - 0.01 * y_range[0], y_range[1] + 0.01 * y_range[1]
        )

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

        cr = fig.circle(
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

        fig_dict[y_identifier] = fig

    return fig_dict


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

    #   Create HTML and JS content
    return components(figs, CDN)

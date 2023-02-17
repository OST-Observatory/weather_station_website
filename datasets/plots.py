import datetime

from astropy.time import Time

import numpy as np

from bokeh import models as mpl
from bokeh import plotting as bpl
from bokeh.embed import components
from bokeh.resources import CDN

from .models import dataset


def scatter_plot(x_identifier, y_identifier, plot_range=1.):
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

        Returns
        -------
        fig                 : `bokeh.plotting.figure`
            Figure
    '''
    #   Current JD
    jd_current = Time(datetime.datetime.now()).jd

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
    fig = bpl.figure(width=1000, height=400, tools=tools)

    #   Prepare hover...
    fig.circle(x_data, y_data, size=8, color='white', alpha=0.1, name='hover')

    #   Plot data
    fig.circle(
        x_data,
        y_data,
        color='powderblue',
        fill_alpha=0.3,
        line_alpha=1.0,
        size=9,
        line_width=1.5,
        )

    x_labels = {'jd':'JD [d]', 'data':'Date'}
    y_labels = {
        'temperature':'Temperature [K]',
        'pressure':'Pressure [hPa]',
        'humidity':'Humidity [g/m3]',
        'illuminance':'Illuminance [lx]',
        'wind_speed':'Wind velocity [m/s]',
        }

    #   Set labels etc.
    fig.toolbar.logo = None
    fig.yaxis.axis_label = y_labels[y_identifier]
    fig.xaxis.axis_label = x_labels[x_identifier]
    fig.yaxis.axis_label_text_font_size = '10pt'
    fig.xaxis.axis_label_text_font_size = '10pt'
    fig.min_border = 5

    return fig


def default_plots(plot_range=1.):
    '''
        Wrapper that crates all default plots and returns the html and js

        Parameters
        ----------
        plot_range          : `float`, optional
            Time to plot in days.
            Default is ``1``.

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
        fig = scatter_plot(x_identifier='jd', y_identifier=y_id)

        figs[y_id] = fig


    #   Create HTML and JS content
    return components(figs, CDN)


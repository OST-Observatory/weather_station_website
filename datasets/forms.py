from django import forms


class ParameterPlotForm(forms.Form):
    #   Time resolution of the plot in seconds
    time_resolution = forms.ChoiceField(
        label='Time resolution',
        required=True,
        widget=forms.Select(),
        choices=(
            (1, '1s'),
            (10, '10s'),
            (30, '30s'),
            (60, '1min'),
            (120, '2min'),
            (300, '5min'),
            (600, '10min'),
            (1800, '30min'),
            (3600, '1h'),
            (3600, '1h'),
            (10800, '3h'),
            (21600, '6h'),
            (86400, '1d'),
            )
        )

    #   Plot range in days
    plot_range = forms.ChoiceField(
        label='Plot range',
        required=True,
        widget=forms.Select(),
        choices=(
            (0.041666667, '1h'),
            (0.083333333, '2h'),
            (0.25, '6h'),
            (0.5, '12h'),
            (1, '1d'),
            (7, '7d'),
            (14, '14d'),
            (30, '30d'),
            (90, '90d'),
            (182.625, '0.5yr'),
            (365.25, '1yr'),
            )
        )

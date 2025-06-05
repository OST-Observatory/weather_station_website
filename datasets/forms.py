from django import forms
from django.utils import timezone
from datetime import timedelta


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
            (7200, '2h'),
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


class DateRangeForm(forms.Form):
    start_date = forms.DateField(
        label='Start date',
        required=True,
        widget=forms.DateInput(attrs={
            'type': 'text',
            'pattern': r'\d{4}-\d{2}-\d{2}',
            'placeholder': 'YYYY-MM-DD',
            'class': 'date-input'
        }),
        input_formats=['%Y-%m-%d']  # Only accept YYYY-MM-DD
    )
    
    end_date = forms.DateField(
        label='End date',
        required=True,
        widget=forms.DateInput(attrs={
            'type': 'text',
            'pattern': r'\d{4}-\d{2}-\d{2}',
            'placeholder': 'YYYY-MM-DD',
            'class': 'date-input'
        }),
        input_formats=['%Y-%m-%d']  # Only accept YYYY-MM-DD
    )

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        if start_date and end_date:
            if start_date > end_date:
                raise forms.ValidationError("End date must be after start date")
            
            # Optional: Add maximum range validation
            max_range = timedelta(days=32) 
            if end_date - start_date > max_range:
                raise forms.ValidationError("Date range cannot exceed 32 days")

        return cleaned_data

from django import forms
from django.utils import timezone
from datetime import timedelta, datetime, time as dtime
from django.core.exceptions import ValidationError


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

    #   Plot range in days (preset)
    plot_range = forms.ChoiceField(
        label='Preset time range',
        required=True,
        widget=forms.Select(),
        choices=(
            (0.041666667, '1h'),
            (0.083333333, '2h'),
            (0.25, '6h'),
            (0.5, '12h'),
            (1, '1d'),
            (2, '2d'),
            (3, '3d'),
            (7, '7d'),
            (14, '14d'),
            (30, '30d'),
            (90, '90d'),
            (182.625, '0.5yr'),
            (365.25, '1yr'),
            )
        )

    #   Custom range (dates)
    start_date = forms.DateField(
        label='Start date',
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'date-input'
        }),
        input_formats=['%Y-%m-%d']
    )

    end_date = forms.DateField(
        label='End date',
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'date-input'
        }),
        input_formats=['%Y-%m-%d']
    )

    def clean(self):
        cleaned = super().clean()
        # Decide preset vs custom by presence of dates
        has_custom = cleaned.get('start_date') and cleaned.get('end_date')

        # Derive range in seconds
        if not has_custom:
            try:
                days = float(cleaned.get('plot_range'))
            except Exception:
                raise ValidationError('Invalid preset range.')
            range_seconds = days * 86400.0
            cleaned['start_dt'] = None
            cleaned['end_dt'] = None
        else:
            sd = cleaned.get('start_date')
            ed = cleaned.get('end_date')
            if not sd or not ed:
                raise ValidationError('For custom range please provide start and end date.')
            if ed < sd:
                raise ValidationError('End date must be after start date.')
            # use end of day for end date
            end_dt = datetime.combine(ed, dtime.max)
            end_dt = timezone.make_aware(end_dt)
            start_dt = timezone.make_aware(datetime.combine(sd, dtime.min))
            range_seconds = (end_dt - start_dt).total_seconds()
            if range_seconds <= 0:
                raise ValidationError('Selected time range must be positive.')
            # Practical upper bound for plots (e.g., 120 days)
            max_days = 120
            if range_seconds > max_days * 86400:
                raise ValidationError(f'The selected time range cannot exceed {max_days} days.')
            cleaned['start_dt'] = start_dt
            cleaned['end_dt'] = end_dt

        # Enforce a max number of points for performance
        max_points = 5000
        tr_choice = cleaned.get('time_resolution')
        try:
            tr_seconds = float(tr_choice)
        except Exception:
            raise ValidationError('Invalid time resolution.')
        min_resolution = max(1.0, range_seconds / max_points)

        # Allowed resolutions from choices
        allowed = [
            1, 10, 30, 60, 120, 300, 600, 1800, 3600, 7200, 10800, 21600, 86400
        ]
        # Pick the smallest allowed >= min_resolution
        adjusted = next((opt for opt in allowed if opt >= min_resolution), allowed[-1])
        if tr_seconds < adjusted:
            # Adjust upward to avoid timeouts
            cleaned['time_resolution'] = str(adjusted)
            cleaned['resolution_adjusted'] = True
            cleaned['adjusted_to'] = adjusted
            cleaned['min_resolution'] = min_resolution
        else:
            cleaned['resolution_adjusted'] = False
        return cleaned


class DateRangeForm(forms.Form):
    start_date = forms.DateField(
        label='Start date',
        required=True,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'date-input'
        }),
        input_formats=['%Y-%m-%d']  # Only accept YYYY-MM-DD
    )
    
    end_date = forms.DateField(
        label='End date',
        required=True,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'date-input'
        }),
        input_formats=['%Y-%m-%d']  # Only accept YYYY-MM-DD
    )

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        if start_date and end_date:
            # Calculate the difference in days
            delta = end_date - start_date
            if delta.days > 31:
                raise ValidationError(
                    'The selected time range cannot exceed 31 days.'
                )
            if end_date < start_date:
                raise ValidationError(
                    'End date must be after start date.'
                )
            if end_date > start_date + timedelta(days=31):
                raise ValidationError(
                    'The selected time range cannot exceed 31 days.'
                )

        return cleaned_data

from django.shortcuts import render

from .plots import default_plots


# Create your views here.

def dashboard(request, **kwargs):
    '''
        Collect weather station data, plot those data, and render request
    '''
    #   Create HTML content
    script, div = default_plots()

    #   Make dict with the content
    context = {
        'figures': div,
        'script': script,
        }

    return render(request, 'datasets/dashboard.html', context)

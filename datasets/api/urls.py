from django.urls import path

from .views import (
    CreateDatasetView,
    dataset_detail_not_allowed,
    download_csv,
    get_last_dataset,
)

app_name = 'datasets-api'

urlpatterns = [
    path('last_dataset/', get_last_dataset, name='last_dataset'),
    path('download-csv/', download_csv, name='download-csv'),
    path('datasets/', CreateDatasetView.as_view(), name='dataset-create'),
    path('datasets/<int:pk>/', dataset_detail_not_allowed, name='dataset-detail'),
]

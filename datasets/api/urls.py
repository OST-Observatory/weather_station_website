from django.urls import include, path
from rest_framework import routers
from .views import DatasetViewSet, get_last_dataset, download_csv

router = routers.DefaultRouter()
router.register(r'datasets', DatasetViewSet)

app_name = 'datasets-api'

# Wire up our API using automatic URL routing.
# Place custom endpoints BEFORE router include to avoid router swallowing the path.
urlpatterns = [
    # Custom endpoints
    path('last_dataset/', get_last_dataset, name='last_dataset'),
    path('download-csv/', download_csv, name='download-csv'),
    # Router-generated endpoints
    path('', include(router.urls)),
]

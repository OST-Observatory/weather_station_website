from django.urls import include, path
from rest_framework import routers
from .views import DatasetViewSet, get_last_dataset

router = routers.DefaultRouter()
router.register(r'datasets', DatasetViewSet)

app_name = 'datasets-api'

# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browsable API.
urlpatterns = [
    path('', include(router.urls)),
    # path('api-auth/', include('rest_framework.urls', namespace='rest_framework'))
    #    Last dataset
    path(
        'last_dataset/',
        get_last_dataset,
        name='last_dataset',
    ),
]

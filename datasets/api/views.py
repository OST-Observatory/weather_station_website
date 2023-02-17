from rest_framework import viewsets, permissions

from datasets.models import dataset

from .serializers import DatasetSerializer

class DatasetViewSet(viewsets.ModelViewSet):
    """
        API endpoint that allows datasets to be viewed or edited.
    """
    queryset = dataset.objects.all()
    serializer_class = DatasetSerializer
    permission_classes = [permissions.IsAuthenticated]

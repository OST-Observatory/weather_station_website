from rest_framework import viewsets, permissions

from datasets.models import Dataset

from .serializers import DatasetSerializer


class DatasetViewSet(viewsets.ModelViewSet):
    """
        API endpoint that allows datasets to be viewed or edited.
    """
    queryset = Dataset.objects.all()
    serializer_class = DatasetSerializer
    permission_classes = [permissions.IsAuthenticated]

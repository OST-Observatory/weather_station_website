from rest_framework import viewsets, permissions
from rest_framework.decorators import api_view
from rest_framework.response import Response

from datasets.models import Dataset

from .serializers import DatasetSerializer


class DatasetViewSet(viewsets.ModelViewSet):
    """
        API endpoint that allows datasets to be viewed or edited.
    """
    queryset = Dataset.objects.all()
    serializer_class = DatasetSerializer
    permission_classes = [permissions.IsAuthenticated]


@api_view(['GET'])
def get_last_dataset(request):
    dataset = Dataset.objects.latest("added_on")

    return Response(DatasetSerializer(dataset).data)
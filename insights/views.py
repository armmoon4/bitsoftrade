from rest_framework.decorators import api_view, permission_classes
from rest_framework import permissions
from rest_framework.response import Response
from .services import calculate_metrics
from .serializers import MetricsSnapshotSerializer


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def metrics_view(request):
    """GET /api/insights/metrics/ — returns all 12 metrics, recalculates if stale."""
    from datetime import date
    snapshot = calculate_metrics(request.user, snapshot_date=date.today())
    return Response(MetricsSnapshotSerializer(snapshot).data)





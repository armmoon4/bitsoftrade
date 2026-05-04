from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from drf_spectacular.utils import extend_schema
from learninghub.models import Video
from learninghub.serializers.video import VideoSerializer
from learninghub.permissions import IsAdminOrLearningSubscriber  


@extend_schema(
    request={
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'title': {'type': 'string'},
                'description': {'type': 'string'},
                'video': {'type': 'string', 'format': 'binary'},
                'course': {'type': 'integer'},
                'is_free': {'type': 'boolean'},
                'is_complete': {'type': 'boolean'},
                'is_active': {'type': 'boolean'},
            },
            'required': ['title', 'video', 'course']
        }
    },
    responses={201: VideoSerializer}
)
class VideoListCreateAPIView(generics.ListCreateAPIView):
    queryset = Video.objects.all()
    serializer_class = VideoSerializer
    permission_classes = [IsAdminOrLearningSubscriber]  
    authentication_classes = []
    parser_classes = [MultiPartParser, FormParser]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response({
            'message': 'Video created successfully',
            'video': serializer.data
        }, status=status.HTTP_201_CREATED, headers=headers)


class VideoDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Video.objects.all()
    serializer_class = VideoSerializer
    permission_classes = [IsAdminOrLearningSubscriber]  
    authentication_classes = []

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response({
            'message': 'Video updated successfully',
            'video': serializer.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response({'message': 'Video deleted successfully'},
                        status=status.HTTP_204_NO_CONTENT)
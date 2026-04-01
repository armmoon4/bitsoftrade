from rest_framework import generics, status, permissions #type: ignore
from rest_framework.response import Response #type: ignore

from learninghub.models import Video
from learninghub.serializers.video import VideoSerializer

class VideoListCreateAPIView(generics.ListCreateAPIView):
    queryset = Video.objects.all()
    serializer_class = VideoSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

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
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

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
        return Response({
            'message': 'Video deleted successfully'
        }, status=status.HTTP_204_NO_CONTENT)
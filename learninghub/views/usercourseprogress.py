from rest_framework import generics, status, permissions #type: ignore
from rest_framework.response import Response #type: ignore

from learninghub.models import UserCourseProgress
from learninghub.serializers.usercourseprogress import UserCourseProgressSerializer, UserCourseProgressCreateSerializer

class UserCourseProgressListAPIView(generics.ListAPIView):
    queryset = UserCourseProgress.objects.all()
    serializer_class = UserCourseProgressSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None  

class UserCourseProgressCreateAPIView(generics.CreateAPIView):
    queryset = UserCourseProgress.objects.all()
    serializer_class = UserCourseProgressCreateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        
        return Response({
            'message': 'Course progress created successfully',
            'course_progress': serializer.data
        }, status=status.HTTP_201_CREATED, headers=headers)
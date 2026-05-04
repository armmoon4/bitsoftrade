from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.shortcuts import get_object_or_404
from learninghub.models import UserCourseProgress, Video
from learninghub.serializers.usercourseprogress import (
    UserCourseProgressSerializer,
    UserCourseProgressCreateSerializer,
)
from learninghub.permissions import IsAdminOrLearningSubscriberFull  

User = get_user_model()


class UserCourseProgressListAPIView(generics.ListAPIView):
    serializer_class = UserCourseProgressSerializer
    permission_classes = [IsAdminOrLearningSubscriberFull]  
    authentication_classes = []
    pagination_class = None

    def get_queryset(self):
        if getattr(self.request, 'admin', None):
            return UserCourseProgress.objects.all()
        return UserCourseProgress.objects.filter(user=self.request.user)


class UserCourseProgressCreateAPIView(generics.CreateAPIView):
    queryset = UserCourseProgress.objects.all()
    serializer_class = UserCourseProgressCreateSerializer
    permission_classes = [IsAdminOrLearningSubscriberFull]  
    authentication_classes = []

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response({
            'message': 'Course progress created successfully',
            'course_progress': serializer.data
        }, status=status.HTTP_201_CREATED, headers=headers)


class MarkVideoWatchedAPIView(APIView):
    permission_classes = [IsAdminOrLearningSubscriberFull]  
    authentication_classes = []

    def post(self, request, progress_id, video_id):
        progress = get_object_or_404(UserCourseProgress, pk=progress_id)
        if not getattr(request, 'admin', None) and progress.user != request.user:
            return Response(
                {'error': 'You do not have permission to update this record.'},
                status=status.HTTP_403_FORBIDDEN
            )
        video = get_object_or_404(Video, pk=video_id, course=progress.course)
        progress.videos_watched.add(video)
        total = progress.course.videos.count()
        watched = progress.videos_watched.count()
        if total > 0 and watched >= total and progress.completed_at is None:
            progress.completed_at = timezone.now()
            progress.save(update_fields=['completed_at'])
        serializer = UserCourseProgressSerializer(progress)
        return Response({
            'message': 'Video marked as watched.',
            'course_progress': serializer.data
        }, status=status.HTTP_200_OK)


class UnmarkVideoWatchedAPIView(APIView):
    permission_classes = [IsAdminOrLearningSubscriberFull]  
    authentication_classes = []

    def delete(self, request, progress_id, video_id):
        progress = get_object_or_404(UserCourseProgress, pk=progress_id)
        if not getattr(request, 'admin', None) and progress.user != request.user:
            return Response(
                {'error': 'You do not have permission to update this record.'},
                status=status.HTTP_403_FORBIDDEN
            )
        video = get_object_or_404(Video, pk=video_id, course=progress.course)
        progress.videos_watched.remove(video)
        if progress.completed_at is not None:
            progress.completed_at = None
            progress.save(update_fields=['completed_at'])
        serializer = UserCourseProgressSerializer(progress)
        return Response({
            'message': 'Video removed from watched list.',
            'course_progress': serializer.data
        }, status=status.HTTP_200_OK)
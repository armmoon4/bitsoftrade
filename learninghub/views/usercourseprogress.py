from rest_framework import generics, status, permissions  # type: ignore
from rest_framework.response import Response  # type: ignore
from rest_framework.views import APIView  # type: ignore
from rest_framework_simplejwt.tokens import UntypedToken  # type: ignore
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken  # type: ignore
from django.contrib.auth import get_user_model  # type: ignore
from django.utils import timezone  # type: ignore
from django.shortcuts import get_object_or_404  # type: ignore
from admin_panel.models import Admin
from learninghub.models import UserCourseProgress, Video
from learninghub.serializers.usercourseprogress import (
    UserCourseProgressSerializer,
    UserCourseProgressCreateSerializer,
)

User = get_user_model()


# Same pattern as your other view files — JWT parsed manually
class IsAdminOrAuthenticatedUser(permissions.BasePermission):
    """
    All HTTP methods → valid user JWT OR admin JWT.
    Unlike IsAdminOrUserReadOnly, regular users can also POST here.
    """
    def has_permission(self, request, view):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return False
        raw_token = auth_header.split(' ', 1)[1]
        try:
            token = UntypedToken(raw_token)
            if token.get('is_admin'):
                request.admin = Admin.objects.get(
                    pk=token.get('admin_id'), deleted_at__isnull=True
                )
                return True
            user_id = token.get('user_id')
            if user_id:
                request.user = User.objects.get(pk=user_id, is_active=True)
                return True
            return False
        except (TokenError, InvalidToken, Admin.DoesNotExist, User.DoesNotExist, Exception):
            return False


class UserCourseProgressListAPIView(generics.ListAPIView):
    serializer_class = UserCourseProgressSerializer
    permission_classes = [IsAdminOrAuthenticatedUser]
    authentication_classes = []
    pagination_class = None

    def get_queryset(self):
        # Admins see all progress; users see only their own
        if getattr(self.request, 'admin', None):
            return UserCourseProgress.objects.all()
        return UserCourseProgress.objects.filter(user=self.request.user)


class UserCourseProgressCreateAPIView(generics.CreateAPIView):
    queryset = UserCourseProgress.objects.all()
    serializer_class = UserCourseProgressCreateSerializer
    permission_classes = [IsAdminOrAuthenticatedUser]
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


# ── NEW: This is what was completely missing — marks a video as watched ──────
class MarkVideoWatchedAPIView(APIView):
    """
    POST /course-progress/<progress_id>/watch/<video_id>/
    Adds a video to videos_watched → updates completion_percentage automatically.
    Sets completed_at when all videos are watched.
    """
    permission_classes = [IsAdminOrAuthenticatedUser]
    authentication_classes = []

    def post(self, request, progress_id, video_id):
        progress = get_object_or_404(UserCourseProgress, pk=progress_id)

        # Only the owner or admin can update this record
        if not getattr(request, 'admin', None) and progress.user != request.user:
            return Response(
                {'error': 'You do not have permission to update this record.'},
                status=status.HTTP_403_FORBIDDEN
            )

        video = get_object_or_404(Video, pk=video_id, course=progress.course)
        progress.videos_watched.add(video)  # M2M .add() is safe — ignores duplicates

        # Auto-set completed_at when every video is watched
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


# ── NEW: Unmark a video (resets completion if needed) ────────────────────────
class UnmarkVideoWatchedAPIView(APIView):
    """
    DELETE /course-progress/<progress_id>/unwatch/<video_id>/
    Removes a video from videos_watched → clears completed_at if course was done.
    """
    permission_classes = [IsAdminOrAuthenticatedUser]
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

        # Course is no longer complete if a video was removed
        if progress.completed_at is not None:
            progress.completed_at = None
            progress.save(update_fields=['completed_at'])

        serializer = UserCourseProgressSerializer(progress)
        return Response({
            'message': 'Video removed from watched list.',
            'course_progress': serializer.data
        }, status=status.HTTP_200_OK)
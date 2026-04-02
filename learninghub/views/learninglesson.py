from rest_framework import generics, status, permissions  # type: ignore
from rest_framework.response import Response  # type: ignore
from rest_framework_simplejwt.tokens import UntypedToken  # type: ignore
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken  # type: ignore
from django.contrib.auth import get_user_model  # type: ignore
from admin_panel.models import Admin
from learninghub.models import LearningLesson
from learninghub.serializers.learninglesson import LearningLessonSerializer

User = get_user_model()


class IsAdminOrUserReadOnly(permissions.BasePermission):
    """
    GET  → user JWT (user_id in payload)  OR  admin JWT (is_admin: True in payload)
    POST/PUT/PATCH/DELETE → admin JWT only
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
            if request.method in permissions.SAFE_METHODS:
                user_id = token.get('user_id')
                if user_id:
                    request.user = User.objects.get(pk=user_id, is_active=True)
                    return True
            return False
        except (TokenError, InvalidToken, Admin.DoesNotExist, User.DoesNotExist, Exception):
            return False


class LearningLessonListCreateAPIView(generics.ListCreateAPIView):
    queryset = LearningLesson.objects.all()
    serializer_class = LearningLessonSerializer
    permission_classes = [IsAdminOrUserReadOnly]
    authentication_classes = []

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response({
            'message': 'Learning Lesson created successfully',
            'learning_lesson': serializer.data
        }, status=status.HTTP_201_CREATED, headers=headers)


class LearningLessonDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = LearningLesson.objects.all()
    serializer_class = LearningLessonSerializer
    permission_classes = [IsAdminOrUserReadOnly]
    authentication_classes = []

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response({
            'message': 'Learning Lesson updated successfully',
            'learning_lesson': serializer.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response({
            'message': 'Learning Lesson deleted successfully'
        }, status=status.HTTP_204_NO_CONTENT)
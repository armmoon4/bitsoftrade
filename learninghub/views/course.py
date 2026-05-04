from rest_framework import generics, status
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from learninghub.models import Course
from learninghub.serializers.course import CourseSerializer
from learninghub.permissions import IsAdminOrLearningSubscriber  

User = get_user_model()


class CourseListCreateAPIView(generics.ListCreateAPIView):
    queryset = Course.objects.all()
    serializer_class = CourseSerializer
    permission_classes = [IsAdminOrLearningSubscriber]  
    authentication_classes = []

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response({
            'message': 'Course created successfully',
            'course': serializer.data
        }, status=status.HTTP_201_CREATED, headers=headers)


class CourseDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Course.objects.all()
    serializer_class = CourseSerializer
    permission_classes = [IsAdminOrLearningSubscriber]  
    authentication_classes = []

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response({
            'message': 'Course updated successfully',
            'course': serializer.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response({'message': 'Course deleted successfully'},
                        status=status.HTTP_204_NO_CONTENT)
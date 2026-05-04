from rest_framework import generics, status
from rest_framework.response import Response
from learninghub.models import LearningLesson
from learninghub.serializers.learninglesson import LearningLessonSerializer
from learninghub.permissions import IsAdminOrLearningSubscriber  


class LearningLessonListCreateAPIView(generics.ListCreateAPIView):
    queryset = LearningLesson.objects.all()
    serializer_class = LearningLessonSerializer
    permission_classes = [IsAdminOrLearningSubscriber]  
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
    permission_classes = [IsAdminOrLearningSubscriber] 
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
        return Response({'message': 'Learning Lesson deleted successfully'},
                        status=status.HTTP_204_NO_CONTENT)
from rest_framework import serializers #type: ignore
from learninghub.models import LearningLesson
from learninghub.serializers.course import CourseSerializer

class LearningLessonSerializer(serializers.ModelSerializer):
    courses = CourseSerializer(many=True, read_only=True)
    class Meta:
        model = LearningLesson
        fields = [
            'id',
            'title',
            'description',
            'is_active',
            'created_at',
            'updated_at',
            'courses',
        ]
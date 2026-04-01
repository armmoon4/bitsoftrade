from rest_framework import serializers #type: ignore
from learninghub.models import Course
from learninghub.serializers.video import VideoSerializer

class CourseSerializer(serializers.ModelSerializer):
    videos = VideoSerializer(many=True, read_only=True)
    class Meta:
        model = Course
        fields = [
            'id',
            'title',
            'about',
            'description',
            'course_type',
            'course_level',
            'is_active',
            'created_at',
            'updated_at',
            'videos',
        ]
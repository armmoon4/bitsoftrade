from rest_framework import serializers #type: ignore
from learninghub.models import Video

class VideoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Video
        fields = '__all__'
        
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['course'] = {
            'id': instance.course.id,
            'title': instance.course.title,
            'course_type': instance.course.course_type,
            'course_level': instance.course.course_level,
        }
        return representation
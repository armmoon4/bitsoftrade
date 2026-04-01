from rest_framework import serializers #type: ignore
from learninghub.models import Video

class VideoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Video
        fields = '__all__'
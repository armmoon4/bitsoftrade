from rest_framework import serializers #type: ignore
from django.db.models import Count, F #type: ignore
from learninghub.models import UserCourseProgress

class UserCourseProgressSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserCourseProgress
        fields = [
            'id',
            'user',
            'course',
            'videos_watched',
            'started_at',
            'completed_at',
        ]
        
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['user'] = {
            'id': instance.user.id,
            'email': instance.user.email,
        }
        representation['course'] = {
            'id': instance.course.id,
            'title': instance.course.title,
            'course_type': instance.course.course_type,
            'course_level': instance.course.course_level,
        }
        representation['videos_watched'] = [
            {
                'id': video.id,
                'title': video.title,
            } for video in instance.videos_watched.all()
        ]
        total_videos = instance.course.videos.count()
        completed_videos = instance.videos_watched.count()
        representation['completion_percentage'] = instance.completion_percentage
        representation['total_videos'] = total_videos
        representation['completed_videos'] = completed_videos
        representation['is_completed'] = completed_videos == total_videos

        # Total counts
        representation['total_UserCourseStart'] = UserCourseProgress.objects.count()
        total_completed = UserCourseProgress.objects.annotate(
            total_videos=Count('course__videos'),
            completed_videos=Count('videos_watched')
        ).filter(completed_videos=F('total_videos')).count()
        representation['total_completed_UserCourseStart'] = total_completed

        return representation

class UserCourseProgressCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserCourseProgress
        fields = [
            'user',
            'course',            
            ]
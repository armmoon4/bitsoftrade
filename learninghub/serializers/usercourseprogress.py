from rest_framework import serializers  # type: ignore
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
            }
            for video in instance.videos_watched.all()
        ]

        total_videos = instance.course.videos.count()
        completed_videos = instance.videos_watched.count()

        representation['completion_percentage'] = instance.completion_percentage
        representation['total_videos'] = total_videos
        representation['completed_videos'] = completed_videos
        representation['is_completed'] = completed_videos == total_videos

        # BUG FIX #3: Removed the two extra per-object global aggregate queries
        # (total_UserCourseStart / total_completed_UserCourseStart).
        # These are global stats that do NOT belong in a per-object serializer —
        # they caused N×2 extra DB queries on list endpoints.
        # If you need these stats, add them in the LIST view's Response() instead:
        #
        #   def list(self, request, *args, **kwargs):
        #       response = super().list(request, *args, **kwargs)
        #       response.data['total_started'] = UserCourseProgress.objects.count()
        #       ...
        #       return response

        return representation


class UserCourseProgressCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserCourseProgress
        fields = [
            'user',
            'course',
        ]
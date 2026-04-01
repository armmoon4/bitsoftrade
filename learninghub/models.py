from django.db import models #type: ignore
from django.contrib.auth import get_user_model #type: ignore

User = get_user_model()

class LearningLesson(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title
    
class Course(models.Model):
    title = models.CharField(max_length=255)
    about = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    lessons = models.ForeignKey(LearningLesson, on_delete=models.CASCADE, related_name='courses')
    course_type = models.CharField(default='general', max_length=50)
    course_level = models.CharField(default='beginner', max_length=50)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title
    
    
class Video(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    video = models.FileField(upload_to='LearningLesson/Course/videos/')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='videos')
    is_free = models.BooleanField(default=False)
    is_complete = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title
    

class UserCourseProgress(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='course_progress')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='user_progress')
    videos_watched = models.ManyToManyField(Video, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('user', 'course')

    def __str__(self):
        return f"{self.user.username} - {self.course.title}"

    @property
    def completion_percentage(self):
        total_videos = self.course.videos.count()
        if total_videos == 0:
            return 0
        watched_count = self.videos_watched.count()
        return round((watched_count / total_videos) * 100, 2)
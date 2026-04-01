from django.urls import path #type: ignore
from learninghub.views import course, video, learninglesson, usercourseprogress


urlpatterns = [
    # Course URLs
    path('courses/', course.CourseListCreateAPIView.as_view(), name='course-list-create'),
    path('courses/<int:pk>/', course.CourseDetailAPIView.as_view(), name='course-detail'),
    # Video URLs
    path('videos/', video.VideoListCreateAPIView.as_view(), name='video-list-create'),
    path('videos/<int:pk>/', video.VideoDetailAPIView.as_view(), name='video-detail'),
    # Learning Lesson URLs
    path('learning-lessons/', learninglesson.LearningLessonListCreateAPIView.as_view(), name='learning-lesson-list-create'),
    path('learning-lessons/<int:pk>/', learninglesson.LearningLessonDetailAPIView.as_view(), name='learning-lesson-detail'),
    
    # course progress URLs
    path('course-progress/', usercourseprogress.UserCourseProgressListAPIView.as_view(), name='course-progress-list'),
    path('course-progress/create/', usercourseprogress.UserCourseProgressCreateAPIView.as_view(), name='course-progress-create'),
]
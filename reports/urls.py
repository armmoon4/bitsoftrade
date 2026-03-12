from django.urls import path
from .views import (
    performance_report_view, risk_report_view,
    behavior_report_view, strategy_report_view, journal_report_view,
    mistake_report_view, overview_report_view
)

urlpatterns = [
    path('performance/', performance_report_view, name='report-performance'),
    path('risk/', risk_report_view, name='report-risk'),
    path('behavior/', behavior_report_view, name='report-behavior'),
    path('strategy/', strategy_report_view, name='report-strategy'),
    path('journal/', journal_report_view, name='report-journal'),
    path('mistakes/', mistake_report_view, name='report-mistake'),
    path('overview/', overview_report_view, name='report-overview'),
]

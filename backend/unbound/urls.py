from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from django.views.generic import RedirectView
from fellows import views

router = DefaultRouter()
router.register(r'tasks', views.TaskViewSet, basename='task')
router.register(r'meetings', views.MeetingAvailabilityViewSet, basename='meeting')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/register/', views.register_code_view, name='register_code'),
    path('accounts/', include('allauth.urls')),
    
    # API Endpoints
    path('api/google/account/', views.GoogleAccountView.as_view(), name='google-account'),
    path('api/google/calendar/', views.GoogleCalendarEventsView.as_view(), name='google-calendar-events'),
    path('api/google/drive/', views.GoogleDrivePersonalFilesView.as_view(), name='google-drive-files'),
    path('api/google-drive/personal-files/', views.GoogleDrivePersonalFilesView.as_view(), name='google-drive-personal'),
    path('api/google-drive/shared-files/', views.GoogleDriveSharedFilesView.as_view(), name='google-drive-shared'),
    path('api/google-drive/folders/', views.GoogleDriveFoldersView.as_view(), name='google-drive-folders'),
    path('api/google-drive/set-folder/', views.GoogleDriveSetFolderView.as_view(), name='google-drive-set-folder'),
    path('api/google/tasks/', views.GoogleTasksView.as_view(), name='google-tasks'),
    path('api/google/tasks/<str:task_id>/', views.GoogleTaskDetailView.as_view(), name='google-task-detail'),
    path('api/badges/', views.BadgesAPIView.as_view(), name='badges-api'),
    path('api/cohort/sdgs/', views.CohortSDGsAPIView.as_view(), name='cohort-sdgs-api'),
    path('api/', include(router.urls)),
    
    # UNbound custom views
    path('', RedirectView.as_view(url='/dashboard/', permanent=False), name='index'),
    path('dashboard/', views.dashboard_view, name='dashboard'),

    path('api/dashboard/overview/', views.DashboardOverviewAPIView.as_view(), name='dashboard-overview-api'),
]
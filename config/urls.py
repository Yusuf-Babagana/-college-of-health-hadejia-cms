"""
URL configuration for the College Management System.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('apps.accounts.urls')),
    path('departments/', include('apps.departments.urls')),
    path('lecturers/', include('apps.lecturers.urls')),
    path('courses/', include('apps.courses.urls')),
    path('academics/', include('apps.academics.urls')),
    path('students/', include('apps.students.urls')),
    path('finance/', include('apps.finance.urls')),
    path('results/', include('apps.results.urls')),
    path('practicals/', include('apps.practicals.urls')),
    path('', include('apps.dashboard.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

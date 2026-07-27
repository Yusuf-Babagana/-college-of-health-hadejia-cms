"""
Base settings shared by all environments.
"""
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)
environ.Env.read_env(BASE_DIR / '.env')

SECRET_KEY = env('SECRET_KEY', default='django-insecure-change-me-in-production')

DEBUG = env.bool('DEBUG', default=False)

ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=[])

# Application definition

DJANGO_APPS = [
    'jazzmin',  # must precede the admin app so its templates take priority
    'apps.core.admin_site.CollegeAdminConfig',  # replaces 'django.contrib.admin'
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'crispy_forms',
    'crispy_bootstrap5',
    'django_filters',
]

LOCAL_APPS = [
    'apps.core',
    'apps.accounts',
    'apps.departments',
    'apps.lecturers',
    'apps.courses',
    'apps.academics',
    'apps.students',
    'apps.finance',
    'apps.results',
    'apps.practicals',
    'apps.dashboard',
    'apps.admissions',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.core.middleware.ForcePasswordChangeMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.core.context_processors.site_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

AUTH_USER_MODEL = 'accounts.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Lagos'
USE_I18N = True
USE_TZ = True

# Static & media files

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Authentication

LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'dashboard:redirect'
LOGOUT_REDIRECT_URL = 'accounts:login'

from django.contrib.messages import constants as message_constants  # noqa: E402

MESSAGE_TAGS = {
    message_constants.ERROR: 'danger',
}

# Crispy Forms

CRISPY_ALLOWED_TEMPLATE_PACKS = 'bootstrap5'
CRISPY_TEMPLATE_PACK = 'bootstrap5'

# Django REST Framework

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 25,
}

# Email (console backend by default; overridden per-environment)

DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='noreply@coihst.edu.ng')

# Paystack

PAYSTACK_SECRET_KEY = env('PAYSTACK_SECRET_KEY', default='')
PAYSTACK_PUBLIC_KEY = env('PAYSTACK_PUBLIC_KEY', default='')

# Admissions portal

ADMISSIONS_APPLICATION_FEE = env.int('ADMISSIONS_APPLICATION_FEE', default=7500)

# College identity

COLLEGE_NAME = 'College of Health Sciences and Technology, Hadejia'
COLLEGE_SHORT_NAME = 'COHST Hadejia'

# Jazzmin admin theme
# Reference: venv/Lib/site-packages/jazzmin/settings.py (DEFAULT_SETTINGS / DEFAULT_UI_TWEAKS)

JAZZMIN_SETTINGS = {
    'site_title': 'COHST Admin',
    'site_header': 'COHST Hadejia',
    'site_brand': 'COHST Hadejia',
    'site_logo': 'img/brand/logo1.png',
    'login_logo': 'img/brand/logo1.png',
    'site_logo_classes': 'img-circle',
    'site_icon': 'img/brand/favicon.png',
    'welcome_sign': f'Welcome to the {COLLEGE_SHORT_NAME} Administration Portal',
    'copyright': COLLEGE_NAME,

    'search_model': ['accounts.User'],
    'user_avatar': 'avatar',

    'topmenu_links': [
        {'name': 'View Site', 'url': 'dashboard:redirect', 'permissions': ['auth.view_user']},
    ],
    'usermenu_links': [
        {'name': 'My Profile', 'url': 'accounts:profile'},
    ],

    'show_sidebar': True,
    'navigation_expanded': True,
    'order_with_respect_to': ['accounts', 'auth'],

    # Pre-mapped for every app in the master plan, not just what's installed
    # today - Jazzmin ignores entries for apps/models that aren't
    # registered yet, so Phase 2+ apps light up automatically as they're
    # built without touching this file again.
    'icons': {
        'auth': 'fas fa-users-cog',
        'auth.Group': 'fas fa-layer-group',
        'accounts': 'fas fa-user-shield',
        'accounts.User': 'fas fa-user',
        'students': 'fas fa-user-graduate',
        'students.Student': 'fas fa-user-graduate',
        'lecturers': 'fas fa-chalkboard-teacher',
        'lecturers.Lecturer': 'fas fa-chalkboard-teacher',
        'departments': 'fas fa-building',
        'departments.Department': 'fas fa-building',
        'courses': 'fas fa-book',
        'courses.Course': 'fas fa-book',
        'courses.CourseOffering': 'fas fa-chalkboard',
        'courses.CourseRegistration': 'fas fa-clipboard-list',
        'academics': 'fas fa-calendar-alt',
        'academics.AcademicSession': 'fas fa-calendar-alt',
        'academics.Semester': 'fas fa-calendar-check',
        'finance': 'fas fa-money-check-alt',
        'finance.FeeStructure': 'fas fa-file-invoice-dollar',
        'finance.Invoice': 'fas fa-receipt',
        'finance.Payment': 'fas fa-money-bill-wave',
        'results': 'fas fa-graduation-cap',
        'results.Grade': 'fas fa-percentage',
        'results.GradeBand': 'fas fa-sliders-h',
        'dashboard': 'fas fa-tachometer-alt',
        'notifications': 'fas fa-bell',
        'reports': 'fas fa-chart-bar',
        'audit': 'fas fa-history',
        'core': 'fas fa-cogs',
        'admissions': 'fas fa-file-signature',
        'admissions.Applicant': 'fas fa-user-clock',
        'admissions.Application': 'fas fa-file-signature',
        'admissions.Programme': 'fas fa-graduation-cap',
        'admissions.ReferralCode': 'fas fa-ticket-alt',
        'admissions.AdmissionPayment': 'fas fa-money-check-alt',
    },
    'default_icon_parents': 'fas fa-chevron-circle-right',
    'default_icon_children': 'fas fa-circle',

    'related_modal_active': True,
    'custom_css': 'css/admin-custom.css',
    'show_ui_builder': False,
    'changeform_format': 'horizontal_tabs',
}

JAZZMIN_UI_TWEAKS = {
    'theme': 'default',
    'default_theme_mode': 'light',
    'accent': 'accent-primary',
    'navbar': 'navbar-light',
    'sidebar': 'sidebar-dark-primary',
    'navbar_fixed': True,
    'sidebar_fixed': True,
    'footer_fixed': False,
    'sidebar_nav_flat_style': True,
}

# Logging

LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{asctime} {levelname} {name} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
            'level': 'INFO',
        },
        'application_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'application.log',
            'maxBytes': 5 * 1024 * 1024,  # 5MB
            'backupCount': 5,
            'formatter': 'verbose',
            'level': 'INFO',
        },
        'error_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'error.log',
            'maxBytes': 5 * 1024 * 1024,  # 5MB
            'backupCount': 5,
            'formatter': 'verbose',
            'level': 'ERROR',
        },
    },
    'root': {
        'handlers': ['console', 'application_file', 'error_file'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'application_file', 'error_file'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console', 'error_file'],
            'level': 'ERROR',
            'propagate': False,
        },
        'django.security': {
            'handlers': ['console', 'error_file'],
            'level': 'WARNING',
            'propagate': False,
        },
        # Namespace used by our own apps (apps.core.utils.emails, pdf, etc.)
        'apps': {
            'handlers': ['console', 'application_file', 'error_file'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
    },
}

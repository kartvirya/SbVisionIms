"""
Settings for Vercel + Neon Postgres deployment.
"""
import os
from pathlib import Path
from urllib.parse import urlparse, parse_qs

BASE_DIR = Path(__file__).resolve().parent.parent

from .settings import (
    INSTALLED_APPS,
    ROOT_URLCONF,
    TEMPLATES,
    WSGI_APPLICATION,
    AUTH_PASSWORD_VALIDATORS,
    LANGUAGE_CODE,
    TIME_ZONE,
    USE_I18N,
    USE_TZ,
    LOGIN_URL,
    LOGIN_REDIRECT_URL,
    LOGOUT_URL,
    DEFAULT_AUTO_FIELD,
    CRISPY_ALLOWED_TEMPLATE_PACKS,
    CRISPY_TEMPLATE_PACK,
    AUTHENTICATION_BACKENDS,
    DATA_UPLOAD_MAX_NUMBER_FIELDS,
    DATA_UPLOAD_MAX_MEMORY_SIZE,
)

SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY environment variable is required")

DEBUG = os.environ.get("DEBUG", "False") == "True"

ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get(
        "ALLOWED_HOSTS",
        ".vercel.app,localhost,127.0.0.1",
    ).split(",")
    if h.strip()
]

# Vercel injects VERCEL_URL without scheme (e.g. sbvision-ims.vercel.app)
_csrf = [
    x.strip()
    for x in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")
    if x.strip()
]
_vercel_url = os.environ.get("VERCEL_URL", "").strip()
if _vercel_url:
    _csrf.append(f"https://{_vercel_url}")
_vercel_project = os.environ.get("VERCEL_PROJECT_PRODUCTION_URL", "").strip()
if _vercel_project:
    _csrf.append(f"https://{_vercel_project}")
# Always trust production project alias pattern used by this app
_csrf.extend(
    [
        "https://sbvision-ims.vercel.app",
        "https://sbvision-ims-kartviryas-projects.vercel.app",
    ]
)
CSRF_TRUSTED_ORIGINS = sorted(set(_csrf))

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "True") == "True"
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Neon / Postgres via DATABASE_URL (prefer pooled URL on serverless)
database_url = os.environ.get("DATABASE_URL", "").strip()
if not database_url:
    raise RuntimeError("DATABASE_URL environment variable is required")

parsed = urlparse(database_url)
query = parse_qs(parsed.query)
sslmode = (query.get("sslmode") or ["require"])[0]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": parsed.path.lstrip("/") or "neondb",
        "USER": parsed.username,
        "PASSWORD": parsed.password,
        "HOST": parsed.hostname,
        "PORT": parsed.port or 5432,
        "OPTIONS": {
            "sslmode": sslmode,
        },
        "CONN_MAX_AGE": 0,  # serverless: no persistent connections
    }
}

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "InventoryMS.request_debug.RequestDebugMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")
STATICFILES_DIRS = [os.path.join(BASE_DIR, "static")]
# Serverless: serve app/static via finders without a separate collectstatic build step
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = True
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

# Ephemeral filesystem on Vercel — uploads will not persist across deploys
MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join("/tmp", "ims_media")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

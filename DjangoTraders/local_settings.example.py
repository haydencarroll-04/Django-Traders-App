"""
Local settings template — copy this file to `local_settings.py` and fill in
real values for your machine. `local_settings.py` is git-ignored, so nothing
you put there is ever committed.

settings.py imports from local_settings.py at the very end, so anything you
define here overrides the defaults above it.
"""

# Django secret key for local development.
SECRET_KEY = "put-any-random-string-here-for-local-dev"

# Local database connection. Match this to your own PostgreSQL setup.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "DjangoTraders",
        "USER": "postgres",
        "PASSWORD": "your-local-postgres-password",
        "HOST": "localhost",
        "PORT": "5432",
    }
}

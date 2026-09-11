"""
Vercel serverless entrypoint for Django WSGI.
"""
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "InventoryMS.settings_vercel")

from InventoryMS.wsgi import application  # noqa: E402

app = application

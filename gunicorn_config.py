"""
Gunicorn configuration file for production deployment
"""
import multiprocessing
import os

# Server socket
bind = "unix:/var/www/inventory_ms/inventory_ms.sock"
backlog = 2048

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2

# Logging
accesslog = "-"  # Log to stdout
errorlog = "-"   # Log to stderr
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Process naming
proc_name = "inventory_ms"

# Server mechanics
daemon = False
pidfile = "/var/www/inventory_ms/inventory_ms.pid"
umask = 0
user = "www-data"
group = "www-data"
tmp_upload_dir = None

# SSL (if using SSL directly with Gunicorn)
# keyfile = None
# certfile = None

#!/bin/bash
# One-time / repeat-safe bootstrap for /var/www/inventory_ms on the sbvision droplet.
# Next.js stays on / ; Django IMS is served at /ims/ (see nginx + FORCE_SCRIPT_NAME).
set -eo pipefail

APP=/var/www/inventory_ms
UNIT=/etc/systemd/system/inventory_ms.service

apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3.12-venv python3-pip libpq-dev build-essential

if [ ! -d "$APP/venv" ]; then
  python3.12 -m venv "$APP/venv"
fi
"$APP/venv/bin/pip" install -q --upgrade pip
"$APP/venv/bin/pip" install -q -r "$APP/requirements.txt"

if [ ! -f "$APP/.env" ]; then
  SECRET_KEY=$(openssl rand -hex 32)
  DB_PASSWORD=$(openssl rand -hex 24)
  cat > "$APP/.env" <<EOF
SECRET_KEY=${SECRET_KEY}
DEBUG=False
ALLOWED_HOSTS=sbvision.com.np,www.sbvision.com.np,157.230.234.42
FORCE_SCRIPT_NAME=/ims
DB_NAME=inventory_db
DB_USER=inventory_user
DB_PASSWORD=${DB_PASSWORD}
DB_HOST=127.0.0.1
DB_PORT=5432
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
CSRF_TRUSTED_ORIGINS=https://sbvision.com.np,https://www.sbvision.com.np
EOF

  sudo -u postgres psql -v dbpass="$DB_PASSWORD" <<'EOSQL'
DO $do$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'inventory_user') THEN
    EXECUTE format('CREATE ROLE inventory_user LOGIN PASSWORD %L', :'dbpass');
  ELSE
    EXECUTE format('ALTER ROLE inventory_user PASSWORD %L', :'dbpass');
  END IF;
END
$do$;
EOSQL

  if ! sudo -u postgres psql -Atqc "SELECT 1 FROM pg_database WHERE datname = 'inventory_db'" | grep -q 1; then
    sudo -u postgres psql -c "CREATE DATABASE inventory_db OWNER inventory_user;"
  fi
fi

install -d -o www-data -g www-data -m 775 "$APP/logs" "$APP/media" "$APP/staticfiles"
chown -R www-data:www-data "$APP"
chown root:www-data "$APP/.env"
chmod 640 "$APP/.env"

sudo -u www-data bash -c "
  set -a
  source '$APP/.env'
  set +a
  cd '$APP'
  . venv/bin/activate
  python manage.py migrate --settings=InventoryMS.settings_production
  python manage.py collectstatic --noinput --settings=InventoryMS.settings_production
"

cat > "$UNIT" <<'UNITEOF'
[Unit]
Description=SbVision Django IMS (Gunicorn)
After=network.target postgresql.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/inventory_ms
EnvironmentFile=/var/www/inventory_ms/.env
Environment=DJANGO_SETTINGS_MODULE=InventoryMS.settings_production
ExecStart=/var/www/inventory_ms/venv/bin/gunicorn \
  --access-logfile - \
  --workers 3 \
  --bind unix:/var/www/inventory_ms/inventory_ms.sock \
  InventoryMS.wsgi:application
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNITEOF

python3 <<'PY'
from pathlib import Path
p = Path("/etc/nginx/sites-available/sbvision")
text = p.read_text()
inj = """
    location = /ims {
        return 301 /ims/;
    }

    location /ims/static/ {
        alias /var/www/inventory_ms/staticfiles/;
    }

    location /ims/media/ {
        alias /var/www/inventory_ms/media/;
    }

    location /ims/ {
        rewrite ^/ims/(.*)$ /$1 break;
        include proxy_params;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_pass http://unix:/var/www/inventory_ms/inventory_ms.sock;
    }

"""
if "location /ims/" not in text:
    text = text.replace("    location / {", inj + "    location / {", 1)
    p.write_text(text)
PY

nginx -t
systemctl daemon-reload
systemctl enable inventory_ms
systemctl restart inventory_ms
systemctl reload nginx

echo "Done. Open https://sbvision.com.np/ims/ (create superuser: sudo -u www-data bash -c 'cd $APP && . venv/bin/activate && source .env && set -a && source .env && set +a && python manage.py createsuperuser --settings=InventoryMS.settings_production')"

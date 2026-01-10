#!/bin/bash

# DigitalOcean Deployment Script for Django Inventory Management System
# This script automates the deployment process on a DigitalOcean droplet

set -e  # Exit on any error

echo "=========================================="
echo "Django Inventory Management System"
echo "DigitalOcean Deployment Script"
echo "=========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Please run as root or with sudo${NC}"
    exit 1
fi

# Variables
APP_NAME="inventory_ms"
APP_USER="www-data"
APP_DIR="/var/www/$APP_NAME"
VENV_DIR="$APP_DIR/venv"
REPO_URL=""  # Set your Git repository URL here
DOMAIN=""    # Set your domain name here

# Update system
echo -e "${GREEN}Updating system packages...${NC}"
apt-get update
apt-get upgrade -y

# Install required packages
echo -e "${GREEN}Installing required packages...${NC}"
apt-get install -y \
    python3.12 \
    python3.12-venv \
    python3-pip \
    postgresql \
    postgresql-contrib \
    nginx \
    git \
    supervisor \
    certbot \
    python3-certbot-nginx \
    build-essential \
    libpq-dev \
    python3-dev

# Create application directory
echo -e "${GREEN}Creating application directory...${NC}"
mkdir -p $APP_DIR
mkdir -p $APP_DIR/logs
mkdir -p $APP_DIR/media
mkdir -p $APP_DIR/staticfiles

# Clone or update repository
if [ -d "$APP_DIR/.git" ]; then
    echo -e "${GREEN}Updating repository...${NC}"
    cd $APP_DIR
    git pull
else
    echo -e "${YELLOW}Repository not found. Please clone your repository manually:${NC}"
    echo "cd $APP_DIR && git clone $REPO_URL ."
    exit 1
fi

# Create virtual environment
echo -e "${GREEN}Setting up virtual environment...${NC}"
if [ ! -d "$VENV_DIR" ]; then
    python3.12 -m venv $VENV_DIR
fi

# Activate virtual environment and install dependencies
echo -e "${GREEN}Installing Python dependencies...${NC}"
source $VENV_DIR/bin/activate
pip install --upgrade pip
pip install -r $APP_DIR/requirements.txt
pip install gunicorn psycopg2-binary

# Set up environment variables
if [ ! -f "$APP_DIR/.env" ]; then
    echo -e "${YELLOW}Creating .env file from template...${NC}"
    cp $APP_DIR/.env.example $APP_DIR/.env
    echo -e "${RED}Please edit $APP_DIR/.env with your production settings!${NC}"
fi

# Set up PostgreSQL database
echo -e "${GREEN}Setting up PostgreSQL database...${NC}"
DB_NAME=$(grep DB_NAME $APP_DIR/.env | cut -d '=' -f2)
DB_USER=$(grep DB_USER $APP_DIR/.env | cut -d '=' -f2)
DB_PASSWORD=$(grep DB_PASSWORD $APP_DIR/.env | cut -d '=' -f2)

sudo -u postgres psql <<EOF
CREATE DATABASE $DB_NAME;
CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';
ALTER ROLE $DB_USER SET client_encoding TO 'utf8';
ALTER ROLE $DB_USER SET default_transaction_isolation TO 'read committed';
ALTER ROLE $DB_USER SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;
\q
EOF

# Run migrations
echo -e "${GREEN}Running database migrations...${NC}"
cd $APP_DIR
export $(cat .env | xargs)
python manage.py migrate --settings=InventoryMS.settings_production

# Collect static files
echo -e "${GREEN}Collecting static files...${NC}"
python manage.py collectstatic --noinput --settings=InventoryMS.settings_production

# Create superuser if needed
echo -e "${YELLOW}Do you want to create a superuser? (y/n)${NC}"
read -r response
if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
    python manage.py createsuperuser --settings=InventoryMS.settings_production
fi

# Set permissions
echo -e "${GREEN}Setting file permissions...${NC}"
chown -R $APP_USER:$APP_USER $APP_DIR
chmod -R 755 $APP_DIR
chmod -R 775 $APP_DIR/media
chmod -R 775 $APP_DIR/logs

# Set up Gunicorn service
echo -e "${GREEN}Setting up Gunicorn service...${NC}"
cat > /etc/systemd/system/$APP_NAME.service <<EOF
[Unit]
Description=gunicorn daemon for $APP_NAME
After=network.target

[Service]
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
Environment="PATH=$VENV_DIR/bin"
ExecStart=$VENV_DIR/bin/gunicorn \\
    --access-logfile - \\
    --workers 3 \\
    --bind unix:$APP_DIR/$APP_NAME.sock \\
    InventoryMS.wsgi:application

[Install]
WantedBy=multi-user.target
EOF

# Enable and start Gunicorn
systemctl daemon-reload
systemctl enable $APP_NAME
systemctl restart $APP_NAME

# Set up Nginx
echo -e "${GREEN}Setting up Nginx...${NC}"
cat > /etc/nginx/sites-available/$APP_NAME <<EOF
server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN;

    client_max_body_size 100M;

    location /static/ {
        alias $APP_DIR/staticfiles/;
    }

    location /media/ {
        alias $APP_DIR/media/;
    }

    location / {
        include proxy_params;
        proxy_pass http://unix:$APP_DIR/$APP_NAME.sock;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

# Enable Nginx site
ln -sf /etc/nginx/sites-available/$APP_NAME /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl restart nginx

# Set up SSL with Let's Encrypt (optional)
echo -e "${YELLOW}Do you want to set up SSL with Let's Encrypt? (y/n)${NC}"
read -r ssl_response
if [[ "$ssl_response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
    certbot --nginx -d $DOMAIN -d www.$DOMAIN --non-interactive --agree-tos --email admin@$DOMAIN
fi

echo -e "${GREEN}=========================================="
echo "Deployment completed successfully!"
echo "==========================================${NC}"
echo ""
echo "Your application should now be running at: http://$DOMAIN"
echo ""
echo "Useful commands:"
echo "  - View logs: journalctl -u $APP_NAME -f"
echo "  - Restart app: systemctl restart $APP_NAME"
echo "  - Restart nginx: systemctl restart nginx"
echo "  - Check status: systemctl status $APP_NAME"

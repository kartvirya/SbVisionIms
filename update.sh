#!/bin/bash

# Update script for Django Inventory Management System
# Run this script to update your application after code changes

set -e

APP_DIR="/var/www/inventory_ms"
VENV_DIR="$APP_DIR/venv"

echo "=========================================="
echo "Updating Django Inventory Management System"
echo "=========================================="

cd $APP_DIR

# Activate virtual environment
source $VENV_DIR/bin/activate

# Pull latest changes (if using Git)
if [ -d ".git" ]; then
    echo "Pulling latest changes from Git..."
    git pull
fi

# Install/update dependencies
echo "Installing/updating Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Load environment variables
export $(cat .env | xargs)

# Run migrations
echo "Running database migrations..."
python manage.py migrate --settings=InventoryMS.settings_production

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput --settings=InventoryMS.settings_production

# Restart Gunicorn
echo "Restarting application..."
sudo systemctl restart inventory_ms

echo "=========================================="
echo "Update completed successfully!"
echo "=========================================="

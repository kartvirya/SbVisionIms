# Quick Start Deployment Guide

## For DigitalOcean Deployment

### 1. Prepare Your Server

```bash
# SSH into your DigitalOcean droplet
ssh root@your-droplet-ip

# Update system
apt-get update && apt-get upgrade -y
```

### 2. Upload Your Code

**Option A: Using Git**
```bash
cd /var/www
git clone https://github.com/yourusername/sales-and-inventory-management.git inventory_ms
cd inventory_ms
```

**Option B: Using SCP (from your local machine)**
```bash
scp -r /path/to/project root@your-droplet-ip:/var/www/inventory_ms
```

### 3. Run Deployment Script

```bash
cd /var/www/inventory_ms
chmod +x deploy.sh

# Edit deploy.sh and update:
# - REPO_URL (if using Git)
# - DOMAIN (your domain name)

sudo ./deploy.sh
```

### 4. Configure Environment Variables

```bash
cd /var/www/inventory_ms
cp env.example .env
nano .env
```

**Important:** Update these values:
- `SECRET_KEY` - Generate new: `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`
- `ALLOWED_HOSTS` - Your domain and IP
- `DB_PASSWORD` - Strong password

### 5. Final Setup

```bash
cd /var/www/inventory_ms
source venv/bin/activate
export $(cat .env | xargs)

# Run migrations
python manage.py migrate --settings=InventoryMS.settings_production

# Create superuser
python manage.py createsuperuser --settings=InventoryMS.settings_production

# Collect static files
python manage.py collectstatic --noinput --settings=InventoryMS.settings_production

# Restart services
sudo systemctl restart inventory_ms
sudo systemctl restart nginx
```

### 6. Set Up SSL (Optional but Recommended)

```bash
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

## Updating Your Application

After making code changes:

```bash
cd /var/www/inventory_ms
./update.sh
```

Or manually:

```bash
cd /var/www/inventory_ms
source venv/bin/activate
git pull  # or upload new files
pip install -r requirements.txt
export $(cat .env | xargs)
python manage.py migrate --settings=InventoryMS.settings_production
python manage.py collectstatic --noinput --settings=InventoryMS.settings_production
sudo systemctl restart inventory_ms
```

## Troubleshooting

**Check application logs:**
```bash
sudo journalctl -u inventory_ms -f
```

**Check Nginx logs:**
```bash
sudo tail -f /var/log/nginx/error.log
```

**Restart services:**
```bash
sudo systemctl restart inventory_ms
sudo systemctl restart nginx
```

For detailed deployment instructions, see [DEPLOYMENT.md](DEPLOYMENT.md)

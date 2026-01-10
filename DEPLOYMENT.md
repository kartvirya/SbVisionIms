# DigitalOcean Deployment Guide

This guide will help you deploy the Django Inventory Management System on a DigitalOcean droplet.

## Prerequisites

- A DigitalOcean account
- A domain name (optional but recommended)
- Basic knowledge of Linux command line

## Step 1: Create a DigitalOcean Droplet

1. Log in to your DigitalOcean account
2. Click "Create" → "Droplets"
3. Choose:
   - **Image**: Ubuntu 22.04 LTS
   - **Plan**: At least 1GB RAM / 1 vCPU ($6/month minimum recommended)
   - **Datacenter**: Choose closest to your users
   - **Authentication**: SSH keys (recommended) or root password
4. Click "Create Droplet"

## Step 2: Initial Server Setup

### Connect to your droplet:

```bash
ssh root@your-droplet-ip
```

### Update system:

```bash
apt-get update && apt-get upgrade -y
```

### Create a non-root user (optional but recommended):

```bash
adduser deploy
usermod -aG sudo deploy
su - deploy
```

## Step 3: Clone Your Repository

```bash
cd /var/www
git clone https://github.com/yourusername/sales-and-inventory-management.git inventory_ms
cd inventory_ms
```

**OR** upload files using SCP:

```bash
# From your local machine
scp -r /path/to/project root@your-droplet-ip:/var/www/inventory_ms
```

## Step 4: Run Deployment Script

### Make the script executable:

```bash
chmod +x deploy.sh
```

### Edit the script variables:

```bash
nano deploy.sh
```

Update these variables:
- `REPO_URL`: Your Git repository URL (if using Git)
- `DOMAIN`: Your domain name

### Run the deployment script:

```bash
sudo ./deploy.sh
```

The script will:
- Install all required packages
- Set up PostgreSQL database
- Create virtual environment
- Install Python dependencies
- Run migrations
- Set up Gunicorn service
- Configure Nginx
- Set up SSL (optional)

## Step 5: Manual Configuration

### 1. Set up Environment Variables

```bash
cd /var/www/inventory_ms
cp env.example .env
nano .env
```

Update the following values:
- `SECRET_KEY`: Generate a new secret key (use `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`)
- `ALLOWED_HOSTS`: Your domain name and IP address
- `DB_PASSWORD`: Strong database password
- Other settings as needed

### 2. Update Settings

Edit `InventoryMS/settings_production.py` if needed to match your environment.

### 3. Run Migrations

```bash
cd /var/www/inventory_ms
source venv/bin/activate
export $(cat .env | xargs)
python manage.py migrate --settings=InventoryMS.settings_production
```

### 4. Create Superuser

```bash
python manage.py createsuperuser --settings=InventoryMS.settings_production
```

### 5. Collect Static Files

```bash
python manage.py collectstatic --noinput --settings=InventoryMS.settings_production
```

## Step 6: Configure Nginx

### Edit Nginx configuration:

```bash
sudo nano /etc/nginx/sites-available/inventory_ms
```

Update `server_name` with your domain:

```nginx
server_name yourdomain.com www.yourdomain.com;
```

### Test and restart Nginx:

```bash
sudo nginx -t
sudo systemctl restart nginx
```

## Step 7: Set up SSL (Let's Encrypt)

```bash
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

Follow the prompts. Certbot will automatically configure SSL.

## Step 8: Start Services

```bash
# Start Gunicorn
sudo systemctl start inventory_ms
sudo systemctl enable inventory_ms

# Check status
sudo systemctl status inventory_ms
```

## Step 9: Firewall Configuration

```bash
# Allow SSH
sudo ufw allow 22/tcp

# Allow HTTP and HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Enable firewall
sudo ufw enable
```

## Post-Deployment

### Useful Commands

```bash
# View application logs
sudo journalctl -u inventory_ms -f

# Restart application
sudo systemctl restart inventory_ms

# Restart Nginx
sudo systemctl restart nginx

# View Nginx error logs
sudo tail -f /var/log/nginx/error.log

# Access Django shell
cd /var/www/inventory_ms
source venv/bin/activate
export $(cat .env | xargs)
python manage.py shell --settings=InventoryMS.settings_production
```

### Updating the Application

```bash
cd /var/www/inventory_ms
git pull  # or upload new files
source venv/bin/activate
pip install -r requirements.txt
export $(cat .env | xargs)
python manage.py migrate --settings=InventoryMS.settings_production
python manage.py collectstatic --noinput --settings=InventoryMS.settings_production
sudo systemctl restart inventory_ms
```

## Troubleshooting

### Application not starting

```bash
# Check Gunicorn logs
sudo journalctl -u inventory_ms -n 50

# Check if socket file exists
ls -la /var/www/inventory_ms/inventory_ms.sock

# Check permissions
ls -la /var/www/inventory_ms/
```

### 502 Bad Gateway

- Check if Gunicorn is running: `sudo systemctl status inventory_ms`
- Check Nginx error logs: `sudo tail -f /var/log/nginx/error.log`
- Verify socket file permissions

### Static files not loading

- Ensure `collectstatic` was run
- Check Nginx configuration for static file paths
- Verify file permissions: `sudo chown -R www-data:www-data /var/www/inventory_ms/staticfiles`

### Database connection errors

- Verify PostgreSQL is running: `sudo systemctl status postgresql`
- Check database credentials in `.env`
- Test connection: `psql -U inventory_user -d inventory_db`

## Security Checklist

- [ ] Changed default SECRET_KEY
- [ ] Set DEBUG=False
- [ ] Configured ALLOWED_HOSTS
- [ ] Set up SSL/HTTPS
- [ ] Configured firewall
- [ ] Set strong database password
- [ ] Limited SSH access (key-based authentication)
- [ ] Regular backups configured
- [ ] Updated system packages

## Backup Strategy

### Database Backup

```bash
# Create backup script
sudo nano /usr/local/bin/backup-db.sh
```

```bash
#!/bin/bash
BACKUP_DIR="/var/backups/inventory_db"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR
sudo -u postgres pg_dump inventory_db > $BACKUP_DIR/db_backup_$DATE.sql
# Keep only last 7 days
find $BACKUP_DIR -name "db_backup_*.sql" -mtime +7 -delete
```

```bash
chmod +x /usr/local/bin/backup-db.sh

# Add to crontab (daily at 2 AM)
crontab -e
# Add: 0 2 * * * /usr/local/bin/backup-db.sh
```

### Media Files Backup

```bash
# Backup media directory
tar -czf /var/backups/media_backup_$(date +%Y%m%d).tar.gz /var/www/inventory_ms/media/
```

## Support

For issues or questions, please refer to:
- Django Deployment Checklist: https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/
- DigitalOcean Community: https://www.digitalocean.com/community

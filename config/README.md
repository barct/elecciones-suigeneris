# Apache Deployment Notes

This directory contains sample configuration for serving the Django project with Apache + `mod_wsgi`.

## Files
- `apache/legis_site.conf`: example virtual host ready for `/etc/apache2/sites-available/`. Update `ServerName`, `DocumentRoot`, and all `/var/www/legis2025` paths to match the real deployment directory. Enable it with `a2ensite legis_site`.
- `apache/envvars.conf`: optional environment overrides. Drop it in `/etc/apache2/conf-available/` and enable with `a2enconf legis_site-env` to keep secrets out of version control.

## Quick Setup Checklist
1. Install requirements on the server: `apt install apache2 libapache2-mod-wsgi-py3`.
2. Copy the project to `/var/www/legis2025/` (or another path) and create the virtualenv referenced in the config.
3. Run `python manage.py collectstatic` so `/static/` is populated.
4. Copy the files from `config/apache/` into Apache's config directories and enable them (`a2ensite`, `a2enconf`).
5. Restart Apache: `systemctl restart apache2` and review `/var/log/apache2/legis_site_error.log` for issues.

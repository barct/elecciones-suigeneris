#!/usr/bin/env bash
# Helper script to install Apache configuration for the Legis 2025 portal.
# Usage: sudo ./deploy_apache.sh
set -euo pipefail

SITE_NAME="legis_site"
PROJECT_ROOT="/var/www/elecciones-suigeneris"
REPO_URL="git@github.com:barct/elecciones-suigeneris.git"
APACHE_SITES_AVAILABLE="/etc/apache2/sites-available"
APACHE_CONF_AVAILABLE="/etc/apache2/conf-available"

# Ensure the source tree is present and up to date before touching Apache.
if [[ ! -d "${PROJECT_ROOT}" ]]; then
  echo "Cloning repository into ${PROJECT_ROOT}..."
  git clone "${REPO_URL}" "${PROJECT_ROOT}"
elif [[ -d "${PROJECT_ROOT}/.git" ]]; then
  echo "Pulling latest changes in ${PROJECT_ROOT}..."
  git -C "${PROJECT_ROOT}" pull --ff-only
else
  echo "ERROR: ${PROJECT_ROOT} exists but is not a git repository." >&2
  exit 1
fi

# Make sure mod_wsgi is available/enabled before installing the vhost.
if ! apache2ctl -M 2>/dev/null | grep -q "wsgi_module"; then
  echo "Enabling Apache mod_wsgi module..."
  if ! a2enmod wsgi >/dev/null; then
    echo "ERROR: Could not enable mod_wsgi. Install 'libapache2-mod-wsgi-py3' and retry." >&2
    exit 1
  fi
fi

install_file() {
  local source_file="$1"
  local destination="$2"
  if [[ ! -f "${source_file}" ]]; then
    echo "ERROR: Source ${source_file} not found." >&2
    exit 1
  fi
  install -m 644 "${source_file}" "${destination}"
  echo "Installed ${source_file} -> ${destination}"
}

# Copy virtual host and optional envvars config.
install_file "${PROJECT_ROOT}/config/apache/legis_site.conf" "${APACHE_SITES_AVAILABLE}/${SITE_NAME}.conf"
install_file "${PROJECT_ROOT}/config/apache/envvars.conf" "${APACHE_CONF_AVAILABLE}/${SITE_NAME}-env.conf"

# Enable site and env configuration.
if ! a2ensite "${SITE_NAME}" >/dev/null; then
  echo "WARNING: a2ensite ${SITE_NAME} returned a non-zero exit code." >&2
fi
if ! a2enconf "${SITE_NAME}-env" >/dev/null; then
  echo "WARNING: a2enconf ${SITE_NAME}-env returned a non-zero exit code." >&2
fi

echo "Testing Apache configuration..."
apache2ctl configtest

echo "Reloading Apache service..."
systemctl reload apache2

echo "Done. Check /var/log/apache2/legis_site_error.log for issues if the site is unreachable."

#!/usr/bin/env bash
# Helper script to install Apache configuration for the Legis 2025 portal.
# Usage: sudo ./deploy_apache.sh
set -euo pipefail

SITE_NAME="legis_site"
PROJECT_ROOT="/var/www/elecciones-suigeneris"
REPO_URL="git@github.com:barct/elecciones-suigeneris.git"
VENV_PATH="${PROJECT_ROOT}/.venv"
PYTHON_BIN="python3"
APACHE_SITES_AVAILABLE="/etc/apache2/sites-available"
APACHE_CONF_AVAILABLE="/etc/apache2/conf-available"
export DJANGO_STATIC_ROOT="${PROJECT_ROOT}/staticfiles"

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

# Create or update the Python virtual environment.
if [[ ! -d "${VENV_PATH}" ]]; then
  echo "Creating virtual environment at ${VENV_PATH}..."
  if ! ${PYTHON_BIN} -m venv "${VENV_PATH}"; then
    echo "ERROR: Could not create virtual environment. Install 'python3-venv' and retry." >&2
    exit 1
  fi
else
  echo "Virtual environment already exists at ${VENV_PATH}."
fi

if [[ ! -x "${VENV_PATH}/bin/pip" ]]; then
  echo "pip not found inside ${VENV_PATH}; recreating virtual environment..."
  rm -rf "${VENV_PATH}"
  if ! ${PYTHON_BIN} -m venv "${VENV_PATH}"; then
    echo "ERROR: Could not recreate virtual environment. Check python3-venv installation." >&2
    exit 1
  fi
fi

echo "Installing Python dependencies..."
if [[ ! -x "${VENV_PATH}/bin/pip" ]]; then
  echo "ERROR: pip still missing inside ${VENV_PATH}." >&2
  exit 1
fi
"${VENV_PATH}/bin/pip" install --upgrade pip
"${VENV_PATH}/bin/pip" install -r "${PROJECT_ROOT}/requirements.txt"

# Apply database migrations so the SQLite file exists and is up to date.
echo "Applying database migrations..."
"${VENV_PATH}/bin/python" "${PROJECT_ROOT}/manage.py" migrate --noinput

# Load baseline fixtures so the site has core reference data.
echo "Loading base fixtures..."
"${VENV_PATH}/bin/python" "${PROJECT_ROOT}/manage.py" loaddata \
  "${PROJECT_ROOT}/elections/fixtures/districts.json" \
  "${PROJECT_ROOT}/elections/fixtures/lists.json"

# Ensure the requested admin account exists for operational access.
echo "Ensuring admin superuser exists..."
"${VENV_PATH}/bin/python" "${PROJECT_ROOT}/manage.py" shell -c "from django.contrib.auth import get_user_model; User = get_user_model(); User.objects.filter(username='admin').exists() or User.objects.create_superuser('admin', 'hidalgofernandojavierqgmail.com', 'mameluco')"

# Collect static files so Apache can serve them.
echo "Collecting static assets..."
mkdir -p "${DJANGO_STATIC_ROOT}"
"${VENV_PATH}/bin/python" "${PROJECT_ROOT}/manage.py" collectstatic --noinput

# Ensure runtime directories are owned by the Apache user.
APACHE_USER="www-data"
if id -u "${APACHE_USER}" >/dev/null 2>&1; then
  if [[ -d "${PROJECT_ROOT}" ]]; then
    chown root:"${APACHE_USER}" "${PROJECT_ROOT}"
    chmod 775 "${PROJECT_ROOT}"
  fi
  if [[ -f "${PROJECT_ROOT}/db.sqlite3" ]]; then
    chown "${APACHE_USER}:${APACHE_USER}" "${PROJECT_ROOT}/db.sqlite3"
    chmod 660 "${PROJECT_ROOT}/db.sqlite3"
    if [[ -f "${PROJECT_ROOT}/db.sqlite3-wal" ]]; then
      chown "${APACHE_USER}:${APACHE_USER}" "${PROJECT_ROOT}/db.sqlite3-wal"
      chmod 660 "${PROJECT_ROOT}/db.sqlite3-wal"
    fi
    if [[ -f "${PROJECT_ROOT}/db.sqlite3-shm" ]]; then
      chown "${APACHE_USER}:${APACHE_USER}" "${PROJECT_ROOT}/db.sqlite3-shm"
      chmod 660 "${PROJECT_ROOT}/db.sqlite3-shm"
    fi
  fi
  if [[ -d "${PROJECT_ROOT}/media" ]]; then
    chown -R "${APACHE_USER}:${APACHE_USER}" "${PROJECT_ROOT}/media"
  fi
  if [[ -d "${DJANGO_STATIC_ROOT}" ]]; then
    chown -R "${APACHE_USER}:${APACHE_USER}" "${DJANGO_STATIC_ROOT}"
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

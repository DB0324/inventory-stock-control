#!/usr/bin/env bash
# Render runs this on every deploy. set -o errexit means a failed migration
# aborts the deploy rather than shipping a half-migrated database.
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate
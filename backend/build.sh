#!/usr/bin/env bash
# Render runs this on every deploy. set -o errexit means a failed migration
# aborts the deploy rather than shipping a half-migrated database.
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate

# The cache backs the login rate limiter, and the database cache needs its
# table. Safe to repeat: it prints "already exists" and carries on.
python manage.py createcachetable

python manage.py create_demo_users

# Idempotent: does nothing once the seeded SKUs exist, so a redeploy will not
# double every quantity.
python manage.py seed_demo_data
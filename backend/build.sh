#!/usr/bin/env bash
# Render runs this on every deploy. set -o errexit means a failed migration
# aborts the deploy rather than shipping a half-migrated database.
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate
python manage.py create_demo_users
# Idempotent: does nothing once items exist, so a redeploy will not
# double every quantity.
# TEMPORARY: the first seed ran before the date-ordering fix, so production
# holds a history where openings are dated last and one shelf goes negative.
# Reverted to plain seed_demo_data immediately after this deploy.
python manage.py seed_demo_data --reset --i-know-this-is-production
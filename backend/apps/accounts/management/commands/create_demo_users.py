"""Creates the demo accounts the reviewer logs in with.

Idempotent, because build.sh runs it on every deploy, and set_password runs
every time -- so changing DEMO_PASSWORD in the host's environment and
redeploying resets both accounts.

The password itself comes from the environment rather than being written here.
It is published in SUBMISSION.md, because a reviewer who cannot sign in cannot
review anything; keeping it out of the source means rotating it does not need
a commit.
"""

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create or update the demo manager and staff accounts."

    def handle(self, *args, **options):
        User = get_user_model()
        password = os.environ.get("DEMO_PASSWORD")
        if not password:
            self.stderr.write("DEMO_PASSWORD is not set; skipping.")
            return

        accounts = [
            ("manager@inventory.local", "Demo Manager", User.Role.MANAGER, True),
            ("staff@inventory.local", "Demo Staff", User.Role.STAFF, False),
        ]

        for email, name, role, is_admin in accounts:
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "full_name": name,
                    "role": role,
                    "is_staff": is_admin,
                    "is_superuser": is_admin,
                },
            )
            user.set_password(password)
            user.save()
            self.stdout.write(f"{'created' if created else 'updated'} {email}")
"""
Management command to bootstrap the very first super admin.

Usage:
    python manage.py create_super_admin --email admin@example.com \
        --name "Super Admin" --password s3cr3tP@ss
"""
from django.core.management.base import BaseCommand, CommandError
from admin_panel.models import Admin


class Command(BaseCommand):
    help = "Create the first super admin (no existing admin required)."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True, help="Email address for the super admin")
        parser.add_argument("--name", required=True, help="Full name for the super admin")
        parser.add_argument("--password", required=True, help="Password for the super admin")

    def handle(self, *args, **options):
        email = options["email"].strip().lower()
        name = options["name"].strip()
        password = options["password"]

        if not email or not name or not password:
            raise CommandError("--email, --name, and --password are all required.")

        if Admin.objects.filter(email=email).exists():
            self.stdout.write(
                self.style.WARNING(f"An admin with email '{email}' already exists. Skipping.")
            )
            return

        admin = Admin(
            full_name=name,
            email=email,
            access_level="super_admin",
        )
        admin.set_password(password)
        admin.save()

        self.stdout.write(
            self.style.SUCCESS(
                f"Super admin '{email}' created successfully with access_level=super_admin."
            )
        )

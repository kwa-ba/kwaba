"""Closes the Django administration sessions opened before the second factor (ADR-028): every super admin signs in
again with a code. The site's sessions are JWT and are not concerned."""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0012_two_factor'),
        ('sessions', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL('DELETE FROM django_session', reverse_sql=migrations.RunSQL.noop),
    ]

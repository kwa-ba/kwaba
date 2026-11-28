# The shared mobility registers (drivers, vehicles, owners, ranges) get their back-office section (harmonisation of
# 26 November 2026, T-H2): an admin limited to the car hire or to the transfers keeps them.
from django.db import migrations


def accorder(apps, schema_editor):
    User = apps.get_model('users', 'UserModel')
    for u in User.objects.filter(admin_sections__isnull=False):
        sections = list(u.admin_sections or [])
        if ('location' in sections or 'transferts' in sections) and 'mobilite' not in sections:
            u.admin_sections = [*sections, 'mobilite']
            u.save(update_fields=['admin_sections'])


def retirer(apps, schema_editor):
    User = apps.get_model('users', 'UserModel')
    for u in User.objects.filter(admin_sections__isnull=False):
        if 'mobilite' in (u.admin_sections or []):
            u.admin_sections = [s for s in u.admin_sections if s != 'mobilite']
            u.save(update_fields=['admin_sections'])


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0016_account_language'),
    ]

    operations = [
        migrations.RunPython(accorder, retirer),
    ]

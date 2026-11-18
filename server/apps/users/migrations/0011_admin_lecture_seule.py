from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0010_admin_permissions'),
    ]

    operations = [
        migrations.AddField(
            model_name='usermodel',
            name='admin_lecture_seule',
            field=models.BooleanField(db_default=False, default=False),
        ),
    ]

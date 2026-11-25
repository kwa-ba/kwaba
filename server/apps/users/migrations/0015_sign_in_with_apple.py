from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0014_account_deletion'),
    ]

    operations = [
        migrations.AddField(
            model_name='usermodel',
            name='apple_id',
            field=models.CharField(blank=True, max_length=255, null=True, unique=True),
        ),
        migrations.AddField(
            model_name='usermodel',
            name='apple_refresh_token',
            field=models.TextField(blank=True, db_default='', default=''),
        ),
    ]

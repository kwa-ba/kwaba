from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0009_validation'),
    ]

    operations = [
        migrations.CreateModel(
            name='CautionModel',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('objet_type', models.CharField(max_length=30)),
                ('objet_id', models.CharField(max_length=64)),
                ('reference', models.CharField(max_length=40)),
                ('offre_code', models.CharField(max_length=30)),
                ('voyageur_id', models.UUIDField(blank=True, null=True)),
                ('montant', models.BigIntegerField()),
                ('recue_le', models.DateTimeField()),
                ('date_limite', models.DateTimeField(help_text='Restitution attendue au plus tard')),
                ('statut', models.CharField(choices=[('detenue', 'Détenue'), ('restituee', 'Restituée'),
                                                     ('retenue', 'Retenue en partie ou en totalité')],
                                            default='detenue', max_length=10)),
                ('montant_retenu', models.BigIntegerField(default=0)),
                ('montant_rendu', models.BigIntegerField(default=0)),
                ('motif_retenue', models.TextField(blank=True, default='')),
                ('cgv_article', models.CharField(blank=True, default='', max_length=30)),
                ('decision_par_id', models.UUIDField(blank=True, null=True)),
                ('decision_le', models.DateTimeField(blank=True, null=True)),
                ('soldee_le', models.DateTimeField(blank=True, null=True)),
                ('mode_restitution', models.CharField(blank=True, default='', max_length=120)),
                ('document_numero', models.CharField(blank=True, default='', max_length=20)),
            ],
            options={
                'verbose_name': 'Caution',
                'db_table': 'finance_caution',
                'ordering': ['date_limite'],
                'constraints': [
                    models.UniqueConstraint(fields=('objet_type', 'objet_id'), name='finance_caution_une_par_objet'),
                    models.CheckConstraint(condition=models.Q(montant__gt=0), name='finance_caution_montant_positif'),
                    models.CheckConstraint(condition=models.Q(montant_retenu__gte=0,
                                                              montant_retenu__lte=models.F('montant')),
                                           name='finance_caution_retenue_bornee'),
                    models.CheckConstraint(
                        condition=models.Q(statut='detenue') | (
                            models.Q(montant_rendu=models.F('montant') - models.F('montant_retenu'))
                            & ~models.Q(document_numero='') & models.Q(soldee_le__isnull=False)),
                        name='finance_caution_soldee_complete'),
                    models.CheckConstraint(condition=models.Q(montant_retenu=0) | (
                        ~models.Q(motif_retenue='') & ~models.Q(cgv_article='')),
                        name='finance_caution_retenue_motivee'),
                ],
            },
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0008_decisions_du_18_novembre'),
    ]

    operations = [
        migrations.CreateModel(
            name='ValidationModel',
            fields=[
                ('id', models.UUIDField(primary_key=True, serialize=False)),
                ('operation', models.CharField(max_length=40)),
                ('objet_type', models.CharField(max_length=30)),
                ('objet_id', models.CharField(max_length=64)),
                ('montant', models.BigIntegerField()),
                ('motif', models.TextField(blank=True, default='')),
                ('donnees', models.JSONField(blank=True, default=dict)),
                ('statut', models.CharField(choices=[('en_attente', 'En attente'), ('executee', 'Validée et exécutée'),
                                                     ('refusee', 'Refusée'),
                                                     ('echouee', 'Validée, exécution en échec')],
                                            default='en_attente', max_length=12)),
                ('demandee_par_id', models.UUIDField(blank=True, help_text='Vide : demandée par le système', null=True)),
                ('demandee_le', models.DateTimeField()),
                ('premiere_par_id', models.UUIDField(blank=True, help_text='Première validation (demande du système)',
                                                     null=True)),
                ('decidee_par_id', models.UUIDField(blank=True, null=True)),
                ('decidee_le', models.DateTimeField(blank=True, null=True)),
                ('resultat', models.TextField(blank=True, default='')),
            ],
            options={
                'verbose_name': 'Double validation',
                'db_table': 'finance_validation',
                'ordering': ['-demandee_le'],
                'constraints': [
                    models.CheckConstraint(condition=models.Q(montant__gt=0),
                                           name='finance_validation_montant_positif'),
                    models.CheckConstraint(
                        condition=(models.Q(decidee_par_id__isnull=True) | models.Q(demandee_par_id__isnull=True)
                                   | ~models.Q(decidee_par_id=models.F('demandee_par_id'))),
                        name='finance_validation_decideur_distinct_du_demandeur'),
                    models.CheckConstraint(
                        condition=(models.Q(premiere_par_id__isnull=True) | models.Q(decidee_par_id__isnull=True)
                                   | ~models.Q(decidee_par_id=models.F('premiere_par_id'))),
                        name='finance_validation_deux_validations_distinctes'),
                    models.UniqueConstraint(condition=models.Q(statut='en_attente'),
                                            fields=('operation', 'objet_type', 'objet_id'),
                                            name='finance_validation_une_demande_en_attente'),
                ],
            },
        ),
    ]

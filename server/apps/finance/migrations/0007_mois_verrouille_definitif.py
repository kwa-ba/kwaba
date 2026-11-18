# Month closing (GL-7, FIN-08): a locked month never opens again, whoever asks (the application, a script or an
# administrator in psql). Locking it is the last word: an error found later is corrected by an inverse line dated in
# an open month, never by rewriting a closed one. A locked month is not deleted either.
from django.db import migrations

GARDE = [
    """
    CREATE OR REPLACE FUNCTION finance_periode_verrouillage_definitif()
    RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF TG_OP = 'DELETE' THEN
            IF OLD.etat = 'verrouillee' THEN
                RAISE EXCEPTION 'Le mois % est verrouillé : il ne se supprime pas.', to_char(OLD.mois, 'MM/YYYY');
            END IF;
            RETURN OLD;
        END IF;
        IF OLD.etat = 'verrouillee' AND (NEW.etat IS DISTINCT FROM OLD.etat
                                         OR NEW.verrouillee_le IS DISTINCT FROM OLD.verrouillee_le
                                         OR NEW.verrouillee_par_id IS DISTINCT FROM OLD.verrouillee_par_id) THEN
            RAISE EXCEPTION 'Le mois % est verrouillé : il ne se rouvre jamais.', to_char(OLD.mois, 'MM/YYYY');
        END IF;
        IF NEW.etat = 'verrouillee' AND NEW.verrouillee_le IS NULL THEN
            RAISE EXCEPTION 'Un mois verrouillé porte la date de son verrouillage.';
        END IF;
        RETURN NEW;
    END $$
    """,
    """
    CREATE TRIGGER trg_finance_periode_verrouillage_definitif
        BEFORE UPDATE OR DELETE ON finance_periode
        FOR EACH ROW EXECUTE FUNCTION finance_periode_verrouillage_definitif()
    """,
]

INVERSE = [
    'DROP TRIGGER IF EXISTS trg_finance_periode_verrouillage_definitif ON finance_periode',
    'DROP FUNCTION IF EXISTS finance_periode_verrouillage_definitif()',
]


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0006_paypal_inactif'),
    ]

    operations = [
        migrations.RunSQL(GARDE, INVERSE),
    ]

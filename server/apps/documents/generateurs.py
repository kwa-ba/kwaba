"""Content of the invoices and credit notes. Vouchers and receipts are built by the module of each product
(documents.api)."""
from .models import AvoirModel, DocumentCautionModel, FactureModel
from .pdf import Document, date, fcfa


def _taux(taux) -> str:
    return str(taux).rstrip('0').rstrip('.').replace('.', ',')


def avoir(a: AvoirModel) -> bytes:
    """Credit note: quotes its invoice, amounts to deduct from it."""
    f = a.facture
    doc = Document("Facture d'avoir", a.numero, sous_titre=f"émise le {date(a.emis_le)}",
                   destinataire=[x for x in (f.client_nom, f.client_adresse, f.client_email) if x])
    doc.bloc('Facture d\'origine', [('Facture', f.numero), ('Émise le', date(f.emise_le)),
                                     ('Montant de la facture', fcfa(f.total_ttc)), ('Motif de l\'avoir', a.motif)])
    lignes = [(lg['libelle'], str(lg['quantite']), f"− {fcfa(lg['prix_unitaire'])}",
               f"− {fcfa(lg['quantite'] * lg['prix_unitaire'])}") for lg in a.lignes]
    totaux = [('Total de l\'avoir', f"− {fcfa(a.total_ttc)}")]
    if a.tva:
        totaux = [('Total HT', f"− {fcfa(a.total_ht)}"), (f"TVA {_taux(a.taux_tva)} %", f"− {fcfa(a.tva)}"),
                  ('Total TTC de l\'avoir', f"− {fcfa(a.total_ttc)}")]
    doc.montants(lignes, totaux)
    if not a.tva:
        doc.paragraphe('TVA non applicable.', 'petit')
    doc.paragraphe(f"Cet avoir neutralise {'la totalité' if a.total_ttc == f.total_ttc else 'une partie'} de la "
                   f"facture {f.numero}, qui reste inchangée. La somme correspondante est remboursée au client.", 'petit')
    return doc.en_pdf()


def nom(u) -> str:
    return f"{u.first_name} {u.last_name}".strip() or u.email


def facture(f: FactureModel) -> bytes:
    doc = Document('Facture', f.numero, sous_titre=f"émise le {date(f.emise_le)}",
                   destinataire=[x for x in (f.client_nom, f.client_adresse, f.client_email) if x])
    lignes = [(lg['libelle'], str(lg['quantite']), fcfa(lg['prix_unitaire']), fcfa(lg['quantite'] * lg['prix_unitaire'])) for lg in f.lignes]
    totaux = [('Total', fcfa(f.total_ttc))]
    if f.tva:
        totaux = [('Total HT', fcfa(f.total_ht)), (f"TVA {str(f.taux_tva).rstrip('0').rstrip('.').replace('.', ',')} %", fcfa(f.tva)),
                  ('Total TTC', fcfa(f.total_ttc))]
    doc.montants(lignes, totaux)
    if not f.tva:
        doc.paragraphe('TVA non applicable.', 'petit')
    if f.objet_type != 'libre':
        doc.paragraphe('Facture acquittée : réglée en ligne lors de la réservation.', 'petit')
    return doc.en_pdf()


def document_caution(d: DocumentCautionModel) -> bytes:
    """REC receipt or RET notice of a deposit: what was held, given back, kept and why."""
    retenue = d.type == 'RET'
    doc = Document('Avis de retenue sur caution' if retenue else 'Reçu de restitution de caution', d.numero,
                   sous_titre=f"émis le {date(d.emis_le)}", destinataire=[x for x in (d.client_nom, d.client_email) if x])
    doc.bloc('Caution', [('Réservation', d.reference), ('Caution versée', fcfa(d.montant_caution)),
                         ('Montant restitué', fcfa(d.montant_rendu)), ('Mode de restitution', d.mode_restitution),
                         *([('Montant retenu', fcfa(d.montant_retenu))] if retenue else [])])
    if retenue:
        doc.bloc('Décision motivée', [
            ('Motif', d.motif), ('Fondement', f"Conditions générales de vente, article {d.cgv_article}"),
            *([('Décision', d.decision)] if d.decision else []),
            ('Pièces justificatives', ', '.join(d.justificatifs) or '—'),
        ])
        doc.paragraphe("La somme retenue est versée au propriétaire pour réparer le préjudice constaté. Vous pouvez "
                       "contester cette décision auprès de l'assistance Kwa-Ba en citant ce numéro d'avis.", 'petit')
    else:
        doc.paragraphe("La totalité de votre caution vous est restituée. Elle était conservée par Kwa-Ba pour votre "
                       "compte et n'a jamais constitué un revenu de Kwa-Ba.", 'petit')
    return doc.en_pdf()

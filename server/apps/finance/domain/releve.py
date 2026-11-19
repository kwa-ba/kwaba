"""Reading a bank statement exported as CSV (GL-22), pure: every bank exports its own columns, so the person who imports
says which column holds the date, the label, the amounts (debit and credit, or one signed amount) and, if any, the
bank's reference. Amounts are whole F CFA; a line that cannot be read stops the import with its line number."""
import csv
import hashlib
import io
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from .entities import ENTREE, SORTIE, LigneReleve
from .exceptions import VirementRefuse

FORMATS_DATE = ('%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d', '%d/%m/%y', '%d.%m.%Y')
LIGNES_MAX = 5000


def _jour(texte: str) -> date:
    texte = (texte or '').strip()
    for format_ in FORMATS_DATE:
        try:
            return datetime.strptime(texte[:10] if format_ == '%Y-%m-%d' else texte, format_).date()
        except ValueError:
            continue
    raise ValueError(f'date illisible « {texte} »')


def montant(texte: str) -> int | None:
    """« 1 234 567 », « 1.234.567 », « 1234567,00 », « -12 500 » → integer (None when empty)."""
    texte = (texte or '').upper()
    for unite in ('FCFA', 'CFA', 'XOF', 'F'):
        texte = texte.replace(unite, '')
    texte = texte.replace(' ', '').replace(' ', '').replace(' ', '')
    if not texte or texte in ('-', '+'):
        return None
    negatif = texte.startswith('-') or (texte.startswith('(') and texte.endswith(')'))
    texte = texte.strip('-+()')
    if ',' in texte and len(texte.rsplit(',', 1)[1]) <= 2:
        entier, decimales = texte.rsplit(',', 1)
        texte = entier.replace('.', '').replace(',', '') + '.' + decimales
    elif '.' in texte and len(texte.rsplit('.', 1)[1]) <= 2 and texte.count('.') == 1:
        pass
    else:
        texte = texte.replace('.', '').replace(',', '')
    try:
        valeur = int(Decimal(texte).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    except InvalidOperation:
        raise ValueError(f'montant illisible « {texte} »') from None
    return -valeur if negatif else valeur


def _delimiteur(texte: str) -> str:
    premiere = texte.splitlines()[0] if texte.strip() else ''
    return max((';', ',', '\t'), key=premiere.count)


def lire(texte: str, colonnes: dict[str, str]) -> list[LigneReleve]:
    """The lines of the statement. `colonnes`: {date, libelle, debit, credit} or {date, libelle, montant} (signed),
    plus `reference` if the bank gives one; names as in the first row of the file."""
    if not (texte or '').strip():
        raise VirementRefuse('Le fichier du relevé est vide.')
    lecteur = csv.DictReader(io.StringIO(texte.lstrip('﻿')), delimiter=_delimiteur(texte))
    entetes = {(e or '').strip(): e for e in (lecteur.fieldnames or [])}
    voulues = [c for c in ('date', 'libelle', 'debit', 'credit', 'montant', 'reference') if colonnes.get(c)]
    manquantes = [colonnes[c] for c in voulues if colonnes[c].strip() not in entetes]
    if manquantes:
        raise VirementRefuse(f'Colonne(s) absente(s) du fichier : {", ".join(manquantes)}. '
                             f'Colonnes trouvées : {", ".join(entetes) or "aucune"}.')
    if not colonnes.get('date') or not (colonnes.get('montant') or (colonnes.get('debit') and colonnes.get('credit'))):
        raise VirementRefuse('Indiquez la colonne de la date et celles du débit et du crédit (ou d\'un montant signé).')
    col = {c: entetes[colonnes[c].strip()] for c in voulues}
    lignes, erreurs, vues = [], [], {}
    for numero, rangee in enumerate(lecteur, start=2):
        if numero - 1 > LIGNES_MAX:
            raise VirementRefuse(f'{LIGNES_MAX} lignes au plus par import : découpez le relevé.')
        if not any((v or '').strip() for v in rangee.values()):
            continue
        try:
            jour = _jour(rangee.get(col['date']))
            if 'montant' in col:
                valeur = montant(rangee.get(col['montant']))
                if not valeur:
                    continue
                somme, sens = abs(valeur), ENTREE if valeur > 0 else SORTIE
            else:
                debit, credit = montant(rangee.get(col['debit'])) or 0, montant(rangee.get(col['credit'])) or 0
                if debit and credit:
                    raise ValueError('débit et crédit sur la même ligne')
                if not (debit or credit):
                    continue
                somme, sens = (abs(credit), ENTREE) if credit else (abs(debit), SORTIE)
        except ValueError as erreur:
            erreurs.append(f'ligne {numero} : {erreur}')
            continue
        libelle = ' '.join((rangee.get(col.get('libelle', '')) or '').split())[:200]
        reference = ' '.join((rangee.get(col.get('reference', '')) or '').split())[:60]
        if not reference:
            # Stable across imports of the same statement: a line imported twice is the same operation
            base = f'{jour.isoformat()}|{libelle}|{somme}|{sens}'
            vues[base] = vues.get(base, 0) + 1
            reference = 'banque:' + hashlib.sha1(f'{base}|{vues[base]}'.encode()).hexdigest()[:16]
        lignes.append(LigneReleve(jour=jour, libelle=libelle, montant=somme, sens=sens, reference=reference))
    if erreurs:
        raise VirementRefuse('Relevé illisible, ' + ' ; '.join(erreurs[:5]) + (' …' if len(erreurs) > 5 else '') + '.')
    if not lignes:
        raise VirementRefuse('Aucune opération dans le relevé.')
    return lignes

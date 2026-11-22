"""Stored files removed together with their row."""
from django.db import transaction
from django.db.models.fields.files import FieldFile


def delete_after_commit(stored: FieldFile | None) -> None:
    """Deletes the file once the transaction is committed: if it is rolled back, the row and its file both stay."""
    if not stored:
        return
    storage, name = stored.storage, stored.name
    transaction.on_commit(lambda: storage.delete(name))

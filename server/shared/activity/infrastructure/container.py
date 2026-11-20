from shared.activity.application.service import ActivityService
from shared.activity.infrastructure.clock import DjangoClock
from shared.activity.infrastructure.lookups import DjangoPeopleLookup
from shared.activity.infrastructure.persistence.repositories import DjangoEntryRepository


def activity_service() -> ActivityService:
    return ActivityService(entries=DjangoEntryRepository(), people=DjangoPeopleLookup(), clock=DjangoClock())

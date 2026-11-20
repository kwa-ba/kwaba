from django.utils import timezone

from shared.activity.application.ports import Clock


class DjangoClock(Clock):
    def now(self):
        return timezone.now()

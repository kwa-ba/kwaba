from django.urls import path

from .views import DevicesView, PreferencesView

urlpatterns = [
    path('notifications/devices/', DevicesView.as_view(), name='notifications-devices'),
    path('users/me/notifications/', PreferencesView.as_view(), name='notifications-preferences'),
]

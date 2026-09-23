from django.apps import AppConfig


class ComplaintsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'complaints'

    def ready(self):
        # Register signal handlers (status history, e-mails, file clean-up)
        from . import signals  # noqa: F401
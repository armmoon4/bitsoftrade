from django.apps import AppConfig


class TradelogConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tradelog'

    def ready(self):
        import discipline.signals  # noqa: F401 — registers post_save signal on Trade
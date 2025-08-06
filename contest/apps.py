from django.apps import AppConfig

class ContestConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'contest'
    
    def ready(self):
        try:
            import contest.signals  # Import signals to register them
        except ImportError as e:
            print(f"Warning: Could not import contest signals: {e}")
            pass
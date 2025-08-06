from django.apps import AppConfig

class SubmissionConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'submission'
    
    def ready(self):
        try:
            import submission.signals  # Import signals to register them
        except ImportError as e:
            print(f"Warning: Could not import submission signals: {e}")
            pass
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from utils.constants import CacheKey
from .models import AntiCheatViolation

@receiver(post_save, sender=AntiCheatViolation)
@receiver(post_delete, sender=AntiCheatViolation)
def clear_contest_rank_cache(sender, instance, **kwargs):
    """
    Clear contest rank cache when violations are added or removed
    """
    try:
        contest_id = instance.contest.id
        cache_key = f"{CacheKey.contest_rank_cache}:{contest_id}"
        cache.delete(cache_key)
        print(f"Cleared contest rank cache for contest {contest_id}")
    except Exception as e:
        print(f"Error clearing contest rank cache: {e}")
        pass
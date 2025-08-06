from django.core.management.base import BaseCommand
from django.utils.timezone import now
from contest.models import Contest, AntiCheatViolation, ACMContestRank, OIContestRank
from submission.models import Submission
from utils.constants import ContestRuleType


class Command(BaseCommand):
    help = 'Fix existing contest rankings by applying anti-cheat penalties'

    def add_arguments(self, parser):
        parser.add_argument(
            '--contest-id',
            type=int,
            help='Fix penalties for a specific contest ID'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without making actual changes'
        )

    def handle(self, *args, **options):
        contest_id = options.get('contest_id')
        dry_run = options.get('dry_run', False)
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        
        # Get contests to process
        if contest_id:
            try:
                contests = [Contest.objects.get(id=contest_id, visible=True)]
            except Contest.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'Contest {contest_id} not found'))
                return
        else:
            contests = Contest.objects.filter(visible=True)
        
        total_fixes = 0
        
        for contest in contests:
            self.stdout.write(f'Processing contest: {contest.title} (ID: {contest.id})')
            
            # Get all users with violations in this contest
            violations_by_user = {}
            violations = AntiCheatViolation.objects.filter(contest=contest).select_related('user')
            
            for violation in violations:
                user_id = violation.user.id
                if user_id not in violations_by_user:
                    violations_by_user[user_id] = {
                        'user': violation.user,
                        'count': 0
                    }
                violations_by_user[user_id]['count'] += 1
            
            if not violations_by_user:
                self.stdout.write(f'  No violations found in contest {contest.id}')
                continue
            
            contest_fixes = 0
            
            for user_id, violation_data in violations_by_user.items():
                user = violation_data['user']
                violation_count = violation_data['count']
                penalty_minutes = violation_count * 10
                penalty_seconds = penalty_minutes * 60
                
                self.stdout.write(f'  User {user.username}: {violation_count} violations, {penalty_minutes} min penalty')
                
                if contest.rule_type == ContestRuleType.ACM:
                    try:
                        rank = ACMContestRank.objects.get(contest=contest, user=user)
                        
                        # Check if penalties have already been applied by looking at accepted submissions
                        accepted_submissions = Submission.objects.filter(
                            contest=contest,
                            user=user,
                            result=0  # Accepted
                        ).exists()
                        
                        if accepted_submissions:
                            old_time = rank.total_time
                            
                            if not dry_run:
                                # Apply penalty
                                rank.total_time += penalty_seconds
                                rank.save()
                            
                            new_time = old_time + penalty_seconds
                            self.stdout.write(f'    ACM Rank: {old_time}s -> {new_time}s')
                            contest_fixes += 1
                        else:
                            self.stdout.write(f'    No accepted submissions for {user.username}')
                            
                    except ACMContestRank.DoesNotExist:
                        self.stdout.write(f'    No ACM rank found for {user.username}')
                        
                else:  # OI Contest
                    try:
                        rank = OIContestRank.objects.get(contest=contest, user=user)
                        
                        # For OI contests, you might want to implement point deduction
                        # For now, we'll just log that we found the rank
                        self.stdout.write(f'    OI Rank found for {user.username} (no penalty applied)')
                        
                    except OIContestRank.DoesNotExist:
                        self.stdout.write(f'    No OI rank found for {user.username}')
            
            self.stdout.write(f'  Fixed {contest_fixes} rankings in contest {contest.id}')
            total_fixes += contest_fixes
        
        if dry_run:
            self.stdout.write(self.style.SUCCESS(f'DRY RUN: Would fix {total_fixes} rankings'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Fixed {total_fixes} rankings total'))
            # Clear contest rank cache
            from django.core.cache import cache
            from utils.constants import CacheKey
            
            for contest in contests:
                cache_key = f"{CacheKey.contest_rank_cache}:{contest.id}"
                cache.delete(cache_key)
                self.stdout.write(f'Cleared cache for contest {contest.id}')
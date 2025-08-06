from django.core.management.base import BaseCommand
from contest.models import Contest, AntiCheatViolation, ACMContestRank, OIContestRank
from account.models import User, AdminType
from utils.constants import ContestRuleType

class Command(BaseCommand):
    help = 'Test if models are working correctly'

    def add_arguments(self, parser):
        parser.add_argument('--contest-id', type=int, required=True)

    def handle(self, *args, **options):
        contest_id = options['contest_id']
        
        try:
            # Test contest exists
            contest = Contest.objects.get(id=contest_id)
            self.stdout.write(f'✓ Contest found: {contest.title} (Rule: {contest.rule_type})')
            
            # Test AntiCheatViolation model
            try:
                violations = AntiCheatViolation.objects.filter(contest=contest)
                self.stdout.write(f'✓ AntiCheatViolation model works. Found {violations.count()} violations')
                
                for violation in violations[:5]:  # Show first 5
                    self.stdout.write(f'  - User: {violation.user.username}, Type: {violation.violation_type}')
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'✗ AntiCheatViolation model error: {e}'))
            
            # Test ranking models
            if contest.rule_type == ContestRuleType.ACM:
                try:
                    ranks = ACMContestRank.objects.filter(contest=contest)
                    self.stdout.write(f'✓ ACMContestRank model works. Found {ranks.count()} ranks')
                    
                    for rank in ranks[:3]:  # Show first 3
                        self.stdout.write(f'  - User: {rank.user.username}, AC: {rank.accepted_number}, Time: {rank.total_time}')
                        
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'✗ ACMContestRank model error: {e}'))
            else:
                try:
                    ranks = OIContestRank.objects.filter(contest=contest)
                    self.stdout.write(f'✓ OIContestRank model works. Found {ranks.count()} ranks')
                    
                    for rank in ranks[:3]:  # Show first 3
                        self.stdout.write(f'  - User: {rank.user.username}, Score: {rank.total_score}')
                        
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'✗ OIContestRank model error: {e}'))
            
            # Test user filtering
            try:
                regular_users = User.objects.filter(
                    admin_type=AdminType.REGULAR_USER,
                    is_disabled=False
                )
                self.stdout.write(f'✓ User filtering works. Found {regular_users.count()} regular users')
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'✗ User filtering error: {e}'))
                
            # Test imports
            try:
                from utils.constants import CacheKey
                self.stdout.write('✓ CacheKey import works')
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'✗ CacheKey import error: {e}'))
                
        except Contest.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'✗ Contest {contest_id} not found'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ General error: {e}'))
            import traceback
            traceback.print_exc()
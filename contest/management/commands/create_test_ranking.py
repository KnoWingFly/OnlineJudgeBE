from django.core.management.base import BaseCommand
from contest.models import Contest, AntiCheatViolation, ACMContestRank, OIContestRank
from account.models import User, AdminType
from utils.constants import ContestRuleType

class Command(BaseCommand):
    help = 'Create test ranking data for debugging'

    def add_arguments(self, parser):
        parser.add_argument('--contest-id', type=int, required=True)

    def handle(self, *args, **options):
        contest_id = options['contest_id']
        
        try:
            contest = Contest.objects.get(id=contest_id)
            self.stdout.write(f'Creating test data for contest: {contest.title}')
            
            # Get regular users
            users = User.objects.filter(
                admin_type=AdminType.REGULAR_USER,
                is_disabled=False
            )[:3]  # Get first 3 users
            
            if not users:
                self.stdout.write(self.style.ERROR('No regular users found'))
                return
            
            # Create test ranking data based on contest type
            if contest.rule_type == ContestRuleType.ACM:
                for i, user in enumerate(users):
                    # Check if rank already exists
                    rank, created = ACMContestRank.objects.get_or_create(
                        contest=contest,
                        user=user,
                        defaults={
                            'submission_number': (i + 1) * 3,
                            'accepted_number': i + 1,
                            'total_time': (i + 1) * 1800,  # 30 minutes, 60 minutes, 90 minutes
                            'submission_info': {}
                        }
                    )
                    if created:
                        self.stdout.write(f'Created ACM rank for {user.username}')
                    else:
                        self.stdout.write(f'ACM rank already exists for {user.username}')
            else:
                for i, user in enumerate(users):
                    # Check if rank already exists
                    rank, created = OIContestRank.objects.get_or_create(
                        contest=contest,
                        user=user,
                        defaults={
                            'total_score': (3 - i) * 100,  # 300, 200, 100 points
                            'submission_info': {}
                        }
                    )
                    if created:
                        self.stdout.write(f'Created OI rank for {user.username}')
                    else:
                        self.stdout.write(f'OI rank already exists for {user.username}')
            
            # Create a test violation for the first user
            if users:
                violation, created = AntiCheatViolation.objects.get_or_create(
                    contest=contest,
                    user=users[0],
                    violation_type='test_violation',
                    defaults={
                        'violation_details': 'Test violation for debugging',
                        'ip_address': '127.0.0.1',
                        'user_agent': 'Test Command'
                    }
                )
                if created:
                    self.stdout.write(f'Created test violation for {users[0].username}')
                else:
                    self.stdout.write(f'Test violation already exists for {users[0].username}')
            
            self.stdout.write(self.style.SUCCESS('Test data creation complete'))
            
        except Contest.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Contest {contest_id} not found'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {str(e)}'))
            import traceback
            traceback.print_exc()
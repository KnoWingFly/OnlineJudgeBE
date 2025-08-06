# management/commands/debug_anti_cheat.py
from django.core.management.base import BaseCommand
from django.db.models.signals import post_save
from contest.models import Contest, AntiCheatViolation, ACMContestRank, OIContestRank
from submission.models import Submission
from account.models import User, AdminType
from utils.constants import ContestRuleType

class Command(BaseCommand):
    help = 'Debug anti-cheat penalty system'

    def add_arguments(self, parser):
        parser.add_argument('--contest-id', type=int, required=True)
        parser.add_argument('--user-id', type=int, required=True)
        parser.add_argument('--problem-id', type=int, required=True)
        parser.add_argument('--create-violation', action='store_true', help='Create a test violation')
        parser.add_argument('--simulate-submission', action='store_true', help='Simulate an accepted submission')

    def handle(self, *args, **options):
        contest_id = options['contest_id']
        user_id = options['user_id']
        problem_id = options['problem_id']
        
        try:
            contest = Contest.objects.get(id=contest_id)
            user = User.objects.get(id=user_id)
            
            self.stdout.write(f'Debugging for Contest: {contest.title} (ID: {contest_id})')
            self.stdout.write(f'Contest Rule Type: {contest.rule_type}')
            self.stdout.write(f'User: {user.username} (ID: {user_id})')
            
            # Check current violations
            violations = AntiCheatViolation.objects.filter(contest=contest, user=user)
            self.stdout.write(f'Current violations: {violations.count()}')
            
            # Check current ranking
            if contest.rule_type == ContestRuleType.ACM:
                try:
                    rank = ACMContestRank.objects.get(contest=contest, user=user)
                    self.stdout.write(f'Current ACM rank - Time: {rank.total_time}, Accepted: {rank.accepted_number}')
                except ACMContestRank.DoesNotExist:
                    self.stdout.write('No ACM ranking found')
            else:
                try:
                    rank = OIContestRank.objects.get(contest=contest, user=user)
                    self.stdout.write(f'Current OI rank - Score: {rank.total_score}')
                except OIContestRank.DoesNotExist:
                    self.stdout.write('No OI ranking found')
            
            if options['create_violation']:
                # Create a test violation
                violation = AntiCheatViolation.objects.create(
                    contest=contest,
                    user=user,
                    violation_type='debug_test',
                    violation_details='Debug test violation',
                    ip_address='127.0.0.1',
                    user_agent='Debug Command'
                )
                self.stdout.write(f'Created violation: {violation.id}')
            
            if options['simulate_submission']:
                # Check if there are existing submissions
                existing_submissions = Submission.objects.filter(
                    contest=contest,
                    user_id=user_id,
                    problem_id=problem_id
                )
                self.stdout.write(f'Existing submissions: {existing_submissions.count()}')
                
                # Create or update a submission to be accepted
                if existing_submissions.exists():
                    submission = existing_submissions.first()
                    old_result = submission.result
                    submission.result = 0  # Set to accepted
                    submission.save()
                    self.stdout.write(f'Updated submission {submission.id} result from {old_result} to 0 (accepted)')
                else:
                    # Create a new accepted submission
                    submission = Submission.objects.create(
                        problem_id=problem_id,
                        user_id=user_id,
                        contest=contest,
                        result=0,  # Accepted
                        code='# Debug test submission',
                        language='Python3',
                        statistic_info={}
                    )
                    self.stdout.write(f'Created new accepted submission: {submission.id}')
                
                # Check ranking after submission
                if contest.rule_type == ContestRuleType.ACM:
                    try:
                        rank = ACMContestRank.objects.get(contest=contest, user=user)
                        self.stdout.write(f'Updated ACM rank - Time: {rank.total_time}, Accepted: {rank.accepted_number}')
                    except ACMContestRank.DoesNotExist:
                        self.stdout.write('Still no ACM ranking found after submission')
                else:
                    try:
                        rank = OIContestRank.objects.get(contest=contest, user=user)
                        self.stdout.write(f'Updated OI rank - Score: {rank.total_score}')
                    except OIContestRank.DoesNotExist:
                        self.stdout.write('Still no OI ranking found after submission')
            
            # Final violation count
            final_violations = AntiCheatViolation.objects.filter(contest=contest, user=user)
            self.stdout.write(f'Final violations count: {final_violations.count()}')
            
        except Contest.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Contest {contest_id} not found'))
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'User {user_id} not found'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {str(e)}'))
            import traceback
            traceback.print_exc()
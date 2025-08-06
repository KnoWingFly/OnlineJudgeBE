from django.core.management.base import BaseCommand
from contest.models import Contest, AntiCheatViolation, ACMContestRank, OIContestRank
from account.models import User, AdminType
from utils.constants import ContestRuleType

class Command(BaseCommand):
    help = 'Recalculate contest rankings with anti-cheat penalties'

    def add_arguments(self, parser):
        parser.add_argument('--contest-id', type=int, required=True)
        parser.add_argument('--force', action='store_true', help='Force recalculation even if no violations')
        parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')

    def handle(self, *args, **options):
        contest_id = options['contest_id']
        force = options['force']
        dry_run = options['dry_run']
        
        try:
            contest = Contest.objects.get(id=contest_id)
            self.stdout.write(f'Processing Contest: {contest.title} (ID: {contest_id})')
            self.stdout.write(f'Contest Rule Type: {contest.rule_type}')
            
            if dry_run:
                self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
            
            # Check for violations
            violations = AntiCheatViolation.objects.filter(contest=contest)
            violation_count = violations.count()
            
            self.stdout.write(f'Total violations in contest: {violation_count}')
            
            if violation_count == 0 and not force:
                self.stdout.write(self.style.WARNING('No violations found and --force not specified. Exiting.'))
                return
            
            # Show violation summary
            if violation_count > 0:
                self.stdout.write('\nViolation Summary:')
                violation_summary = violations.values('user__username', 'violation_type').distinct()
                for v in violation_summary:
                    user_violations = violations.filter(user__username=v['user__username'])
                    self.stdout.write(f"  {v['user__username']}: {user_violations.count()} violations")
            
            # Get all participants
            if contest.rule_type == ContestRuleType.ACM:
                ranks = ACMContestRank.objects.filter(contest=contest).select_related('user')
                self.stdout.write(f'\nCurrent ACM Rankings ({ranks.count()} participants):')
                
                for rank in ranks.order_by('-accepted_number', 'total_time'):
                    user_violations = violations.filter(user=rank.user).count()
                    penalty_time = user_violations * 600  # 10 minutes in seconds
                    
                    self.stdout.write(
                        f"  {rank.user.username}: "
                        f"AC={rank.accepted_number}, "
                        f"Time={rank.total_time}s, "
                        f"Violations={user_violations}, "
                        f"Penalty={penalty_time}s"
                    )
                    
                    if not dry_run and user_violations > 0:
                        # Apply penalty if not already applied
                        new_total_time = rank.total_time
                        
                        # Simple approach: ensure penalty is included
                        # Calculate base time from submissions
                        from submission.models import Submission
                        accepted_submissions = Submission.objects.filter(
                            contest=contest,
                            user_id=rank.user.id,
                            result=0
                        )
                        
                        # Recalculate time
                        base_time = 0
                        for sub in accepted_submissions:
                            time_diff = sub.create_time - contest.start_time
                            base_time += time_diff.total_seconds()
                        
                        # Add wrong submission penalties (this is standard ACM)
                        wrong_submissions = Submission.objects.filter(
                            contest=contest,
                            user_id=rank.user.id
                        ).exclude(result=0)
                        
                        # Group by problem to count wrong attempts before AC
                        from collections import defaultdict
                        problem_attempts = defaultdict(list)
                        for sub in Submission.objects.filter(contest=contest, user_id=rank.user.id).order_by('create_time'):
                            problem_attempts[sub.problem_id].append(sub)
                        
                        wrong_penalty = 0
                        for problem_id, attempts in problem_attempts.items():
                            wrong_count = 0
                            for attempt in attempts:
                                if attempt.result == 0:  # Found AC
                                    break
                                wrong_count += 1
                            wrong_penalty += wrong_count * 1200  # 20 minutes per wrong attempt
                        
                        # Calculate final time with all penalties
                        final_time = int(base_time + wrong_penalty + penalty_time)
                        
                        if final_time != rank.total_time:
                            old_time = rank.total_time
                            rank.total_time = final_time
                            rank.save()
                            
                            self.stdout.write(self.style.SUCCESS(
                                f"    Updated {rank.user.username}: {old_time}s -> {final_time}s"
                            ))
                        else:
                            self.stdout.write(f"    No change needed for {rank.user.username}")
                            
            else:  # OI Contest
                ranks = OIContestRank.objects.filter(contest=contest).select_related('user')
                self.stdout.write(f'\nCurrent OI Rankings ({ranks.count()} participants):')
                
                for rank in ranks.order_by('-total_score'):
                    user_violations = violations.filter(user=rank.user).count()
                    penalty_points = user_violations * 10  # 10 points per violation
                    
                    self.stdout.write(
                        f"  {rank.user.username}: "
                        f"Score={rank.total_score}, "
                        f"Violations={user_violations}, "
                        f"Penalty={penalty_points} points"
                    )
                    
                    if not dry_run and user_violations > 0:
                        # For OI, we need to be more careful about score calculation
                        # Let's recalculate from submissions
                        from submission.models import Submission
                        
                        total_score = 0
                        problems = contest.problem_set.all()
                        
                        for problem in problems:
                            best_sub = Submission.objects.filter(
                                contest=contest,
                                user_id=rank.user.id,
                                problem=problem
                            ).order_by('-score', 'create_time').first()
                            
                            if best_sub and best_sub.score:
                                total_score += best_sub.score
                        
                        # Apply anti-cheat penalty
                        final_score = max(0, total_score - penalty_points)
                        
                        if final_score != rank.total_score:
                            old_score = rank.total_score
                            rank.total_score = final_score
                            rank.save()
                            
                            self.stdout.write(self.style.SUCCESS(
                                f"    Updated {rank.user.username}: {old_score} -> {final_score} points"
                            ))
                        else:
                            self.stdout.write(f"    No change needed for {rank.user.username}")
            
            if not dry_run:
                self.stdout.write(self.style.SUCCESS('\nRanking recalculation complete!'))
            else:
                self.stdout.write(self.style.WARNING('\nDry run complete - no changes made'))
                
        except Contest.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Contest {contest_id} not found'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {str(e)}'))
            import traceback
            traceback.print_exc()
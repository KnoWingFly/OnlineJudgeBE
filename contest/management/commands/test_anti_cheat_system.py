# management/commands/test_anti_cheat_system.py
from django.core.management.base import BaseCommand
from django.db import transaction
from django.core.cache import cache
from contest.models import Contest, AntiCheatViolation, ACMContestRank, OIContestRank
from submission.models import Submission
from account.models import User, AdminType
from problem.models import Problem
from utils.constants import ContestRuleType, CacheKey
from django.utils.timezone import now
from datetime import timedelta
import time

class Command(BaseCommand):
    help = 'Test the complete anti-cheat system end-to-end'

    def add_arguments(self, parser):
        parser.add_argument('--contest-id', type=int, required=True)
        parser.add_argument('--user-id', type=int, required=True)
        parser.add_argument('--clean-start', action='store_true', 
                          help='Clean existing data for this user in this contest')
        parser.add_argument('--test-api', action='store_true',
                          help='Test API responses as well')

    def handle(self, *args, **options):
        contest_id = options['contest_id']
        user_id = options['user_id']
        clean_start = options['clean_start']
        test_api = options['test_api']
        
        try:
            contest = Contest.objects.get(id=contest_id)
            user = User.objects.get(id=user_id)
            
            self.stdout.write(self.style.SUCCESS('=' * 60))
            self.stdout.write(self.style.SUCCESS('🧪 ANTI-CHEAT SYSTEM TEST'))
            self.stdout.write(self.style.SUCCESS('=' * 60))
            self.stdout.write(f'Contest: {contest.title} (ID: {contest_id}, Type: {contest.rule_type})')
            self.stdout.write(f'User: {user.username} (ID: {user_id})')
            self.stdout.write(f'Contest Start: {contest.start_time}')
            self.stdout.write(f'Contest End: {contest.end_time}')
            
            if clean_start:
                self.stdout.write('\n' + '=' * 40)
                self.stdout.write('🧹 CLEANING EXISTING DATA')
                self.stdout.write('=' * 40)
                
                # Clean existing data
                violations_deleted = AntiCheatViolation.objects.filter(contest=contest, user=user).count()
                submissions_deleted = Submission.objects.filter(contest=contest, user_id=user.id).count()
                
                AntiCheatViolation.objects.filter(contest=contest, user=user).delete()
                Submission.objects.filter(contest=contest, user_id=user.id).delete()
                
                if contest.rule_type == ContestRuleType.ACM:
                    ranks_deleted = ACMContestRank.objects.filter(contest=contest, user=user).count()
                    ACMContestRank.objects.filter(contest=contest, user=user).delete()
                else:
                    ranks_deleted = OIContestRank.objects.filter(contest=contest, user=user).count()
                    OIContestRank.objects.filter(contest=contest, user=user).delete()
                
                # Clear cache
                cache_key = f"{CacheKey.contest_rank_cache}:{contest.id}"
                cache.delete(cache_key)
                
                self.stdout.write(f'✅ Deleted: {violations_deleted} violations, {submissions_deleted} submissions')
                self.stdout.write('✅ Cleared contest rank cache')
            
            # Get problems from the contest
            problems = list(contest.problem_set.all()[:3])  # Get up to 3 problems
            if not problems:
                self.stdout.write(self.style.ERROR('❌ No problems found in contest'))
                return
            
            self.stdout.write(f'\n📝 Available problems: {len(problems)}')
            for i, p in enumerate(problems):
                self.stdout.write(f'  {i+1}. {p.title} (ID: {p.id})')
            
            # Test Scenario 1: Initial state
            self.stdout.write('\n' + '=' * 40)
            self.stdout.write('📊 STEP 1: INITIAL STATE')
            self.stdout.write('=' * 40)
            self.check_current_ranking(contest, user, "Initial state")
            
            # Test Scenario 2: Create wrong submissions
            self.stdout.write('\n' + '=' * 40)
            self.stdout.write('❌ STEP 2: CREATE WRONG SUBMISSIONS')
            self.stdout.write('=' * 40)
            
            wrong_submissions = []
            for i, problem in enumerate(problems[:2]):  # Use first 2 problems
                submission = Submission.objects.create(
                    problem=problem,
                    user_id=user.id,
                    username=user.username,
                    contest=contest,
                    result=1,  # Wrong Answer
                    code=f'print("wrong answer for problem {problem.id}")',
                    language='Python3',
                    statistic_info={},
                    ip='127.0.0.1'
                )
                wrong_submissions.append(submission)
                self.stdout.write(f'  ➕ Created wrong submission for {problem.title}: {submission.id}')
                time.sleep(1)  # Small delay to ensure different timestamps
            
            self.check_current_ranking(contest, user, "After wrong submissions")
            
            # Test Scenario 3: Create first violation
            self.stdout.write('\n' + '=' * 40)
            self.stdout.write('🚨 STEP 3: CREATE ANTI-CHEAT VIOLATIONS')
            self.stdout.write('=' * 40)
            
            violations = []
            violation_types = ['fullscreen_exit', 'tab_switch', 'dev_tools', 'window_blur']
            
            for i, violation_type in enumerate(violation_types[:2]):  # Create 2 violations
                violation = AntiCheatViolation.objects.create(
                    contest=contest,
                    user=user,
                    problem=problems[i % len(problems)],  # Assign to different problems
                    violation_type=violation_type,
                    violation_details=f'Test violation #{i+1}: {violation_type}',
                    ip_address='127.0.0.1',
                    user_agent='Test Command'
                )
                violations.append(violation)
                self.stdout.write(f'  ⚠️  Created violation: {violation_type} on problem {violation.problem.title}')
                time.sleep(1)
            
            self.check_current_ranking(contest, user, "After violations")
            
            # Test Scenario 4: Create accepted submissions
            self.stdout.write('\n' + '=' * 40)
            self.stdout.write('✅ STEP 4: CREATE ACCEPTED SUBMISSIONS')
            self.stdout.write('=' * 40)
            
            accepted_submissions = []
            for i, problem in enumerate(problems[:2]):  # Accept first 2 problems
                # Calculate time from contest start (simulate realistic solve times)
                solve_time_minutes = 30 + (i * 20)  # 30, 50 minutes
                create_time = contest.start_time + timedelta(minutes=solve_time_minutes)
                
                submission = Submission.objects.create(
                    problem=problem,
                    user_id=user.id,
                    username=user.username,
                    contest=contest,
                    result=0,  # Accepted
                    code=f'print("correct answer for problem {problem.id}")',
                    language='Python3',
                    statistic_info={'score': 100} if contest.rule_type == ContestRuleType.OI else {},
                    ip='127.0.0.1'
                )
                # Manually set create_time to simulate realistic timing
                submission.create_time = create_time
                submission.save()
                
                accepted_submissions.append(submission)
                self.stdout.write(f'  ✅ Accepted submission for {problem.title}: {submission.id} '
                                f'(solved at {solve_time_minutes} min)')
                time.sleep(1)
            
            self.check_current_ranking(contest, user, "After accepted submissions")
            
            # Test Scenario 5: Create more violations
            self.stdout.write('\n' + '=' * 40)
            self.stdout.write('🚨 STEP 5: CREATE MORE VIOLATIONS')
            self.stdout.write('=' * 40)
            
            for i, violation_type in enumerate(['context_menu', 'page_leave']):
                violation = AntiCheatViolation.objects.create(
                    contest=contest,
                    user=user,
                    problem=problems[0] if i == 0 else None,  # One with problem, one general
                    violation_type=violation_type,
                    violation_details=f'Additional test violation: {violation_type}',
                    ip_address='127.0.0.1',
                    user_agent='Test Command'
                )
                violations.append(violation)
                problem_info = f"on problem {violation.problem.title}" if violation.problem else "general"
                self.stdout.write(f'  ⚠️  Created violation: {violation_type} {problem_info}')
                time.sleep(1)
            
            self.check_current_ranking(contest, user, "After additional violations")
            
            # Test Scenario 6: Manual recalculation
            self.stdout.write('\n' + '=' * 40)
            self.stdout.write('🔄 STEP 6: TEST MANUAL RECALCULATION')
            self.stdout.write('=' * 40)
            
            try:
                if contest.rule_type == ContestRuleType.ACM:
                    from submission.signals import recalculate_acm_ranking_with_penalties
                    rank = recalculate_acm_ranking_with_penalties(user, contest)
                else:
                    from submission.signals import recalculate_oi_ranking_with_penalties
                    rank = recalculate_oi_ranking_with_penalties(user, contest)
                
                if rank:
                    self.stdout.write('✅ Manual recalculation successful')
                    self.check_current_ranking(contest, user, "After manual recalculation")
                else:
                    self.stdout.write('❌ Manual recalculation failed')
            except Exception as e:
                self.stdout.write(f'❌ Manual recalculation error: {e}')
            
            # Test Scenario 7: API Testing (if requested)
            if test_api:
                self.stdout.write('\n' + '=' * 40)
                self.stdout.write('🌐 STEP 7: TEST API RESPONSES')
                self.stdout.write('=' * 40)
                self.test_api_responses(contest, user)
            
            # Final Summary
            self.stdout.write('\n' + '=' * 50)
            self.stdout.write('📋 FINAL SUMMARY')
            self.stdout.write('=' * 50)
            
            final_violations = AntiCheatViolation.objects.filter(contest=contest, user=user)
            final_submissions = Submission.objects.filter(contest=contest, user_id=user.id)
            
            self.stdout.write(f'📊 Statistics:')
            self.stdout.write(f'  • Total violations: {final_violations.count()}')
            self.stdout.write(f'  • Total submissions: {final_submissions.count()}')
            self.stdout.write(f'  • Accepted submissions: {final_submissions.filter(result=0).count()}')
            self.stdout.write(f'  • Wrong submissions: {final_submissions.filter(result__gt=0).count()}')
            
            # Violation breakdown
            violation_types = final_violations.values_list('violation_type', flat=True)
            from collections import Counter
            violation_counts = Counter(violation_types)
            self.stdout.write(f'  • Violation breakdown:')
            for vtype, count in violation_counts.items():
                self.stdout.write(f'    - {vtype}: {count}')
            
            if contest.rule_type == ContestRuleType.ACM:
                expected_penalty = final_violations.count() * 600  # 10 minutes per violation
                self.stdout.write(f'  • Expected anti-cheat penalty: {expected_penalty} seconds ({expected_penalty/60:.1f} minutes)')
            else:
                expected_penalty = final_violations.count() * 10  # 10 points per violation
                self.stdout.write(f'  • Expected anti-cheat penalty: {expected_penalty} points')
            
            self.check_current_ranking(contest, user, "FINAL RANKING")
            
            self.stdout.write('\n' + self.style.SUCCESS('=' * 60))
            self.stdout.write(self.style.SUCCESS('🎉 ANTI-CHEAT SYSTEM TEST COMPLETED!'))
            self.stdout.write(self.style.SUCCESS('=' * 60))
            
        except Contest.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'❌ Contest {contest_id} not found'))
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'❌ User {user_id} not found'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error: {str(e)}'))
            import traceback
            traceback.print_exc()
    
    def check_current_ranking(self, contest, user, step_name=""):
        """Helper method to check and display current ranking"""
        try:
            self.stdout.write(f'\n  📊 {step_name}:')
            
            if contest.rule_type == ContestRuleType.ACM:
                try:
                    rank = ACMContestRank.objects.get(contest=contest, user=user)
                    self.stdout.write(f'    🏆 ACM Ranking:')
                    self.stdout.write(f'      • Accepted: {rank.accepted_number} problems')
                    self.stdout.write(f'      • Total Time: {rank.total_time}s ({rank.total_time/60:.1f} minutes)')
                    self.stdout.write(f'      • Submissions: {rank.submission_number}')
                    
                    # Show problem details if available
                    if rank.submission_info:
                        self.stdout.write(f'      • Problem Details:')
                        for prob_id, info in rank.submission_info.items():
                            if info.get('is_ac'):
                                ac_time_min = info['ac_time'] / 60
                                self.stdout.write(f'        - Problem {prob_id}: ✅ {ac_time_min:.1f}min '
                                                f'(errors: {info.get("error_number", 0)})')
                            else:
                                self.stdout.write(f'        - Problem {prob_id}: ❌ {info.get("error_number", 0)} errors')
                except ACMContestRank.DoesNotExist:
                    self.stdout.write('    ❌ No ACM ranking found')
            else:
                try:
                    rank = OIContestRank.objects.get(contest=contest, user=user)
                    self.stdout.write(f'    🏆 OI Ranking:')
                    self.stdout.write(f'      • Total Score: {rank.total_score} points')
                    self.stdout.write(f'      • Submissions: {rank.submission_number}')
                    
                    # Show problem scores if available
                    if rank.submission_info:
                        self.stdout.write(f'      • Problem Scores:')
                        for prob_id, score in rank.submission_info.items():
                            if isinstance(score, dict):
                                self.stdout.write(f'        - Problem {prob_id}: {score.get("score", 0)} points')
                            else:
                                self.stdout.write(f'        - Problem {prob_id}: {score} points')
                except OIContestRank.DoesNotExist:
                    self.stdout.write('    ❌ No OI ranking found')
                    
            # Always show violation information
            violations = AntiCheatViolation.objects.filter(contest=contest, user=user)
            violation_count = violations.count()
            self.stdout.write(f'    ⚠️  Violations: {violation_count}')
            
            if violation_count > 0:
                # Group violations by problem
                problem_violations = {}
                general_violations = 0
                
                for violation in violations:
                    if violation.problem:
                        prob_id = str(violation.problem.id)
                        if prob_id not in problem_violations:
                            problem_violations[prob_id] = []
                        problem_violations[prob_id].append(violation.violation_type)
                    else:
                        general_violations += 1
                
                if problem_violations:
                    self.stdout.write(f'      • Problem-specific violations:')
                    for prob_id, vtypes in problem_violations.items():
                        self.stdout.write(f'        - Problem {prob_id}: {len(vtypes)} ({", ".join(set(vtypes))})')
                
                if general_violations:
                    self.stdout.write(f'      • General violations: {general_violations}')
                
                # Calculate expected penalties
                if contest.rule_type == ContestRuleType.ACM:
                    penalty_seconds = violation_count * 600
                    self.stdout.write(f'      • Expected penalty: {penalty_seconds}s ({penalty_seconds/60:.1f} min)')
                else:
                    penalty_points = violation_count * 10
                    self.stdout.write(f'      • Expected penalty: {penalty_points} points')
            
        except Exception as e:
            self.stdout.write(f'    ❌ Error checking ranking: {e}')
            import traceback
            traceback.print_exc()
    
    def test_api_responses(self, contest, user):
        """Test API endpoint responses"""
        try:
            from contest.views.oj import ContestRankAPI
            from django.test import RequestFactory
            from django.contrib.auth.models import AnonymousUser
            
            self.stdout.write('  🌐 Testing ContestRankAPI...')
            
            # Create a mock request
            factory = RequestFactory()
            request = factory.get(f'/api/contest/rank/?contest_id={contest.id}')
            request.user = user
            
            # Test the API
            api = ContestRankAPI()
            api.contest = contest
            
            try:
                ranking_data = api.get_rank()
                self.stdout.write(f'    ✅ API returned {len(ranking_data)} ranking entries')
                
                # Find our test user's data
                user_ranking = None
                for rank in ranking_data:
                    if rank.user.id == user.id:
                        user_ranking = rank
                        break
                
                if user_ranking:
                    self.stdout.write(f'    ✅ Found user ranking in API response')
                    if hasattr(user_ranking, 'violation_count'):
                        self.stdout.write(f'      • Violations: {user_ranking.violation_count}')
                        if contest.rule_type == ContestRuleType.ACM:
                            self.stdout.write(f'      • Penalty Time: {getattr(user_ranking, "penalty_time", 0)}s')
                            self.stdout.write(f'      • Total Time with Penalty: {getattr(user_ranking, "total_time_with_penalty", 0)}s')
                        else:
                            self.stdout.write(f'      • Penalty Points: {getattr(user_ranking, "penalty_points", 0)}')
                            self.stdout.write(f'      • Score with Penalty: {getattr(user_ranking, "total_score_with_penalty", 0)}')
                    else:
                        self.stdout.write(f'    ⚠️  No violation data in API response')
                else:
                    self.stdout.write(f'    ❌ User not found in API response')
                    
            except Exception as e:
                self.stdout.write(f'    ❌ API test failed: {e}')
                
        except Exception as e:
            self.stdout.write(f'  ❌ API testing failed: {e}')
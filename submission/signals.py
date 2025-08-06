# from django.db.models.signals import post_save
# from django.dispatch import receiver
# from django.utils.timezone import now
# from django.db import transaction
# from django.core.cache import cache
# from datetime import timedelta

# from .models import Submission
# from utils.constants import ContestRuleType, CacheKey

# # Import with error handling
# try:
#     from contest.models import AntiCheatViolation, ACMContestRank, OIContestRank
#     ANTI_CHEAT_AVAILABLE = True
# except ImportError:
#     print("Warning: AntiCheatViolation model not available")
#     ANTI_CHEAT_AVAILABLE = False


# def clear_contest_rank_cache(contest_id):
#     """Clear contest ranking cache"""
#     cache_key = f"{CacheKey.contest_rank_cache}:{contest_id}"
#     cache.delete(cache_key)
#     print(f"Cleared contest rank cache for contest {contest_id}")


# def recalculate_acm_ranking_with_penalties(user, contest):
#     """
#     Recalculate ACM ranking including violation penalties
#     """
#     try:
#         print(f"Recalculating ACM ranking for user {user.username} in contest {contest.id}")
        
#         # Get all submissions for this user in this contest
#         submissions = Submission.objects.filter(
#             contest=contest,
#             user_id=user.id,
#             create_time__gte=contest.start_time  # Only submissions after contest start
#         ).order_by('create_time')
        
#         # Get violation count
#         violation_count = AntiCheatViolation.objects.filter(
#             contest=contest,
#             user=user
#         ).count()
        
#         print(f"Found {submissions.count()} submissions and {violation_count} violations")
        
#         # Calculate ACM metrics from scratch
#         accepted_problems = set()
#         base_total_time = 0  # Time without anti-cheat penalties
#         submission_count = submissions.count()
#         submission_info = {}
        
#         # Group submissions by problem
#         from collections import defaultdict
#         problem_submissions = defaultdict(list)
#         for sub in submissions:
#             problem_submissions[sub.problem_id].append(sub)
        
#         # Calculate time for each problem
#         for problem_id, problem_subs in problem_submissions.items():
#             problem_key = str(problem_id)
#             submission_info[problem_key] = {
#                 'ac_time': 0,
#                 'error_number': 0,
#                 'is_ac': False,
#                 'is_first_ac': False
#             }
            
#             ac_found = False
#             wrong_attempts = 0
            
#             for sub in problem_subs:
#                 if sub.result == 0 and not ac_found:  # First AC
#                     ac_found = True
#                     accepted_problems.add(problem_id)
                    
#                     # Calculate time from contest start
#                     time_diff = sub.create_time - contest.start_time
#                     problem_time = int(time_diff.total_seconds())
                    
#                     # Add penalty for wrong attempts (20 minutes each)
#                     wrong_penalty = wrong_attempts * 20 * 60
#                     final_problem_time = problem_time + wrong_penalty
                    
#                     submission_info[problem_key] = {
#                         'ac_time': final_problem_time,
#                         'error_number': wrong_attempts,
#                         'is_ac': True,
#                         'is_first_ac': True
#                     }
                    
#                     base_total_time += final_problem_time
#                     break
#                 elif sub.result != 0:  # Wrong submission
#                     wrong_attempts += 1
            
#             if not ac_found:
#                 submission_info[problem_key]['error_number'] = wrong_attempts
        
#         # Calculate anti-cheat penalty
#         anti_cheat_penalty = violation_count * 600  # 10 minutes per violation
        
#         # FIXED: Distribute anti-cheat penalty to individual problems
#         final_total_time = base_total_time
        
#         if accepted_problems and anti_cheat_penalty > 0:
#             # Distribute penalty equally among accepted problems
#             penalty_per_problem = anti_cheat_penalty // len(accepted_problems)
#             remaining_penalty = anti_cheat_penalty % len(accepted_problems)
            
#             # Apply penalty to each accepted problem's ac_time
#             for i, problem_id in enumerate(accepted_problems):
#                 problem_key = str(problem_id)
#                 if problem_key in submission_info and submission_info[problem_key]['is_ac']:
#                     original_ac_time = submission_info[problem_key]['ac_time']
                    
#                     # Add base penalty + extra penalty for first problem (remainder)
#                     additional_penalty = penalty_per_problem
#                     if i == 0:  # Give remainder to first problem
#                         additional_penalty += remaining_penalty
                    
#                     # Update the ac_time with penalty
#                     submission_info[problem_key]['ac_time'] = original_ac_time + additional_penalty
                    
#                     print(f"Problem {problem_id}: original_time={original_ac_time}s, "
#                           f"penalty={additional_penalty}s, final_time={original_ac_time + additional_penalty}s")
            
#             # Recalculate total time from updated problem times
#             final_total_time = sum(
#                 info['ac_time'] for info in submission_info.values() 
#                 if info.get('is_ac', False)
#             )
        
#         print(f"Calculated metrics: AC={len(accepted_problems)}, "
#               f"Base Time={base_total_time}s, "
#               f"Anti-cheat Penalty={anti_cheat_penalty}s, Final Total={final_total_time}s")
        
#         # Update or create ranking - SAVE THE FINAL TOTAL TIME WITH INDIVIDUAL PROBLEM PENALTIES
#         with transaction.atomic():
#             rank, created = ACMContestRank.objects.update_or_create(
#                 contest=contest,
#                 user=user,
#                 defaults={
#                     'submission_number': submission_count,
#                     'accepted_number': len(accepted_problems),
#                     'total_time': final_total_time,  # Total time = sum of individual problem times (with penalties)
#                     'submission_info': submission_info  # Each problem's ac_time includes its penalty share
#                 }
#             )
            
#             print(f"{'Created' if created else 'Updated'} ACM rank for {user.username}")
#             print(f"Saved total_time to database: {final_total_time}s")
#             return rank
            
#     except Exception as e:
#         print(f"Error recalculating ACM ranking for user {user.username}: {e}")
#         import traceback
#         traceback.print_exc()
#         return None

# def recalculate_oi_ranking_with_penalties(user, contest):
#     """
#     Recalculate OI ranking including violation penalties
#     """
#     try:
#         print(f"Recalculating OI ranking for user {user.username} in contest {contest.id}")
        
#         # Get violation count
#         violation_count = AntiCheatViolation.objects.filter(
#             contest=contest,
#             user=user
#         ).count()
        
#         # Calculate OI score from best submissions
#         problems = contest.problem_set.all()
#         total_score = 0
#         submission_info = {}
#         submission_count = 0
        
#         for problem in problems:
#             # Get best submission for this problem
#             best_submission = Submission.objects.filter(
#                 contest=contest,
#                 user_id=user.id,
#                 problem=problem,
#                 create_time__gte=contest.start_time
#             ).order_by('-statistic_info__score', 'create_time').first()
            
#             if best_submission:
#                 submission_count += 1
#                 # Get score from statistic_info
#                 problem_score = best_submission.statistic_info.get('score', 0) if best_submission.statistic_info else 0
#                 total_score += problem_score
                
#                 submission_info[str(problem.id)] = {
#                     'score': problem_score,
#                     'ac_time': int((best_submission.create_time - contest.start_time).total_seconds()),
#                     'is_ac': best_submission.result == 0
#                 }
        
#         # Apply anti-cheat penalty
#         anti_cheat_penalty = violation_count * 10  # 10 points per violation
#         final_score = max(0, total_score - anti_cheat_penalty)
        
#         print(f"Calculated OI metrics: Base Score={total_score}, "
#               f"Penalty={anti_cheat_penalty}, Final={final_score}")
        
#         # Update or create ranking
#         with transaction.atomic():
#             rank, created = OIContestRank.objects.update_or_create(
#                 contest=contest,
#                 user=user,
#                 defaults={
#                     'submission_number': submission_count,
#                     'total_score': final_score,
#                     'submission_info': submission_info
#                 }
#             )
            
#             print(f"{'Created' if created else 'Updated'} OI rank for {user.username}")
#             return rank
            
#     except Exception as e:
#         print(f"Error recalculating OI ranking for user {user.username}: {e}")
#         import traceback
#         traceback.print_exc()
#         return None


# @receiver(post_save, sender=Submission)
# def update_ranking_on_submission(sender, instance, created, **kwargs):
#     """
#     Update ranking when a submission is made
#     """
#     # Skip if not a contest submission
#     if not instance.contest:
#         return
    
#     # Skip if anti-cheat is not available
#     if not ANTI_CHEAT_AVAILABLE:
#         return
    
#     try:
#         from account.models import User
#         user = User.objects.get(id=instance.user_id)
#         contest = instance.contest
        
#         print(f"Updating ranking for user {user.username} after submission {instance.id}")
        
#         # Clear cache
#         clear_contest_rank_cache(contest.id)
        
#         # Recalculate ranking based on contest type
#         if contest.rule_type == ContestRuleType.ACM:
#             recalculate_acm_ranking_with_penalties(user, contest)
#         else:  # OI
#             recalculate_oi_ranking_with_penalties(user, contest)
        
#         print(f"Successfully updated ranking for user {user.username}")
        
#     except Exception as e:
#         print(f"Error updating ranking on submission: {e}")
#         import traceback
#         traceback.print_exc()


# if ANTI_CHEAT_AVAILABLE:
#     @receiver(post_save, sender=AntiCheatViolation)
#     def update_ranking_on_violation(sender, instance, created, **kwargs):
#         """
#         Update ranking when a new violation is created
#         """
#         if not created:
#             return
        
#         try:
#             contest = instance.contest
#             user = instance.user
            
#             print(f"New violation '{instance.violation_type}' created for user {user.username} "
#                   f"in contest {contest.id}")
            
#             if instance.problem:
#                 print(f"Violation occurred on problem {instance.problem.id}: {instance.problem.title}")
            
#             # Clear cache
#             clear_contest_rank_cache(contest.id)
            
#             # Recalculate ranking based on contest type
#             if contest.rule_type == ContestRuleType.ACM:
#                 recalculate_acm_ranking_with_penalties(user, contest)
#             else:  # OI
#                 recalculate_oi_ranking_with_penalties(user, contest)
            
#             # Get updated violation count for logging
#             total_violations = AntiCheatViolation.objects.filter(
#                 contest=contest,
#                 user=user
#             ).count()
            
#             print(f"Updated ranking for user {user.username} after violation "
#                   f"(total violations: {total_violations})")
            
#         except Exception as e:
#             print(f"Error updating ranking on violation: {e}")
#             import traceback
#             traceback.print_exc()


# def get_user_anti_cheat_penalty(user, contest):
#     """
#     Helper function to get total penalty for a user in a contest
#     """
#     try:
#         violation_count = AntiCheatViolation.objects.filter(
#             contest=contest,
#             user=user
#         ).count()
        
#         if contest.rule_type == ContestRuleType.ACM:
#             return violation_count * 10 * 60  # 10 minutes per violation in seconds
#         else:  # OI
#             return violation_count * 10  # 10 points per violation
#     except:
#         return 0


# def get_user_violation_count(user, contest, problem=None):
#     """
#     Helper function to get violation count for a user in a contest
#     Optionally filter by problem
#     """
#     try:
#         violations = AntiCheatViolation.objects.filter(
#             contest=contest,
#             user=user
#         )
        
#         if problem:
#             violations = violations.filter(problem=problem)
        
#         return violations.count()
#     except:
#         return 0
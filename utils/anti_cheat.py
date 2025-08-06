# # utils/anti_cheat_utils.py
# from django.db import models, transaction
# from django.utils.timezone import now

# def apply_anti_cheat_penalty_to_user(user, contest, force_recalculate=False):
#     """
#     Apply anti-cheat penalties to a user's ranking in a contest.
#     This function ensures penalties are correctly applied to the database.
#     """
#     try:
#         from contest.models import AntiCheatViolation, ACMContestRank, OIContestRank
#         from utils.constants import ContestRuleType
        
#         # Get violation count
#         violation_count = AntiCheatViolation.objects.filter(
#             contest=contest,
#             user=user
#         ).count()
        
#         if violation_count == 0 and not force_recalculate:
#             return {'status': 'no_violations', 'penalty': 0}
        
#         penalty_applied = False
        
#         if contest.rule_type == ContestRuleType.ACM:
#             # For ACM contests, add penalty time
#             penalty_seconds = violation_count * 600  # 10 minutes per violation
            
#             try:
#                 with transaction.atomic():
#                     rank = ACMContestRank.objects.select_for_update().get(
#                         contest=contest,
#                         user=user
#                     )
                    
#                     # Store original time for comparison
#                     original_time = rank.total_time
                    
#                     # Calculate what the time should be with penalty
#                     # We need to be careful not to double-apply penalties
#                     # One approach: store penalty info in a separate field or use a marker
                    
#                     # For now, let's recalculate from submissions and add penalty
#                     from submission.models import Submission
                    
#                     # Get all accepted submissions by this user in this contest
#                     accepted_submissions = Submission.objects.filter(
#                         contest=contest,
#                         user_id=user.id,
#                         result=0  # Accepted
#                     ).order_by('create_time')
                    
#                     # Recalculate base time from submissions
#                     base_time = 0
#                     for submission in accepted_submissions:
#                         # Calculate time in seconds from contest start
#                         time_diff = submission.create_time - contest.start_time
#                         base_time += time_diff.total_seconds()
                    
#                     # Add penalty time
#                     total_time_with_penalty = base_time + penalty_seconds
                    
#                     # Update the rank
#                     rank.total_time = int(total_time_with_penalty)
#                     rank.save()
                    
#                     penalty_applied = True
                    
#                     print(f"Applied ACM penalty: User {user.username}, "
#                           f"Original: {original_time}s, New: {rank.total_time}s, "
#                           f"Penalty: {penalty_seconds}s, Violations: {violation_count}")
                    
#                     return {
#                         'status': 'penalty_applied',
#                         'penalty_seconds': penalty_seconds,
#                         'violation_count': violation_count,
#                         'original_time': original_time,
#                         'new_time': rank.total_time
#                     }
                    
#             except ACMContestRank.DoesNotExist:
#                 print(f"No ACM ranking found for user {user.username} in contest {contest.id}")
#                 return {'status': 'no_ranking', 'penalty': penalty_seconds}
                
#         elif contest.rule_type == ContestRuleType.OI:
#             # For OI contests, deduct penalty points
#             penalty_points = violation_count * 10  # 10 points per violation
            
#             try:
#                 with transaction.atomic():
#                     rank = OIContestRank.objects.select_for_update().get(
#                         contest=contest,
#                         user=user
#                     )
                    
#                     # Store original score
#                     original_score = rank.total_score
                    
#                     # Apply penalty (but don't go below 0)
#                     rank.total_score = max(0, rank.total_score - penalty_points)
#                     rank.save()
                    
#                     penalty_applied = True
                    
#                     print(f"Applied OI penalty: User {user.username}, "
#                           f"Original: {original_score}, New: {rank.total_score}, "
#                           f"Penalty: {penalty_points} points, Violations: {violation_count}")
                    
#                     return {
#                         'status': 'penalty_applied',
#                         'penalty_points': penalty_points,
#                         'violation_count': violation_count,
#                         'original_score': original_score,
#                         'new_score': rank.total_score
#                     }
                    
#             except OIContestRank.DoesNotExist:
#                 print(f"No OI ranking found for user {user.username} in contest {contest.id}")
#                 return {'status': 'no_ranking', 'penalty': penalty_points}
                
#     except Exception as e:
#         print(f"Error applying anti-cheat penalty: {e}")
#         import traceback
#         traceback.print_exc()
#         return {'status': 'error', 'error': str(e)}
    
#     return {'status': 'no_action'}


# def ensure_all_penalties_applied(contest):
#     """
#     Ensure all anti-cheat penalties are applied for all users in a contest.
#     This should be called when displaying rankings.
#     """
#     try:
#         from contest.models import AntiCheatViolation
#         from account.models import AdminType
        
#         # Get all users who have violations in this contest
#         users_with_violations = AntiCheatViolation.objects.filter(
#             contest=contest
#         ).values_list('user_id', flat=True).distinct()
        
#         results = []
#         for user_id in users_with_violations:
#             try:
#                 from account.models import User
#                 user = User.objects.get(
#                     id=user_id,
#                     admin_type=AdminType.REGULAR_USER,
#                     is_disabled=False
#                 )
#                 result = apply_anti_cheat_penalty_to_user(user, contest, force_recalculate=True)
#                 results.append({'user': user.username, 'result': result})
#             except User.DoesNotExist:
#                 continue
                
#         return results
        
#     except Exception as e:
#         print(f"Error ensuring penalties applied: {e}")
#         import traceback
#         traceback.print_exc()
#         return []


# def get_user_anti_cheat_penalty(user, contest):
#     """
#     Helper function to get total penalty time for a user in a contest
#     """
#     try:
#         from contest.models import AntiCheatViolation
#         from utils.constants import ContestRuleType
        
#         violation_count = AntiCheatViolation.objects.filter(
#             contest=contest,
#             user=user
#         ).count()
        
#         if contest.rule_type == ContestRuleType.ACM:
#             return violation_count * 10 * 60  # 10 minutes per violation in seconds
#         else:  # OI
#             return violation_count * 10  # 10 points per violation
#     except Exception as e:
#         print(f"Error calculating penalty: {e}")
#         return 0


# def recalculate_contest_rankings_with_penalties(contest):
#     """
#     Recalculate all rankings for a contest, applying anti-cheat penalties.
#     This is a comprehensive function that rebuilds rankings from scratch.
#     """
#     try:
#         from contest.models import ACMContestRank, OIContestRank, AntiCheatViolation
#         from submission.models import Submission
#         from account.models import User, AdminType
#         from utils.constants import ContestRuleType
#         from django.db.models import Q
#         from collections import defaultdict
        
#         print(f"Recalculating rankings for contest {contest.id} with anti-cheat penalties")
        
#         # Get all users who have participated in this contest
#         participant_ids = Submission.objects.filter(
#             contest=contest
#         ).values_list('user_id', flat=True).distinct()
        
#         participants = User.objects.filter(
#             id__in=participant_ids,
#             admin_type=AdminType.REGULAR_USER,
#             is_disabled=False
#         )
        
#         print(f"Found {participants.count()} participants")
        
#         if contest.rule_type == ContestRuleType.ACM:
#             # Recalculate ACM rankings
#             for user in participants:
#                 # Get all submissions by this user in this contest
#                 submissions = Submission.objects.filter(
#                     contest=contest,
#                     user_id=user.id
#                 ).order_by('create_time')
                
#                 # Calculate ACM metrics
#                 accepted_problems = set()
#                 total_time = 0
#                 submission_count = submissions.count()
#                 submission_info = {}
                
#                 for submission in submissions:
#                     problem_id = str(submission.problem_id)
                    
#                     if problem_id not in submission_info:
#                         submission_info[problem_id] = {
#                             'ac_time': 0,
#                             'error_number': 0,
#                             'is_ac': False
#                         }
                    
#                     if submission.result == 0:  # Accepted
#                         if problem_id not in accepted_problems:
#                             accepted_problems.add(problem_id)
#                             # Calculate time from contest start
#                             time_diff = submission.create_time - contest.start_time
#                             problem_time = int(time_diff.total_seconds())
                            
#                             # Add penalty for wrong submissions (20 minutes each)
#                             penalty_for_wrong = submission_info[problem_id]['error_number'] * 20 * 60
                            
#                             submission_info[problem_id]['ac_time'] = problem_time + penalty_for_wrong
#                             submission_info[problem_id]['is_ac'] = True
                            
#                             total_time += problem_time + penalty_for_wrong
#                     else:
#                         # Wrong submission
#                         if not submission_info[problem_id]['is_ac']:
#                             submission_info[problem_id]['error_number'] += 1
                
#                 # Get anti-cheat violations and add penalty
#                 violation_count = AntiCheatViolation.objects.filter(
#                     contest=contest,
#                     user=user
#                 ).count()
                
#                 anti_cheat_penalty = violation_count * 600  # 10 minutes per violation
#                 total_time += anti_cheat_penalty
                
#                 # Update or create ranking
#                 rank, created = ACMContestRank.objects.update_or_create(
#                     contest=contest,
#                     user=user,
#                     defaults={
#                         'submission_number': submission_count,
#                         'accepted_number': len(accepted_problems),
#                         'total_time': total_time,
#                         'submission_info': submission_info
#                     }
#                 )
                
#                 print(f"Updated ACM rank for {user.username}: "
#                       f"AC={len(accepted_problems)}, Time={total_time}s, "
#                       f"AntiCheatPenalty={anti_cheat_penalty}s, Violations={violation_count}")
                
#         else:  # OI Contest
#             # Recalculate OI rankings
#             for user in participants:
#                 # Get best submission for each problem
#                 problems = contest.problem_set.all()
#                 total_score = 0
#                 submission_info = {}
                
#                 for problem in problems:
#                     best_submission = Submission.objects.filter(
#                         contest=contest,
#                         user_id=user.id,
#                         problem=problem
#                     ).order_by('-score', 'create_time').first()
                    
#                     if best_submission:
#                         problem_score = best_submission.score or 0
#                         total_score += problem_score
                        
#                         submission_info[str(problem.id)] = {
#                             'score': problem_score,
#                             'ac_time': int((best_submission.create_time - contest.start_time).total_seconds()),
#                             'is_ac': best_submission.result == 0
#                         }
                
#                 # Apply anti-cheat penalty
#                 violation_count = AntiCheatViolation.objects.filter(
#                     contest=contest,
#                     user=user
#                 ).count()
                
#                 anti_cheat_penalty = violation_count * 10  # 10 points per violation
#                 total_score = max(0, total_score - anti_cheat_penalty)
                
#                 # Update or create ranking
#                 rank, created = OIContestRank.objects.update_or_create(
#                     contest=contest,
#                     user=user,
#                     defaults={
#                         'total_score': total_score,
#                         'submission_info': submission_info
#                     }
#                 )
                
#                 print(f"Updated OI rank for {user.username}: "
#                       f"Score={total_score}, AntiCheatPenalty={anti_cheat_penalty}, "
#                       f"Violations={violation_count}")
        
#         print(f"Ranking recalculation complete for contest {contest.id}")
#         return {'status': 'success', 'participants': participants.count()}
        
#     except Exception as e:
#         print(f"Error recalculating rankings: {e}")
#         import traceback
#         traceback.print_exc()
#         return {'status': 'error', 'error': str(e)}
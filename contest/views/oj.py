import io

import xlsxwriter
from utils.api import APIView, validate_serializer
import ipaddress
from django.http import HttpResponse
from django.utils.timezone import now
from django.core.cache import cache
from django.db.models import Count, Q
from django.db import models

from problem.models import Problem
from utils.api import APIView, validate_serializer
from utils.constants import CacheKey, CONTEST_PASSWORD_SESSION_KEY
from utils.shortcuts import datetime2str, check_is_id
from account.models import AdminType
from account.decorators import login_required, check_contest_permission, check_contest_password

from utils.constants import ContestRuleType, ContestStatus
from ..models import ContestAnnouncement, Contest, OIContestRank, ACMContestRank, AntiCheatViolation, ContestReview
from submission.models import Submission
from ..serializers import ContestAnnouncementSerializer
from ..serializers import ContestSerializer, ContestPasswordVerifySerializer
from ..serializers import OIContestRankSerializer, ACMContestRankSerializer
from ..serializers import ContestReviewSerializer, CreateContestReviewSerializer


class ContestAnnouncementListAPI(APIView):
    @check_contest_permission(check_type="announcements")
    def get(self, request):
        contest_id = request.GET.get("contest_id")
        if not contest_id:
            return self.error("Invalid parameter, contest_id is required")
        data = ContestAnnouncement.objects.select_related("created_by").filter(contest_id=contest_id, visible=True)
        max_id = request.GET.get("max_id")
        if max_id:
            data = data.filter(id__gt=max_id)
        return self.success(ContestAnnouncementSerializer(data, many=True).data)


class ContestAPI(APIView):
    def get(self, request):
        id = request.GET.get("id")
        if not id or not check_is_id(id):
            return self.error("Invalid parameter, id is required")
        try:
            contest = Contest.objects.get(id=id, visible=True)
        except Contest.DoesNotExist:
            return self.error("Contest does not exist")
        data = ContestSerializer(contest).data
        data["now"] = datetime2str(now())
        return self.success(data)


class ContestListAPI(APIView):
    def get(self, request):
        contests = Contest.objects.select_related("created_by").filter(visible=True)
        keyword = request.GET.get("keyword")
        rule_type = request.GET.get("rule_type")
        status = request.GET.get("status")
        if keyword:
            contests = contests.filter(title__contains=keyword)
        if rule_type:
            contests = contests.filter(rule_type=rule_type)
        if status:
            cur = now()
            if status == ContestStatus.CONTEST_NOT_START:
                contests = contests.filter(start_time__gt=cur)
            elif status == ContestStatus.CONTEST_ENDED:
                contests = contests.filter(end_time__lt=cur)
            else:
                contests = contests.filter(start_time__lte=cur, end_time__gte=cur)
        return self.success(self.paginate_data(request, contests, ContestSerializer))


class ContestPasswordVerifyAPI(APIView):
    @validate_serializer(ContestPasswordVerifySerializer)
    @login_required
    def post(self, request):
        data = request.data
        try:
            contest = Contest.objects.get(id=data["contest_id"], visible=True, password__isnull=False)
        except Contest.DoesNotExist:
            return self.error("Contest does not exist")
        if not check_contest_password(data["password"], contest.password):
            return self.error("Wrong password or password expired")

        # password verify OK.
        if CONTEST_PASSWORD_SESSION_KEY not in request.session:
            request.session[CONTEST_PASSWORD_SESSION_KEY] = {}
        request.session[CONTEST_PASSWORD_SESSION_KEY][contest.id] = data["password"]
        # https://docs.djangoproject.com/en/dev/topics/http/sessions/#when-sessions-are-saved
        request.session.modified = True
        return self.success(True)


class ContestAccessAPI(APIView):
    @login_required
    def get(self, request):
        contest_id = request.GET.get("contest_id")
        if not contest_id:
            return self.error()
        try:
            contest = Contest.objects.get(id=contest_id, visible=True, password__isnull=False)
        except Contest.DoesNotExist:
            return self.error("Contest does not exist")
        session_pass = request.session.get(CONTEST_PASSWORD_SESSION_KEY, {}).get(contest.id)
        return self.success({"access": check_contest_password(session_pass, contest.password)})


class ContestRankAPI(APIView):
    def get_rank(self):
        import traceback
        import logging
        import json
        from collections import defaultdict # Import defaultdict
        
        logger = logging.getLogger('contest')
        
        try:
            logger.info(f"Getting rank for contest {self.contest.id}, rule type: {self.contest.rule_type}")
            
            if self.contest.rule_type == ContestRuleType.ACM:
                logger.info("Processing ACM contest")
                
                ranks = ACMContestRank.objects.filter(
                    contest=self.contest,
                    user__admin_type=AdminType.REGULAR_USER,
                    user__is_disabled=False
                ).select_related("user")
                
                if not ranks.exists():
                    return []
                
                penalty_data = []
                # Check contest status once before the loop
                is_contest_ended = self.contest.status == ContestStatus.CONTEST_ENDED

                for rank in ranks:
                    try:
                        logger.debug(f"Processing penalties for user {rank.user.username}")

                        # --- BUG FIX STARTS HERE --- (Existing code)
                        violations_by_problem = defaultdict(int)
                        user_violations = AntiCheatViolation.objects.filter(
                            contest=self.contest,
                            user=rank.user,
                            problem__isnull=False
                        )

                        for v in user_violations:
                            violations_by_problem[str(v.problem_id)] += 1
                        
                        logger.debug(f"User {rank.user.username} violation counts: {dict(violations_by_problem)}")
                        # --- BUG FIX ENDS HERE ---

                        modified_submission_info = json.loads(json.dumps(rank.submission_info))
                        total_time_adjustment = 0
                        
                        for problem_id_str, violation_count in violations_by_problem.items():
                            if problem_id_str in modified_submission_info and modified_submission_info[problem_id_str].get('is_ac', False):
                                problem_penalty_seconds = violation_count * 600
                                
                                original_ac_time = modified_submission_info[problem_id_str]['ac_time']
                                new_ac_time = original_ac_time + problem_penalty_seconds
                                
                                modified_submission_info[problem_id_str]['ac_time'] = new_ac_time
                                modified_submission_info[problem_id_str]['penalty_applied'] = problem_penalty_seconds
                                modified_submission_info[problem_id_str]['violation_count'] = violation_count
                                modified_submission_info[problem_id_str]['original_ac_time'] = original_ac_time
                                
                                total_time_adjustment += problem_penalty_seconds
                                logger.debug(f"Applied penalty to problem {problem_id_str}: {problem_penalty_seconds}s for {violation_count} violations.")
                        
                        # --- NEW: PENALTY FOR NO REVIEW ---
                        review_penalty_seconds = 0
                        # Only apply the penalty if the contest has officially ended.
                        if is_contest_ended:
                            review_exists = ContestReview.objects.filter(contest=self.contest, user=rank.user).exists()
                            if not review_exists:
                                review_penalty_seconds = 3600  # 60 minutes * 60 seconds
                                total_time_adjustment += review_penalty_seconds
                                logger.info(f"User {rank.user.username} has no review, applying {review_penalty_seconds}s penalty.")
                        
                        # Add penalty info to the rank object for the serializer
                        rank.review_penalty_applied = review_penalty_seconds
                        # --- END NEW LOGIC ---

                        # Apply the calculated penalties to the user's rank object
                        rank.submission_info = modified_submission_info
                        rank.total_penalty_time = total_time_adjustment # Now includes both anti-cheat and review penalties
                        rank.total_violation_count = sum(violations_by_problem.values())
                        
                        rank.original_total_time = rank.total_time
                        rank.total_time += total_time_adjustment
                        rank.total_time_with_penalty = rank.total_time
                        
                        penalty_data.append(rank)
                        
                    except Exception as e:
                        logger.error(f"Error processing penalties for user {rank.user.username}: {str(e)}")
                        rank.total_penalty_time = 0
                        rank.total_violation_count = 0
                        penalty_data.append(rank)
                
                penalty_data.sort(key=lambda x: (-x.accepted_number, x.total_time))
                return penalty_data
                
            else: # OI Contest
                # Note: A time-based penalty is not applicable to OI contests as they are score-based.
                # A score deduction would be a more suitable penalty for this rule type.
                ranks = OIContestRank.objects.filter(
                    contest=self.contest,
                    user__admin_type=AdminType.REGULAR_USER,
                    user__is_disabled=False
                ).select_related("user").order_by('-total_score')
                return list(ranks)
                
        except Exception as e:
            logger.error(f"Exception in get_rank: {str(e)}")
            traceback.print_exc()
            return []

    def column_string(self, n):
        string = ""
        while n > 0:
            n, remainder = divmod(n - 1, 26)
            string = chr(65 + remainder) + string
        return string

    @check_contest_permission(check_type="ranks")
    def get(self, request):
        import traceback
        import logging
        
        logger = logging.getLogger('contest')
        
        try:
            logger.info(f"ContestRankAPI.get called for contest {self.contest.id}")
            
            download_csv = request.GET.get("download_csv")
            force_refresh = request.GET.get("force_refresh")
            is_contest_admin = request.user.is_authenticated and request.user.is_contest_admin(self.contest)
            
            logger.info(f"download_csv={download_csv}, force_refresh={force_refresh}, is_contest_admin={is_contest_admin}")
            logger.info(f"Contest rule type: {self.contest.rule_type}")
            
            if self.contest.rule_type == ContestRuleType.OI:
                serializer = OIContestRankSerializer
                logger.info("Using OI serializer")
            else:
                serializer = ACMContestRankSerializer
                logger.info("Using ACM serializer")

            # Check if there are violations
            logger.info("Checking for violations...")
            has_violations = AntiCheatViolation.objects.filter(contest=self.contest).exists()
            logger.info(f"Has violations: {has_violations}")
            
            # Get ranking data
            if force_refresh == "1" and is_contest_admin:
                logger.info("Force refresh requested by admin")
                qs = self.get_rank()
            elif has_violations:
                logger.info("Has violations, calculating fresh data")
                qs = self.get_rank()
            else:
                logger.info("Checking cache...")
                cache_key = f"{CacheKey.contest_rank_cache}:{self.contest.id}"
                qs = cache.get(cache_key)
                if not qs:
                    logger.info("Cache miss, calculating fresh data")
                    qs = self.get_rank()
                    # Only cache when there are no violations
                    if not has_violations:
                        logger.info("Caching results for 60 seconds")
                        cache.set(cache_key, qs, 60)
                else:
                    logger.info("Cache hit")

            logger.info(f"Got {len(qs) if qs else 0} ranking entries")

            # Handle empty rankings
            if not qs:
                logger.info("No ranking data available, returning empty results")
                return self.success({
                    "total": 0,
                    "results": []
                })

            if download_csv:
                logger.info("CSV download requested")
                # Skip CSV for now to focus on the main issue
                return self.error("CSV download temporarily disabled during debugging")
            
            logger.info("Paginating data...")
            try:
                page_qs = self.paginate_data(request, qs)
                logger.info(f"Paginated to {len(page_qs['results']) if page_qs and 'results' in page_qs else 0} entries")
            except Exception as e:
                logger.error(f"Pagination error: {str(e)}")
                # Return unpaginated data if pagination fails
                page_qs = {
                    "total": len(qs),
                    "results": qs
                }
            
            logger.info("Serializing data...")
            try:
                serialized_data = serializer(page_qs["results"], many=True, is_contest_admin=is_contest_admin).data
                page_qs["results"] = serialized_data
                logger.info(f"Serialization complete, returning {len(serialized_data)} entries")
            except Exception as e:
                logger.error(f"Serialization error: {str(e)}")
                traceback.print_exc()
                return self.error(f"Serialization error: {str(e)}")
            
            return self.success(page_qs)
            
        except Exception as e:
            logger.error(f"Exception in ContestRankAPI.get: {str(e)}")
            traceback.print_exc()
            return self.error(f"Internal server error: {str(e)}")

class AntiCheatViolationAPI(APIView):
    @login_required
    def post(self, request):
        """
        Report an anti-cheat violation
        """
        import logging
        import traceback
        
        logger = logging.getLogger('django')
        logger.info(f"AntiCheatViolationAPI POST called by user {request.user.id}")
        logger.info(f"Request data: {request.data}")
        
        try:
            data = request.data
            contest_id = data.get('contest_id')
            violation_type = data.get('violation_type', '').strip()
            violation_details = data.get('violation_details', '').strip()
            problem_id = data.get('problem_id')  # This is display_id from frontend
            
            logger.info(f"Parsed data - contest_id: {contest_id}, violation_type: {violation_type}, problem_id: {problem_id}")
            
            # Validate required fields
            if not contest_id:
                logger.error("Missing contest_id")
                return self.error("Contest ID is required")
            
            if not violation_type:
                logger.error("Missing violation_type")
                return self.error("Violation type is required")
            
            # Validate contest exists
            try:
                contest = Contest.objects.get(id=contest_id, visible=True)
                logger.info(f"Found contest: {contest.title}")
            except Contest.DoesNotExist:
                logger.error(f"Contest {contest_id} not found")
                return self.error("Contest not found")
            except ValueError:
                logger.error(f"Invalid contest_id format: {contest_id}")
                return self.error("Invalid contest ID format")
            
            # Validate problem if specified
            problem = None
            if problem_id:
                try:
                    from problem.models import Problem
                    
                    # FIXED: Use _id field (display_id) instead of id field
                    problem = Problem.objects.get(
                        _id=problem_id,  # Use display ID (_id field)
                        visible=True,
                        contest=contest  # Check if problem belongs to this contest
                    )
                        
                    logger.info(f"Found problem: {problem.title} (display_id: {problem._id}, db_id: {problem.id})")
                except Problem.DoesNotExist:
                    logger.error(f"Problem with display ID '{problem_id}' not found in contest {contest_id}")
                    return self.error("Problem not found in this contest")
                except ValueError:
                    logger.error(f"Invalid problem_id format: {problem_id}")
                    return self.error("Invalid problem ID format")
            
            # Validate violation type
            valid_violation_types = [choice[0] for choice in AntiCheatViolation.VIOLATION_TYPES]
            if violation_type not in valid_violation_types:
                logger.warning(f"Invalid violation_type: {violation_type}, using 'window_resize'")
                violation_type = 'window_resize'
            
            # Check for recent duplicate violations (prevent spam)
            from django.utils.timezone import now, timedelta
            recent_threshold = now() - timedelta(seconds=15)
            recent_violation = AntiCheatViolation.objects.filter(
                contest=contest,
                user=request.user,
                problem=problem,
                violation_type=violation_type,
                violation_details=violation_details,
                timestamp__gte=recent_threshold
            ).first()
            
            if recent_violation:
                logger.info(f"Recent duplicate violation found, skipping creation")
                problem_violations = AntiCheatViolation.objects.filter(
                    contest=contest,
                    user=request.user,
                    problem=problem
                ).count() if problem else 0
                
                return self.success({
                    'violation_id': recent_violation.id,
                    'problem_violation_count': problem_violations,
                    'problem_penalty_minutes': problem_violations * 10,
                    'message': f'Duplicate violation ignored. Problem penalty: {problem_violations * 10} minutes'
                })
            
            # Create violation record
            violation = AntiCheatViolation.objects.create(
                contest=contest,
                problem=problem,
                user=request.user,
                violation_type=violation_type,
                violation_details=violation_details,
                ip_address=request.session.get("ip", ""),
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:500]
            )
            
            logger.info(f"Created violation {violation.id}")
            
            # Get problem-specific violations count
            problem_violations = AntiCheatViolation.objects.filter(
                contest=contest,
                user=request.user,
                problem=problem
            ).count() if problem else 0
            
            problem_penalty_minutes = problem_violations * 10
            
            logger.info(f"User {request.user.username} now has {problem_violations} violations for problem {problem_id}, penalty: {problem_penalty_minutes} minutes")
            
            return self.success({
                'violation_id': violation.id,
                'problem_violation_count': problem_violations,
                'problem_penalty_minutes': problem_penalty_minutes,
                'message': f'Violation recorded. Problem penalty: {problem_penalty_minutes} minutes'
            })
            
        except Exception as e:
            logger.error(f"Unexpected error in AntiCheatViolationAPI: {str(e)}")
            logger.error(traceback.format_exc())
            return self.error(f"Internal server error: {str(e)}")

class AntiCheatViolationListAPI(APIView):
    @login_required
    def get(self, request):
        """
        Get anti-cheat violations for a contest
        """
        contest_id = request.GET.get('contest_id')
        user_id = request.GET.get('user_id')
        
        if not contest_id:
            return self.error("Contest ID is required")
        
        try:
            contest = Contest.objects.get(id=contest_id, visible=True)
        except Contest.DoesNotExist:
            return self.error("Contest not found")
        
        # Only allow admins to see other users' violations
        if user_id and user_id != str(request.user.id):
            if not request.user.is_contest_admin(contest):
                return self.error("Permission denied")
        
        violations = AntiCheatViolation.objects.filter(contest=contest)
        
        if user_id:
            violations = violations.filter(user_id=user_id)
        else:
            # If no user_id specified, show current user's violations
            violations = violations.filter(user=request.user)
        
        violations_data = []
        for violation in violations:
            violations_data.append({
                'id': violation.id,
                'violation_type': violation.violation_type,
                'violation_details': violation.violation_details,
                'timestamp': violation.timestamp,
                'problem_id': violation.problem.id if violation.problem else None,
                'problem_title': violation.problem.title if violation.problem else None
            })
        
        return self.success({
            'violations': violations_data,
            'total_count': len(violations_data),
            'penalty_minutes': len(violations_data) * 10
        })


class AntiCheatStatusAPI(APIView):
    @login_required
    def get(self, request):
        """
        Get anti-cheat status for current user in a contest
        """
        contest_id = request.GET.get('contest_id')
        
        if not contest_id:
            return self.error("Contest ID is required")
        
        try:
            contest = Contest.objects.get(id=contest_id, visible=True)
        except Contest.DoesNotExist:
            return self.error("Contest not found")
        
        # Get violation count
        violation_count = AntiCheatViolation.objects.filter(
            contest=contest,
            user=request.user
        ).count()
        
        penalty_minutes = violation_count * 10
        
        return self.success({
            'violation_count': violation_count,
            'penalty_minutes': penalty_minutes,
            'has_violations': violation_count > 0
        })


class ProblemAntiCheatStatusAPI(APIView):
    @login_required
    def get(self, request):
        """
        Check anti-cheat status for a specific problem in a contest
        """
        contest_id = request.GET.get('contest_id')
        problem_id = request.GET.get('problem_id')  # This is display_id from frontend
        
        if not contest_id or not problem_id:
            return self.error("Contest ID and Problem ID are required")
        
        try:
            contest = Contest.objects.get(id=contest_id, visible=True)
            from problem.models import Problem
            
            # FIXED: Use _id field (display_id) instead of id field
            problem = Problem.objects.get(
                _id=problem_id,  # Use display ID (_id field)
                visible=True,
                contest=contest  # Check if problem belongs to this contest
            )
                
        except Contest.DoesNotExist:
            return self.error("Contest not found")
        except Problem.DoesNotExist:
            return self.error("Problem not found in this contest")
        
        # Get violations for this specific problem only
        problem_violations = AntiCheatViolation.objects.filter(
            contest=contest,
            user=request.user,
            problem=problem  # Use the actual problem object
        ).count()
        
        # Check if user has any accepted submission for this problem
        from submission.models import Submission
        has_accepted = Submission.objects.filter(
            contest=contest,
            problem=problem,  # Use the actual problem object
            user_id=request.user.id,
            result=0  # Accepted
        ).exists()
        
        # Calculate penalties ONLY for this problem
        problem_penalty_minutes = problem_violations * 10
        
        return self.success({
            'problem_solved': has_accepted,
            'anti_cheat_required': not has_accepted,
            'problem_violation_count': problem_violations,
            'problem_penalty_minutes': problem_penalty_minutes,
            'anti_cheat_enabled': True
        })
        
def get_user_anti_cheat_penalty(user, contest):
    """
    Helper function to get total penalty time for a user in a contest
    """
    try:
        violation_count = AntiCheatViolation.objects.filter(
            contest=contest,
            user=user
        ).count()
        return violation_count * 10 * 60  # 10 minutes per violation in seconds
    except:
        return 0
    
class ContestViolationDetailsAPI(APIView):
    @login_required
    def get(self, request):
        """
        Get detailed violation information for a contest, grouped by user and problem
        """
        contest_id = request.GET.get('contest_id')
        user_id = request.GET.get('user_id')
        
        if not contest_id:
            return self.error("Contest ID is required")
        
        try:
            contest = Contest.objects.get(id=contest_id, visible=True)
        except Contest.DoesNotExist:
            return self.error("Contest not found")
        
        # Check permissions - only admins can see other users' violations
        if user_id and str(user_id) != str(request.user.id):
            if not request.user.is_contest_admin(contest):
                return self.error("Permission denied")
        
        # Base query - FIXED: Import Problem model properly
        from problem.models import Problem
        violations = AntiCheatViolation.objects.filter(contest=contest).select_related('user', 'problem')
        
        if user_id:
            violations = violations.filter(user_id=user_id)
        else:
            # If no user_id specified and not admin, show only current user's violations
            if not request.user.is_contest_admin(contest):
                violations = violations.filter(user=request.user)
        
        # Group violations by user and problem
        violation_data = {}
        
        for violation in violations:
            user_key = str(violation.user.id)
            problem_key = str(violation.problem.id) if violation.problem else 'general'
            
            if user_key not in violation_data:
                violation_data[user_key] = {
                    'user_id': violation.user.id,
                    'username': violation.user.username,
                    'problems': {},
                    'total_violations': 0,
                    'total_penalty_minutes': 0
                }
            
            if problem_key not in violation_data[user_key]['problems']:
                violation_data[user_key]['problems'][problem_key] = {
                    'problem_id': violation.problem.id if violation.problem else None,
                    'problem_title': violation.problem.title if violation.problem else 'General',
                    'violations': [],
                    'violation_count': 0
                }
            
            violation_data[user_key]['problems'][problem_key]['violations'].append({
                'id': violation.id,
                'violation_type': violation.violation_type,
                'violation_details': violation.violation_details,
                'timestamp': violation.timestamp,
                'ip_address': violation.ip_address
            })
            
            violation_data[user_key]['problems'][problem_key]['violation_count'] += 1
            violation_data[user_key]['total_violations'] += 1
        
        # Calculate penalties
        for user_data in violation_data.values():
            user_data['total_penalty_minutes'] = user_data['total_violations'] * 10
            
            # For ACM contests, show how penalty affects each problem
            if contest.rule_type == ContestRuleType.ACM:
                for problem_data in user_data['problems'].values():
                    problem_penalty = problem_data['violation_count'] * 10 * 60  # seconds
                    problem_data['penalty_seconds'] = problem_penalty
                    problem_data['penalty_minutes'] = problem_data['violation_count'] * 10
        
        return self.success({
            'contest_id': contest.id,
            'contest_title': contest.title,
            'rule_type': contest.rule_type,
            'violation_details': list(violation_data.values())
        })


class UserProblemViolationsAPI(APIView):
    @login_required
    def get(self, request):
        """
        Get violations for a specific user and problem combination
        """
        contest_id = request.GET.get('contest_id')
        problem_id = request.GET.get('problem_id')
        user_id = request.GET.get('user_id', request.user.id)
        
        if not contest_id:
            return self.error("Contest ID is required")
        
        try:
            contest = Contest.objects.get(id=contest_id, visible=True)
        except Contest.DoesNotExist:
            return self.error("Contest not found")
        
        # Check permissions
        if str(user_id) != str(request.user.id):
            if not request.user.is_contest_admin(contest):
                return self.error("Permission denied")
        
        # Base query
        violations = AntiCheatViolation.objects.filter(
            contest=contest,
            user_id=user_id
        ).select_related('problem')
        
        if problem_id:
            violations = violations.filter(problem_id=problem_id)
        
        violations_list = []
        for violation in violations:
            violations_list.append({
                'id': violation.id,
                'violation_type': violation.violation_type,
                'violation_details': violation.violation_details,
                'timestamp': violation.timestamp,
                'problem_id': violation.problem.id if violation.problem else None,
                'problem_title': violation.problem.title if violation.problem else None,
                'ip_address': violation.ip_address
            })
        
        total_count = len(violations_list)
        penalty_minutes = total_count * 10
        penalty_seconds = penalty_minutes * 60
        
        return self.success({
            'user_id': user_id,
            'contest_id': contest.id,
            'problem_id': problem_id,
            'violations': violations_list,
            'total_violations': total_count,
            'penalty_minutes': penalty_minutes,
            'penalty_seconds': penalty_seconds
        })
        
class ContestReviewAPI(APIView):
    @login_required
    def post(self, request):
        """
        Submit or update a contest review
        """
        import logging
        logger = logging.getLogger('django')
        
        try:
            data = request.data.copy()
            contest_id = data.get('contest_id')
            
            if not contest_id:
                return self.error("Contest ID is required")
            
            # Validate contest exists and user can access it
            try:
                contest = Contest.objects.get(id=contest_id, visible=True)
            except Contest.DoesNotExist:
                return self.error("Contest not found")
            
            # Check if user participated in contest (optional validation)
            # You might want to add this check based on your requirements
            # has_participated = Submission.objects.filter(
            #     contest=contest, user=request.user
            # ).exists()
            # if not has_participated:
            #     return self.error("You must participate in the contest to submit a review")
            
            # Set contest and user
            data['contest'] = contest.id
            
            # Check if review already exists
            existing_review = ContestReview.objects.filter(
                contest=contest, user=request.user
            ).first()
            
            if existing_review:
                # Update existing review
                serializer = CreateContestReviewSerializer(existing_review, data=data, partial=False)
                action = "updated"
            else:
                # Create new review
                serializer = CreateContestReviewSerializer(data=data)
                action = "created"
            
            if serializer.is_valid():
                review = serializer.save(
                    user=request.user,
                    ip_address=request.session.get("ip", "")
                )
                
                logger.info(f"Contest review {action} by user {request.user.username} for contest {contest.title}")
                
                return self.success({
                    'message': f'Review {action} successfully',
                    'review': ContestReviewSerializer(review).data
                })
            else:
                return self.error("Validation failed", data=serializer.errors)
                
        except Exception as e:
            logger.error(f"Error in ContestReviewAPI.post: {str(e)}")
            return self.error(f"Internal server error: {str(e)}")
    
    @login_required 
    def get(self, request):
        """
        Get user's review for a contest
        """
        contest_id = request.GET.get('contest_id')
        
        if not contest_id:
            return self.error("Contest ID is required")
        
        try:
            contest = Contest.objects.get(id=contest_id, visible=True)
        except Contest.DoesNotExist:
            return self.error("Contest not found")
        
        try:
            review = ContestReview.objects.get(contest=contest, user=request.user)
            return self.success(ContestReviewSerializer(review).data)
        except ContestReview.DoesNotExist:
            return self.success(None)  # No review found


class ContestReviewListAPI(APIView):
    def get(self, request):
        """
        Get all reviews for a contest (for admin/public viewing)
        """
        contest_id = request.GET.get('contest_id')
        
        if not contest_id:
            return self.error("Contest ID is required")
        
        try:
            contest = Contest.objects.get(id=contest_id, visible=True)
        except Contest.DoesNotExist:
            return self.error("Contest not found")
        
        # Check permissions - only admins can see all reviews
        if not request.user.is_authenticated or not request.user.is_contest_admin(contest):
            return self.error("Permission denied")
        
        reviews = ContestReview.objects.filter(contest=contest).select_related('user')
        
        # Add summary statistics
        total_reviews = reviews.count()
        if total_reviews > 0:
            avg_rating = reviews.aggregate(
                avg_rating=models.Avg('rating')
            )['avg_rating']
            
            rating_distribution = {}
            for i in range(1, 11):
                rating_distribution[str(i)] = reviews.filter(rating=i).count()
        else:
            avg_rating = 0
            rating_distribution = {}
        
        return self.success({
            'reviews': self.paginate_data(request, reviews, ContestReviewSerializer)['results'],
            'total_reviews': total_reviews,
            'average_rating': round(avg_rating, 2) if avg_rating else 0,
            'rating_distribution': rating_distribution
        })


class ContestReviewStatsAPI(APIView):
    def get(self, request):
        """
        Get review statistics for a contest
        """
        contest_id = request.GET.get('contest_id')
        
        if not contest_id:
            return self.error("Contest ID is required")
        
        try:
            contest = Contest.objects.get(id=contest_id, visible=True)
        except Contest.DoesNotExist:
            return self.error("Contest not found")
        
        # Public stats (no authentication required)
        reviews = ContestReview.objects.filter(contest=contest)
        total_reviews = reviews.count()
        
        if total_reviews == 0:
            return self.success({
                'total_reviews': 0,
                'average_rating': 0,
                'rating_distribution': {},
                'category_averages': {}
            })
        
        # Calculate statistics
        avg_rating = reviews.aggregate(avg_rating=models.Avg('rating'))['avg_rating']
        
        # Rating distribution
        rating_distribution = {}
        for i in range(1, 11):
            count = reviews.filter(rating=i).count()
            rating_distribution[str(i)] = {
                'count': count,
                'percentage': round((count / total_reviews) * 100, 1)
            }
        
        # Category averages
        category_averages = {}
        categories = ['user_interface', 'performance', 'problem_quality', 'judging_accuracy']
        
        for category in categories:
            ratings = []
            for review in reviews:
                if review.category_ratings and category in review.category_ratings:
                    ratings.append(review.category_ratings[category])
            
            if ratings:
                category_averages[category] = {
                    'average': round(sum(ratings) / len(ratings), 2),
                    'count': len(ratings)
                }
            else:
                category_averages[category] = {
                    'average': 0,
                    'count': 0
                }
        
        return self.success({
            'contest_id': contest.id,
            'contest_title': contest.title,
            'total_reviews': total_reviews,
            'average_rating': round(avg_rating, 2),
            'rating_distribution': rating_distribution,
            'category_averages': category_averages,
            'technical_issues_count': reviews.filter(had_technical_issues=True).count()
        })
from django.conf.urls import url

from ..views.oj import ContestAnnouncementListAPI
from ..views.oj import ContestPasswordVerifyAPI, ContestAccessAPI
from ..views.oj import ContestListAPI, ContestAPI
from ..views.oj import ContestRankAPI
from ..views.oj import AntiCheatViolationAPI, AntiCheatViolationListAPI, ProblemAntiCheatStatusAPI, AntiCheatStatusAPI, ContestViolationDetailsAPI, UserProblemViolationsAPI
from ..views.oj import ContestReviewAPI, ContestReviewListAPI, ContestReviewStatsAPI

urlpatterns = [
    url(r"^contests/?$", ContestListAPI.as_view(), name="contest_list_api"),
    url(r"^contest/?$", ContestAPI.as_view(), name="contest_api"),
    url(r"^contest/password/?$", ContestPasswordVerifyAPI.as_view(), name="contest_password_api"),
    url(r"^contest/announcement/?$", ContestAnnouncementListAPI.as_view(), name="contest_announcement_api"),
    url(r"^contest/access/?$", ContestAccessAPI.as_view(), name="contest_access_api"),
    url(r"^contest_rank/?$", ContestRankAPI.as_view(), name="contest_rank_api"),
    
    # Anti-cheat endpoints
    url(r"^contest/anti_cheat_violation/?$", AntiCheatViolationAPI.as_view(), name="contest_anti_cheat_violation_api"),
    url(r"^contest/anti_cheat_violations/?$", AntiCheatViolationListAPI.as_view(), name="contest_anti_cheat_violations_api"),
    url(r"^contest/problem_anti_cheat_status/?$", ProblemAntiCheatStatusAPI.as_view(), name="problem_anti_cheat_status_api"),
    url(r"^contest/anti_cheat_status/?$", AntiCheatStatusAPI.as_view(), name="contest_anti_cheat_status_api"),
    url(r"^contest/violation_details/?$", ContestViolationDetailsAPI.as_view(), name="contest_violation_details_api"),
    url(r"^contest/user_violations/?$", UserProblemViolationsAPI.as_view(), name="user_problem_violations_api"),
    
    # Contest Review endpoints
    url(r"^contest/review/?$", ContestReviewAPI.as_view(), name="contest_review_api"),
    url(r"^contest/reviews/?$", ContestReviewListAPI.as_view(), name="contest_review_list_api"),
    url(r"^contest/review/stats/?$", ContestReviewStatsAPI.as_view(), name="contest_review_stats_api"),
]
from django.conf.urls import url

from ..views.admin import ContestAnnouncementAPI, ContestAPI, ACMContestHelper, DownloadContestSubmissions, ContestReviewAdminAPI, ContestReviewStatsAdminAPI

urlpatterns = [
    url(r"^contest/?$", ContestAPI.as_view(), name="contest_admin_api"),
    url(r"^contest/announcement/?$", ContestAnnouncementAPI.as_view(), name="contest_announcement_admin_api"),
    url(r"^contest/acm_helper/?$", ACMContestHelper.as_view(), name="acm_contest_helper"),
    url(r"^download_submissions/?$", DownloadContestSubmissions.as_view(), name="acm_contest_helper"),
    
    url(r"^contest/reviews/?$", ContestReviewAdminAPI.as_view(), name="contest_reviews_admin_api"),
    url(r"^contest/review/stats/?$", ContestReviewStatsAdminAPI.as_view(), name="contest_review_stats_admin_api"),
]

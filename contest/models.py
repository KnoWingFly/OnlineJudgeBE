from utils.constants import ContestRuleType  # noqa
from django.db import models
from django.utils.timezone import now
from utils.models import JSONField

from utils.constants import ContestStatus, ContestType
from account.models import User
from utils.models import RichTextField


class Contest(models.Model):
    title = models.TextField()
    description = RichTextField()
    # show real time rank or cached rank
    real_time_rank = models.BooleanField()
    password = models.TextField(null=True)
    # enum of ContestRuleType
    rule_type = models.TextField()
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    create_time = models.DateTimeField(auto_now_add=True)
    last_update_time = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    # 是否可见 false的话相当于删除
    visible = models.BooleanField(default=True)
    allowed_ip_ranges = JSONField(default=list)

    @property
    def status(self):
        if self.start_time > now():
            # 没有开始 返回1
            return ContestStatus.CONTEST_NOT_START
        elif self.end_time < now():
            # 已经结束 返回-1
            return ContestStatus.CONTEST_ENDED
        else:
            # 正在进行 返回0
            return ContestStatus.CONTEST_UNDERWAY

    @property
    def contest_type(self):
        if self.password:
            return ContestType.PASSWORD_PROTECTED_CONTEST
        return ContestType.PUBLIC_CONTEST

    # 是否有权查看problem 的一些统计信息 诸如submission_number, accepted_number 等
    def problem_details_permission(self, user):
        return self.rule_type == ContestRuleType.ACM or \
               self.status == ContestStatus.CONTEST_ENDED or \
               user.is_authenticated and user.is_contest_admin(self) or \
               self.real_time_rank

    class Meta:
        db_table = "contest"
        ordering = ("-start_time",)


class AbstractContestRank(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    contest = models.ForeignKey(Contest, on_delete=models.CASCADE)
    submission_number = models.IntegerField(default=0)

    class Meta:
        abstract = True


class ACMContestRank(AbstractContestRank):
    accepted_number = models.IntegerField(default=0)
    # total_time is only for ACM contest, total_time =  ac time + none-ac times * 20 * 60
    total_time = models.IntegerField(default=0)
    # {"23": {"is_ac": True, "ac_time": 8999, "error_number": 2, "is_first_ac": True}}
    # key is problem id
    submission_info = JSONField(default=dict)

    class Meta:
        db_table = "acm_contest_rank"
        unique_together = (("user", "contest"),)


class OIContestRank(AbstractContestRank):
    total_score = models.IntegerField(default=0)
    # {"23": 333}
    # key is problem id, value is current score
    submission_info = JSONField(default=dict)

    class Meta:
        db_table = "oi_contest_rank"
        unique_together = (("user", "contest"),)


class ContestAnnouncement(models.Model):
    contest = models.ForeignKey(Contest, on_delete=models.CASCADE)
    title = models.TextField()
    content = RichTextField()
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    visible = models.BooleanField(default=True)
    create_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "contest_announcement"
        ordering = ("-create_time",)

class AntiCheatViolation(models.Model):
    VIOLATION_TYPES = (
        ('fullscreen_exit', 'Exited Fullscreen'),
        ('tab_switch', 'Switched Tab/Window'),
        ('dev_tools', 'Opened Developer Tools'),
        ('forbidden_keys', 'Pressed Forbidden Keys'),
        ('context_menu', 'Opened Context Menu'),
        ('window_blur', 'Window Lost Focus'),
        ('page_leave', 'Attempted to Leave Page'),
        ('window_resize', 'Suspicious Window Resize'),
    )
    
    contest = models.ForeignKey('Contest', on_delete=models.CASCADE)
    problem = models.ForeignKey('problem.Problem', on_delete=models.CASCADE, null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    violation_type = models.CharField(max_length=50, choices=VIOLATION_TYPES)
    violation_details = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    class Meta:
        db_table = 'anti_cheat_violation'
        ordering = ['-timestamp']
        
    def __str__(self):
        return f"{self.user.username} - {self.violation_type} in {self.contest.title}"
    
# Add this to your contest/models.py file

class ContestReview(models.Model):
    contest = models.ForeignKey(Contest, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    
    # Rating fields
    rating = models.IntegerField()  # Overall rating (1-10)
    category_ratings = JSONField(default=dict)  # Category-specific ratings
    
    # Review content
    review_text = models.TextField()
    
    # Additional questions
    had_technical_issues = models.BooleanField(default=False)
    technical_issues_detail = models.TextField(blank=True)
    
    # Metadata
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    
    class Meta:
        db_table = 'contest_review'
        unique_together = ('contest', 'user')  # One review per user per contest
        ordering = ['-submitted_at']
        
    def __str__(self):
        return f"{self.user.username}'s review for {self.contest.title} ({self.rating}/10)"
    
    @property
    def average_category_rating(self):
        """Calculate average of all category ratings"""
        if not self.category_ratings:
            return 0
        return sum(self.category_ratings.values()) / len(self.category_ratings)
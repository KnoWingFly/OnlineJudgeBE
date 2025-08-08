from utils.api import UsernameSerializer, serializers

from .models import Contest, ContestAnnouncement, ContestRuleType
from .models import ACMContestRank, OIContestRank
from .models import ContestReview


class CreateConetestSeriaizer(serializers.Serializer):
    title = serializers.CharField(max_length=128)
    description = serializers.CharField()
    start_time = serializers.DateTimeField()
    end_time = serializers.DateTimeField()
    rule_type = serializers.ChoiceField(choices=[ContestRuleType.ACM, ContestRuleType.OI])
    password = serializers.CharField(allow_blank=True, max_length=32)
    visible = serializers.BooleanField()
    real_time_rank = serializers.BooleanField()
    allowed_ip_ranges = serializers.ListField(child=serializers.CharField(max_length=32), allow_empty=True)


class EditConetestSeriaizer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField(max_length=128)
    description = serializers.CharField()
    start_time = serializers.DateTimeField()
    end_time = serializers.DateTimeField()
    password = serializers.CharField(allow_blank=True, allow_null=True, max_length=32)
    visible = serializers.BooleanField()
    real_time_rank = serializers.BooleanField()
    allowed_ip_ranges = serializers.ListField(child=serializers.CharField(max_length=32))


class ContestAdminSerializer(serializers.ModelSerializer):
    created_by = UsernameSerializer()
    status = serializers.CharField()
    contest_type = serializers.CharField()

    class Meta:
        model = Contest
        fields = "__all__"


class ContestSerializer(ContestAdminSerializer):
    class Meta:
        model = Contest
        exclude = ("password", "visible", "allowed_ip_ranges")


class ContestAnnouncementSerializer(serializers.ModelSerializer):
    created_by = UsernameSerializer()

    class Meta:
        model = ContestAnnouncement
        fields = "__all__"


class CreateContestAnnouncementSerializer(serializers.Serializer):
    contest_id = serializers.IntegerField()
    title = serializers.CharField(max_length=128)
    content = serializers.CharField()
    visible = serializers.BooleanField()


class EditContestAnnouncementSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField(max_length=128, required=False)
    content = serializers.CharField(required=False, allow_blank=True)
    visible = serializers.BooleanField(required=False)


class ContestPasswordVerifySerializer(serializers.Serializer):
    contest_id = serializers.IntegerField()
    password = serializers.CharField(max_length=30, required=True)


class ACMContestRankSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()

    class Meta:
        model = ACMContestRank
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        self.is_contest_admin = kwargs.pop("is_contest_admin", False)
        super().__init__(*args, **kwargs)

    def get_user(self, obj):
        return UsernameSerializer(obj.user, need_real_name=self.is_contest_admin).data
    
    def to_representation(self, instance):
        data = super().to_representation(instance)

        # Check if the instance was processed by the penalty logic in `get_rank`.
        # `total_penalty_time` is a custom attribute added during that process.
        if hasattr(instance, 'total_penalty_time'):
            # The rank object includes penalty data. Add summary fields for the frontend.
            data['total_violation_count'] = instance.total_violation_count
            data['total_penalty_time'] = instance.total_penalty_time
            
            # --- NEW: ADD REVIEW PENALTY TO RESPONSE ---
            # Expose the specific penalty for not submitting a review.
            data['review_penalty_applied'] = getattr(instance, 'review_penalty_applied', 0)
            
            # For admins, expose the original total_time for comparison.
            if self.is_contest_admin:
                data['original_total_time'] = instance.original_total_time
        else:
            # Fallback for data that wasn't processed (e.g., from an old cache).
            # Provide default zero-value fields so the frontend doesn't break.
            data['total_violation_count'] = 0
            data['total_penalty_time'] = 0
            data['review_penalty_applied'] = 0 # Default value
            if self.is_contest_admin:
                data['original_total_time'] = instance.total_time
                
        return data


class OIContestRankSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()

    class Meta:
        model = OIContestRank
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        self.is_contest_admin = kwargs.pop("is_contest_admin", False)
        super().__init__(*args, **kwargs)

    def get_user(self, obj):
        return UsernameSerializer(obj.user, need_real_name=self.is_contest_admin).data
    
    def to_representation(self, instance):
        data = super().to_representation(instance)
        
        # Add violation and penalty information
        if hasattr(instance, 'violation_count'):
            # Information from get_rank() method with penalties applied
            data['violation_count'] = instance.violation_count
            data['penalty_points'] = getattr(instance, 'penalty_points', 0)
            data['total_score_with_penalty'] = getattr(instance, 'total_score_with_penalty', instance.total_score)
            data['original_total_score'] = instance.total_score  # Keep original for admin reference
            
            # Show the penalized score as the main total_score for ranking
            data['total_score'] = data['total_score_with_penalty']
            
            # Add penalty breakdown if admin
            if self.is_contest_admin:
                data['penalty_breakdown'] = {
                    'violations': instance.violation_count,
                    'penalty_points': getattr(instance, 'penalty_points', 0),
                    'original_score': instance.total_score,
                    'penalized_score': data['total_score_with_penalty']
                }
        else:
            # Fallback: calculate violations from database if not provided by get_rank()
            try:
                from .models import AntiCheatViolation
                violation_count = AntiCheatViolation.objects.filter(
                    contest_id=instance.contest_id,
                    user=instance.user
                ).count()
                
                penalty_points = violation_count * 10  # 10 points per violation
                
                data['violation_count'] = violation_count
                data['penalty_points'] = penalty_points
                data['total_score_with_penalty'] = max(0, instance.total_score - penalty_points)
                data['original_total_score'] = instance.total_score
                
                # Show penalized score
                data['total_score'] = data['total_score_with_penalty']
                
                if self.is_contest_admin:
                    data['penalty_breakdown'] = {
                        'violations': violation_count,
                        'penalty_points': penalty_points,
                        'original_score': instance.total_score,
                        'penalized_score': data['total_score_with_penalty']
                    }
            except:
                # If violation model not available or error, show defaults
                data['violation_count'] = 0
                data['penalty_points'] = 0
                data['total_score_with_penalty'] = instance.total_score
                data['original_total_score'] = instance.total_score
        
        return data


class ACMContesHelperSerializer(serializers.Serializer):
    contest_id = serializers.IntegerField()
    problem_id = serializers.CharField()
    rank_id = serializers.IntegerField()
    checked = serializers.BooleanField()


# Additional serializer for violation details
class ViolationDetailSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    violation_type = serializers.CharField()
    violation_details = serializers.CharField()
    timestamp = serializers.DateTimeField()
    problem_id = serializers.IntegerField(allow_null=True)
    problem_title = serializers.CharField(allow_null=True)
    ip_address = serializers.IPAddressField(allow_null=True)


class UserViolationSummarySerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    username = serializers.CharField()
    total_violations = serializers.IntegerField()
    total_penalty_minutes = serializers.IntegerField()
    problems = serializers.DictField()  # Will contain problem-specific violation data
    
class ContestReviewSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    user_id = serializers.IntegerField(source='user.id', read_only=True)
    contest_title = serializers.CharField(source='contest.title', read_only=True)
    
    class Meta:
        model = ContestReview
        fields = [
            'id', 'contest', 'user', 'username', 'user_id', 'contest_title',
            'rating', 'category_ratings', 'review_text', 
            'had_technical_issues', 'technical_issues_detail',
            'submitted_at', 'updated_at'
        ]
        read_only_fields = ['user', 'submitted_at', 'updated_at']

class CreateContestReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContestReview
        fields = [
            'contest', 'rating', 'category_ratings', 'review_text',
            'had_technical_issues', 'technical_issues_detail'
        ]
        
    def validate_rating(self, value):
        if not (1 <= value <= 10):
            raise serializers.ValidationError("Rating must be between 1 and 10")
        return value
        
    def validate_review_text(self, value):
        if len(value.strip()) < 10:
            raise serializers.ValidationError("Review text must be at least 10 characters long")
        return value.strip()
        
    def validate_category_ratings(self, value):
        """Validate category ratings"""
        valid_categories = ['user_interface', 'performance', 'problem_quality', 'judging_accuracy']
        
        for category, rating in value.items():
            if category not in valid_categories:
                raise serializers.ValidationError(f"Invalid category: {category}")
            if not isinstance(rating, int) or not (1 <= rating <= 5):
                raise serializers.ValidationError(f"Category rating for {category} must be between 1 and 5")
        
        return value
from django.conf import settings
from django.db import models


class ApplicantType(models.TextChoices):
    """Who is using the app. Picked at sign-up ("I am a ...")."""

    HIGH_SCHOOL = "high_school", "High school student"
    COLLEGE = "college", "College student"
    PROFESSIONAL = "professional", "Working professional"
    SUPPORTER = "supporter", "Parent or counselor"


# One short line under each option on the sign-up page.
APPLICANT_TYPE_HINTS = {
    ApplicantType.HIGH_SCHOOL: "Applying to college",
    ApplicantType.COLLEGE: "Transfer or grad school",
    ApplicantType.PROFESSIONAL: "Grad school, MBA, and more",
    ApplicantType.SUPPORTER: "Helping someone apply",
}


class Profile(models.Model):
    """Account-level facts about a person, kept next to Django's built-in User.

    Accounts created outside sign-up (createsuperuser, the seed command) may
    have no Profile; use Profile.for_user(user) to read one safely.
    """

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    applicant_type = models.CharField(max_length=20, choices=ApplicantType.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user} ({self.get_applicant_type_display()})"

    @classmethod
    def for_user(cls, user):
        """The user's Profile, or None (never raises) for anonymous or profile-less users."""
        if not getattr(user, "is_authenticated", False):
            return None
        return cls.objects.filter(user=user).first()

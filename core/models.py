"""Domain models for Admit Compass.  Owner: D.

Design rules that come from the product promise ("every figure comes from
federal data, not LLM memory"):

1. Every metric is nullable.  College Scorecard suppresses figures for small
   schools, so a missing value must stay missing.  Never store 0 for "not
   reported" -- it would silently become a real number in a comparison.
2. Every row records which data release it came from, so the interface can
   show the figure's provenance and link to the official page.
3. `data_release == Institution.SAMPLE` marks rows created by the local seed
   rather than by a real import, so demo data can never be mistaken for
   federal data.
"""

from django.conf import settings
from django.db import models


class Institution(models.Model):
    """One school, keyed by its federal IPEDS UNITID."""

    SAMPLE = "SAMPLE"

    class Ownership(models.IntegerChoices):
        PUBLIC = 1, "Public"
        PRIVATE_NONPROFIT = 2, "Private nonprofit"
        PRIVATE_FOR_PROFIT = 3, "Private for-profit"

    class PredominantDegree(models.IntegerChoices):
        CERTIFICATE = 1, "Certificate"
        ASSOCIATE = 2, "Associate"
        BACHELOR = 3, "Bachelor's"
        GRADUATE = 4, "Graduate"

    # --- identity (join key for every federal dataset) ---
    unitid = models.PositiveIntegerField(unique=True, db_index=True)
    name = models.CharField(max_length=255, db_index=True)
    city = models.CharField(max_length=120, blank=True)
    state = models.CharField(max_length=2, blank=True, db_index=True)
    school_url = models.URLField(blank=True)

    ownership = models.IntegerField(choices=Ownership.choices, null=True, blank=True)
    predominant_degree = models.IntegerField(choices=PredominantDegree.choices, null=True, blank=True)

    # --- metrics: all nullable on purpose (see module docstring) ---
    enrollment_undergrad = models.PositiveIntegerField(null=True, blank=True)
    admission_rate = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    sat_average = models.PositiveIntegerField(null=True, blank=True)
    tuition_in_state = models.PositiveIntegerField(null=True, blank=True)
    tuition_out_of_state = models.PositiveIntegerField(null=True, blank=True)
    cost_attendance = models.PositiveIntegerField(null=True, blank=True)
    completion_rate_150 = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    retention_rate = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    median_earnings_10yr = models.PositiveIntegerField(null=True, blank=True)
    median_debt = models.PositiveIntegerField(null=True, blank=True)

    # --- provenance ---
    data_release = models.CharField(
        max_length=20,
        default=SAMPLE,
        db_index=True,
        help_text='College Scorecard release label, e.g. "2024-25". "SAMPLE" means locally seeded demo data.',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return f"{self.name} ({self.state})" if self.state else self.name

    @property
    def is_sample(self):
        """True when this row is demo data, not a real federal import."""
        return self.data_release == self.SAMPLE

    @property
    def scorecard_url(self):
        """Official page for this school, so any figure can be checked by hand."""
        if self.is_sample:
            return ""
        return f"https://collegescorecard.ed.gov/school/?{self.unitid}"


class Shortlist(models.Model):
    """A list of schools a user is considering."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="shortlists")
    name = models.CharField(max_length=120, default="My shortlist")
    institutions = models.ManyToManyField(Institution, through="ShortlistItem", related_name="shortlists")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at",)
        constraints = (models.UniqueConstraint(fields=["user", "name"], name="unique_shortlist_name_per_user"),)

    def __str__(self):
        return f"{self.name} ({self.user})"


class ShortlistItem(models.Model):
    """One school on one shortlist, with the user's own note."""

    shortlist = models.ForeignKey(Shortlist, on_delete=models.CASCADE, related_name="items")
    institution = models.ForeignKey(Institution, on_delete=models.CASCADE, related_name="items")
    note = models.TextField(blank=True)
    position = models.PositiveIntegerField(default=0)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("position", "added_at")
        constraints = (
            models.UniqueConstraint(fields=["shortlist", "institution"], name="unique_institution_per_shortlist"),
        )

    def __str__(self):
        return f"{self.institution.name} on {self.shortlist.name}"

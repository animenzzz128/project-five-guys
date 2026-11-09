"""Sign-up and log-in forms. People sign in with their email address.

We keep Django's built-in User model (the course asks for the framework's
standard authentication). A new account stores the lowercased email in both
`username` and `email`, so the default ModelBackend works unchanged and no
settings change is needed.

Accounts made some other way (createsuperuser, the seed command) may have a
username that is not their email. The log-in form also looks people up by
email (see resolve_username), so `grader@example.com` works even if the
username is `grader`.
"""

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.db import transaction

from .models import APPLICANT_TYPE_HINTS, ApplicantType, Profile

User = get_user_model()

PASSWORD_HINT = "At least 8 characters. Not all numbers, and not a common password."


def normalize_email(value):
    return (value or "").strip().lower()


def email_taken(email):
    return User.objects.filter(email__iexact=email).exists() or User.objects.filter(username__iexact=email).exists()


class SignupForm(UserCreationForm):
    applicant_type = forms.ChoiceField(
        label="I am a…",
        choices=ApplicantType.choices,
        widget=forms.RadioSelect,
        error_messages={"required": "Choose the option that describes you best."},
    )
    email = forms.EmailField(
        label="Email",
        max_length=150,  # the email doubles as the username, which is capped at 150
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
    )

    field_order = ("applicant_type", "email", "password1", "password2")

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("email",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].label = "Password"
        self.fields["password1"].help_text = PASSWORD_HINT
        self.fields["password2"].label = "Confirm password"
        self.fields["password2"].help_text = ""

    def applicant_options(self):
        """(radio, value, title, hint) for each choice, so the template can draw option cards."""
        for radio in self["applicant_type"]:
            value = radio.data["value"]
            yield radio, value, radio.choice_label, APPLICANT_TYPE_HINTS.get(value, "")

    def clean_email(self):
        email = normalize_email(self.cleaned_data.get("email"))
        if email_taken(email):
            raise forms.ValidationError("An account with this email already exists. Try logging in instead.")
        return email

    def _post_clean(self):
        # Fill the username before password validation, so the "too similar to
        # your username/email" check sees it.
        email = self.cleaned_data.get("email")
        if email:
            self.instance.username = email
        super()._post_clean()

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.username = user.email
        if commit:
            # User and Profile land together or not at all.
            with transaction.atomic():
                user.save()
                Profile.objects.create(user=user, applicant_type=self.cleaned_data["applicant_type"])
        return user


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.CharField(
        label="Email",
        max_length=254,
        widget=forms.TextInput(
            attrs={"autocomplete": "username", "inputmode": "email", "spellcheck": "false"}
        ),
    )

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "That email and password don't match. Check both and try again.",
    }

    def clean(self):
        identifier = (self.cleaned_data.get("username") or "").strip()
        self.cleaned_data["username"] = resolve_username(identifier)
        return super().clean()


def _only(queryset):
    """The single username in the queryset, or None if there are zero or several."""
    found = list(queryset.values_list("username", flat=True)[:2])
    return found[0] if len(found) == 1 else None


def resolve_username(identifier):
    """Map what someone typed in the Email box to the username Django should check.

    Most specific match wins, so no account can shadow another:
    1. an exact username            (e.g. "admin", or "a@x.com" stored as-is)
    2. a username, ignoring case    (e.g. typed "A@X.com" for "a@x.com")
    3. an email, ignoring case      (seed accounts whose username isn't their email)
    Ambiguous matches are skipped, and the text is then tried unchanged.
    """
    if not identifier:
        return identifier
    if User.objects.filter(username=identifier).exists():
        return identifier
    by_username = _only(User.objects.filter(username__iexact=identifier))
    if by_username:
        return by_username
    if "@" in identifier:
        by_email = _only(User.objects.filter(email__iexact=identifier))
        if by_email:
            return by_email
    return identifier

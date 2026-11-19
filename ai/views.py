from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from .client import AIBadOutput, AILimitReached, AIUnavailable
from .models import SearchInterpretation
from .search import MAX_NAME, MAX_TEXT, available_states, normalize, parse_sentence

SESSION_TEXT = "ai_search_text"  # keeps the box filled after any outcome
UNAVAILABLE = "AI search is unavailable right now, showing a plain name search."


def _colleges(params=None):
    query = urlencode(params, doseq=True) if params else ""
    return redirect(f"{reverse('colleges')}?{query}" if query else reverse("colleges"))


@require_POST
def ask(request):
    """Turn one sentence into `/colleges/` filters (#38).  Owner: C."""
    if not request.user.is_authenticated:
        return redirect_to_login(reverse("colleges"))
    text = (request.POST.get("example") or request.POST.get("text") or "").replace("\x00", "").strip()
    request.session[SESSION_TEXT] = text[:MAX_TEXT]
    if not text:
        messages.error(request, "Describe your ideal college first.")
        return _colleges()
    if len(text) > MAX_TEXT:
        messages.error(request, f"Keep it to {MAX_TEXT} characters or fewer.")
        return _colleges()

    try:
        raw = parse_sentence(text, request.user)
    except AILimitReached:
        messages.warning(request, "You've used today's AI searches.")
        return _colleges()
    except (AIUnavailable, AIBadOutput):
        messages.info(request, UNAVAILABLE)
        return _colleges({"q": text[:MAX_NAME]})

    if raw.get("intent") == "out_of_scope":
        messages.info(request, "That doesn't look like a college search. Describe the kind of college you want.")
        return _colleges()

    params, notes = normalize(raw, available_states())
    interpretation = SearchInterpretation.objects.create(
        user=request.user, text=text, raw_json=raw, params=params, notes=notes,
    )
    if notes:
        messages.info(request, "Can't filter by: " + "; ".join(f"{n['phrase']} ({n['reason']})" for n in notes))
    return _colleges({**params, "interp": interpretation.pk})

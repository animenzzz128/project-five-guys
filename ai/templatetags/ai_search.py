from django import template

from ai.models import SearchInterpretation

register = template.Library()


@register.simple_tag(takes_context=True)
def ai_interpretation(context):
    """The viewer's own SearchInterpretation named by ?interp=, else None.

    Someone else's id (or a bad one) is ignored exactly like a missing one, so
    a shared or guessed link never shows another student's sentence (#38).
    """
    request = context.get("request")
    if request is None or not request.user.is_authenticated:
        return None
    pk = request.GET.get("interp", "")
    if not pk.isascii() or not pk.isdecimal() or len(pk) > 18:
        return None
    return SearchInterpretation.objects.filter(pk=int(pk), user=request.user).first()

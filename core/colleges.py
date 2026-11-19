from django import forms
from django.core.paginator import Paginator
from django.db.models import Case, F, IntegerField, Q, Value, When
from django.http import QueryDict
from django.shortcuts import get_object_or_404, render

from .models import Institution, Program
from .ranking import FACTORS, match_majors, parse_prefer, prefer_param, rank
from .similarity import NotComparable, similar_institutions
from .shortlists import with_saved_item


SORT_CHOICES = [("", "Name"), ("match", "Best match"), ("cost", "Lowest cost"), ("earnings", "Highest earnings"),
                ("admit_rate", "Lowest admission rate"), ("size", "Most undergraduates")]
SORT_ORDER = {  # schools that don't report the figure go last, never counted as 0
    "cost": F("cost_attendance").asc(nulls_last=True),
    "earnings": F("median_earnings_10yr").desc(nulls_last=True),
    "admit_rate": F("admission_rate").asc(nulls_last=True),
    "size": F("enrollment_undergrad").desc(nulls_last=True),
}
SIMILAR_LIMIT = 50
PAGE_SIZE = 25
MAX_RELAX = 2
LOOKUPS = {"q": "name__icontains", "state": "state__in", "ownership": "ownership",
           "tuition_max": "tuition_in_state__lte", "size_min": "enrollment_undergrad__gte",
           "size_max": "enrollment_undergrad__lte", "max_cost": "cost_attendance__lte",
           "min_earnings": "median_earnings_10yr__gte", "min_admit": "admission_rate__gte",
           "max_admit": "admission_rate__lte", "min_completion": "completion_rate_150__gte"}


class TextListField(forms.Field):
    """A repeated query parameter of short free-text values (major=..., prefer=...), as a hidden list."""

    widget = forms.MultipleHiddenInput

    def to_python(self, value):
        values = value if isinstance(value, (list, tuple)) else ([value] if value else [])
        cleaned = []
        for item in values:
            item = " ".join(str(item).replace("\x00", "").split()).lower()[:60]
            if item and item not in cleaned:
                cleaned.append(item)
        return cleaned[:5]


class CollegeFilters(forms.Form):
    q = forms.CharField(label="College name", max_length=255, required=False,
                        widget=forms.TextInput(attrs={"placeholder": "e.g. Michigan", "type": "search"}))
    state = forms.MultipleChoiceField(label="States and territories", required=False,
                                      widget=forms.CheckboxSelectMultiple)
    ownership = forms.TypedChoiceField(label="School type", required=False, coerce=int,
                                       choices=[("", "Any type"), *Institution.Ownership.choices])
    tuition_max = forms.IntegerField(label="Maximum in-state tuition ($)", required=False, min_value=0,
                                     max_value=2147483647)
    size_min = forms.IntegerField(label="Minimum undergraduates", required=False, min_value=0, max_value=2147483647)
    size_max = forms.IntegerField(label="Maximum undergraduates", required=False, min_value=0, max_value=2147483647)
    # Added for the one-sentence AI search (#38, owner C). Fractions, majors,
    # preferences and similar_to are hidden fields: they arrive from the AI
    # search and leave through their chips; Apply filters and paging keep them.
    max_cost = forms.IntegerField(label="Maximum cost of attendance ($)", required=False, min_value=0,
                                  max_value=2147483647)
    min_earnings = forms.IntegerField(label="Minimum earnings after 10 years ($)", required=False, min_value=0,
                                      max_value=2147483647)
    min_admit = forms.DecimalField(required=False, min_value=0, max_value=1, max_digits=5, decimal_places=4,
                                   widget=forms.HiddenInput)
    max_admit = forms.DecimalField(required=False, min_value=0, max_value=1, max_digits=5, decimal_places=4,
                                   widget=forms.HiddenInput)
    min_completion = forms.DecimalField(required=False, min_value=0, max_value=1, max_digits=5, decimal_places=4,
                                        widget=forms.HiddenInput)
    major = TextListField(required=False)
    prefer = TextListField(required=False)
    similar_to = forms.IntegerField(required=False, min_value=0, max_value=2147483647, widget=forms.HiddenInput)
    sort = forms.ChoiceField(label="Sort by", required=False, choices=SORT_CHOICES)

    def clean_prefer(self):
        return [prefer_param(name, weight) for name, weight in parse_prefer(self.cleaned_data["prefer"])]

    def clean(self):
        values = super().clean()
        for low_key, high_key in (("size_min", "size_max"), ("min_admit", "max_admit")):
            low, high = values.get(low_key), values.get(high_key)
            if low is not None and high is not None and low > high:
                self.add_error(high_key, "Enter a maximum at least as large as the minimum.")
        return values

    def active_filters(self):
        """One chip per applied value: {"label", "query" without it, "kind": must | prefer | sort}."""
        if not self.is_valid():
            return []
        values = self.cleaned_data
        chips = []

        def add(field, label, value=None, kind="must"):
            query = self.data.copy()
            query.pop("page", None)
            if field == "state":
                query.setlist(field, [state for state in values[field] if state != value])
            elif field == "major":
                query.setlist(field, [major for major in values[field] if major != value])
            elif field == "prefer":
                query.setlist(field, [wish for wish in values[field] if wish.partition(":")[0] != value])
            else:
                query.pop(field, None)
            chips.append({"label": label, "query": query.urlencode(), "kind": kind})

        if values["q"]:
            add("q", values["q"])
        for state in values["state"]:
            add("state", state, state)
        if values["ownership"]:
            add("ownership", Institution.Ownership(values["ownership"]).label)
        for field, label in (("tuition_max", "Tuition ≤ ${:,}"), ("size_min", "Students ≥ {:,}"),
                             ("size_max", "Students ≤ {:,}"), ("max_cost", "Cost ≤ ${:,}"),
                             ("min_earnings", "Earnings ≥ ${:,}"), ("min_admit", "Admission ≥ {:.0%}"),
                             ("max_admit", "Admission ≤ {:.0%}"), ("min_completion", "Graduation ≥ {:.0%}")):
            if values[field] is not None:
                add(field, label.format(values[field]))
        for major in values["major"]:
            add("major", f"Major: {major}", major)
        if values["similar_to"] is not None:
            name = Institution.objects.filter(unitid=values["similar_to"]).values_list("name", flat=True).first()
            add("similar_to", f"Like {name or values['similar_to']}")
        for name, _ in parse_prefer(values["prefer"]):
            add("prefer", f"Prefers: {FACTORS[name].label}", name, kind="prefer")
        if values["sort"]:
            add("sort", f"Sorted by {dict(SORT_CHOICES)[values['sort']].lower()}", kind="sort")
        return chips


def _similar_ids(unitid, schools):
    """PKs of up to SIMILAR_LIMIT schools in `schools` most like `unitid`, closest first (#16)."""
    try:
        results = similar_institutions(unitid, k=SIMILAR_LIMIT, filters=Q(pk__in=schools.values("pk")))
    except (Institution.DoesNotExist, NotComparable):
        return []
    return [result.institution.pk for result in results]


def _candidates(schools, values):
    """Apply the hard requirements. Returns (queryset, similarity-ordered pks or None)."""
    schools = schools.filter(**{lookup: values[key] for key, lookup in LOOKUPS.items()
                                if values[key] not in (None, "", [])})
    if values["major"]:  # any of the named fields, as a federal bachelor's program
        codes = {code for keyword in values["major"] for code, _ in match_majors(keyword)}
        offering = Program.objects.filter(credential_level=3, cip_code__in=codes).values("institution")
        schools = schools.filter(pk__in=offering)
    similar = None
    if values["similar_to"] is not None:
        similar = _similar_ids(values["similar_to"], schools)
        schools = schools.filter(pk__in=similar)
    return schools, similar


def _relaxations(form, schools):
    """When nothing matches: the hard requirements whose removal alone would bring results back."""
    suggestions = []
    for chip in form.active_filters():
        if chip["kind"] != "must":
            continue
        relaxed = CollegeFilters(QueryDict(chip["query"]))
        relaxed.fields["state"].choices = form.fields["state"].choices
        if relaxed.is_valid():
            count = _candidates(schools, relaxed.cleaned_data)[0].count()
            if count:
                suggestions.append({"label": chip["label"], "query": chip["query"], "count": count})
    return sorted(suggestions, key=lambda suggestion: -suggestion["count"])[:MAX_RELAX]


def colleges(request):
    schools = Institution.objects.all()
    # Staging can start with only the demo seed. Once imported, show real schools.
    real = schools.exclude(data_release=Institution.SAMPLE)
    demo = not real.exists()
    if not demo:
        schools = real
    states = schools.exclude(state="").order_by("state").values_list("state", flat=True).distinct()
    form = CollegeFilters(request.GET, label_suffix="")
    form.fields["state"].choices = [(state, state) for state in states]
    page_number = request.GET.get("page")
    relax = []
    if not form.is_valid():
        page = Paginator(schools.none(), PAGE_SIZE).get_page(page_number)
        return render(request, "core/colleges.html", {"form": form, "page": page, "demo": demo, "relax": relax})

    values = form.cleaned_data
    candidates, similar = _candidates(schools, values)
    prefer = parse_prefer(values["prefer"])
    sort = values["sort"] or ("match" if prefer else "")
    if sort == "match" and (prefer or similar):
        # Hybrid ranking (#38): hard filters above, soft preferences (and similarity) here.
        extra = None
        if similar:
            source = Institution.objects.filter(unitid=values["similar_to"]).values_list("name", flat=True).first()
            extra = {pk: (1 - i / max(len(similar) - 1, 1), f"#{i + 1} most similar to {source}")
                     for i, pk in enumerate(similar)}
        ranked = rank(candidates, prefer, extra=extra)
        page = Paginator(ranked, PAGE_SIZE).get_page(page_number)
        reasons = {result.pk: result.reasons for result in page.object_list}
        found = {school.pk: school for school in
                 with_saved_item(Institution.objects.filter(pk__in=list(reasons)), request.user)}
        for school in found.values():
            school.match_reasons = reasons[school.pk]
        page.object_list = [found[result.pk] for result in page.object_list]
    else:
        order = ["name", "unitid"]
        if similar:
            rank_order = Case(*[When(pk=pk, then=Value(i)) for i, pk in enumerate(similar)],
                              output_field=IntegerField())
            candidates = candidates.annotate(similar_rank=rank_order)
            order = ["similar_rank", *order]
        if sort in SORT_ORDER:
            order = [SORT_ORDER[sort], *order]
        page = Paginator(with_saved_item(candidates, request.user).order_by(*order), PAGE_SIZE).get_page(page_number)
    if not page.paginator.count:
        relax = _relaxations(form, schools)
    return render(request, "core/colleges.html", {"form": form, "page": page, "demo": demo, "relax": relax})


def college_detail(request, unitid):
    school = get_object_or_404(with_saved_item(Institution.objects.all(), request.user), unitid=unitid)
    return render(request, "core/college_detail.html", {"school": school})


def similar_colleges(request, unitid):
    """Up to ten schools like this one, each with two or three plain reasons (#16).  Owner: B."""
    school = get_object_or_404(with_saved_item(Institution.objects.all(), request.user), unitid=unitid)
    try:
        results = similar_institutions(unitid)
    except NotComparable:
        results = None
    if results and request.user.is_authenticated:
        matches = Institution.objects.filter(pk__in=[result.institution.pk for result in results])
        saved = dict(with_saved_item(matches, request.user).values_list("pk", "saved_item_id"))
        for result in results:
            result.institution.saved_item_id = saved.get(result.institution.pk)
    return render(request, "core/similar.html", {"school": school, "results": results})

from django import forms
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render

from .models import Institution
from .similarity import NotComparable, similar_institutions
from .shortlists import with_saved_item


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

    def clean(self):
        values = super().clean()
        low, high = values.get("size_min"), values.get("size_max")
        if low is not None and high is not None and low > high:
            self.add_error("size_max", "Enter a maximum at least as large as the minimum.")
        return values


    def active_filters(self):
        if not self.is_valid():
            return []
        values = self.cleaned_data
        chips = []

        def add(field, label, value=None):
            query = self.data.copy()
            query.pop("page", None)
            if field == "state":
                query.setlist(field, [state for state in values[field] if state != value])
            else:
                query.pop(field, None)
            chips.append({"label": label, "query": query.urlencode()})

        if values["q"]:
            add("q", values["q"])
        for state in values["state"]:
            add("state", state, state)
        if values["ownership"]:
            add("ownership", Institution.Ownership(values["ownership"]).label)
        for field, label in (("tuition_max", "Tuition ≤ ${:,}"), ("size_min", "Students ≥ {:,}"),
                             ("size_max", "Students ≤ {:,}")):
            if values[field] is not None:
                add(field, label.format(values[field]))
        return chips


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
    if form.is_valid():
        lookups = {"q": "name__icontains", "state": "state__in", "ownership": "ownership",
                   "tuition_max": "tuition_in_state__lte", "size_min": "enrollment_undergrad__gte",
                   "size_max": "enrollment_undergrad__lte"}
        schools = schools.filter(**{lookup: form.cleaned_data[key] for key, lookup in lookups.items()
                                    if form.cleaned_data[key] not in (None, "", [])})
    else:
        schools = schools.none()
    schools = with_saved_item(schools, request.user)
    page = Paginator(schools.order_by("name", "unitid"), 25).get_page(request.GET.get("page"))
    return render(request, "core/colleges.html", {"form": form, "page": page, "demo": demo})


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

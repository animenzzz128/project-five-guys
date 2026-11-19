// Keep the fields accessible without JavaScript. On phones, start with the
// results in view and keep validation errors expanded.
const filterPanel = document.querySelector(".filter-panel");
if (filterPanel && !filterPanel.hasAttribute("data-has-errors")) {
  const mobile = window.matchMedia("(max-width: 700px)");
  filterPanel.open = !mobile.matches;
  mobile.addEventListener("change", event => { filterPanel.open = !event.matches; });
}

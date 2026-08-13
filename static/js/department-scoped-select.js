/**
 * Filters a department-scoped <select> (e.g. Programme) down to the
 * options belonging to whichever Department is currently chosen in a
 * sibling <select name="department">, on any form carrying both.
 *
 * Options are pre-tagged with data-department="<id>" server-side (see
 * apps.core.forms.DepartmentScopedSelect) - this script only toggles
 * their visibility/availability and resets the scoped field if its
 * current value no longer belongs to the selected department.
 */
(function () {
  function filterScopedSelect(departmentSelect, scopedSelect) {
    var departmentId = departmentSelect.value;
    var previousValue = scopedSelect.value;
    var hasVisibleSelection = false;

    Array.prototype.forEach.call(scopedSelect.options, function (option) {
      if (!option.value) {
        option.hidden = false;
        option.disabled = false;
        return;
      }
      var belongs = !departmentId || option.dataset.department === departmentId;
      option.hidden = !belongs;
      option.disabled = !belongs;
      if (belongs && option.value === previousValue) {
        hasVisibleSelection = true;
      }
    });

    if (!hasVisibleSelection) {
      scopedSelect.value = '';
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('select[data-scoped-by]').forEach(function (scopedSelect) {
      var departmentSelect = document.querySelector(
        'select[name="' + scopedSelect.dataset.scopedBy + '"]'
      );
      if (!departmentSelect) return;

      filterScopedSelect(departmentSelect, scopedSelect);
      departmentSelect.addEventListener('change', function () {
        filterScopedSelect(departmentSelect, scopedSelect);
      });
    });
  });
})();

/**
 * Programme -> Academic Session dropdowns on the Semester form.
 *
 * The Session <select> stays disabled until a Programme is chosen. Picking
 * (or changing) the Programme reloads the Session options from the server
 * - only sessions that apply to that programme - and resets the selection.
 * The server validates the pair again on save; this is only convenience.
 */
(function () {
  document.addEventListener('DOMContentLoaded', function () {
    var programme = document.querySelector('select[data-sessions-url]');
    if (!programme) return;
    var session = document.querySelector('select[name="' + programme.dataset.sessionTarget + '"]');
    if (!session) return;

    function reset(options) {
      session.innerHTML = '';
      var blank = document.createElement('option');
      blank.value = '';
      blank.textContent = '--------- Select a session ---------';
      session.appendChild(blank);
      options.forEach(function (item) {
        var option = document.createElement('option');
        option.value = item.value;
        option.textContent = item.label;
        session.appendChild(option);
      });
      session.value = '';
    }

    function load() {
      if (!programme.value) {
        reset([]);
        session.disabled = true;
        return;
      }
      session.disabled = true;
      fetch(programme.dataset.sessionsUrl + '?programme=' + encodeURIComponent(programme.value), {
        credentials: 'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      })
        .then(function (response) { return response.json(); })
        .then(function (data) {
          reset(data.sessions || []);
          session.disabled = false;
        })
        .catch(function () { session.disabled = !programme.value; });
    }

    // The initial render keeps the server-chosen session (e.g. when editing).
    session.disabled = !programme.value;
    programme.addEventListener('change', load);
  });
})();

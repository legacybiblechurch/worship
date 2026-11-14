/* Legacy Bible Church · the back button goes back to where you came from.
 * A job page opens another page with ?from=stream (or slides, table, rotation).
 * This points that page's back button at the job page instead of Home. */
(function () {
  var m = /[?&]from=(stream|slides|table|rotation)(&|$)/.exec(location.search);
  if (!m) return;
  var to = { stream: ['jobs/stream/', 'Stream'], slides: ['jobs/slides/', 'Guide & Slides'], table: ['jobs/table/', 'Table'], rotation: ['rotation.html', 'Sunday Rotation'] }[m[1]];
  function go() {
    var a = document.querySelector('a.lbc-back');
    if (!a || !a.lastChild) return;
    a.href = to[0]; a.lastChild.nodeValue = to[1];
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', go); else go();
})();

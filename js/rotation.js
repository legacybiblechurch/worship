/* Legacy Bible Church · who is up which Sunday.
 * Reads window.LBC_ROTATION (js/rotation-data.js) and answers for any Sunday.
 *   LBCRotation.sunday(d)       the Sunday a date belongs to (Mon..Sun -> that week's coming Sunday)
 *   LBCRotation.at('2026-11-15') { date, slides, stream, table, off, note, changed }
 *   LBCRotation.JOBS            ['slides', 'stream', 'table']
 *   LBCRotation.list(from, n)   n Sundays from a date
 *   LBCRotation.label(date)     "Nov 16"
 * Dates are strings YYYY-MM-DD, counted in Los Angeles.
 */
(function (global) {
  'use strict';
  var TZ = 'America/Los_Angeles';
  var JOBS = ['slides', 'stream', 'table'];
  function cfg() { return global.LBC_ROTATION || { people: [], start: '2026-11-15', jobs: { slides: 0, stream: 1, table: 3 }, changes: {} }; }
  function parse(s) { var p = String(s).split('-'); return Date.UTC(+p[0], +p[1] - 1, +p[2]); }     // midnight UTC stands in for the calendar day
  function fmt(ms) { var d = new Date(ms); return d.getUTCFullYear() + '-' + ('0' + (d.getUTCMonth() + 1)).slice(-2) + '-' + ('0' + d.getUTCDate()).slice(-2); }
  function todayLA() { return new Intl.DateTimeFormat('en-CA', { timeZone: TZ }).format(new Date()); }
  // the Sunday this date counts toward: a Sunday is itself, any other day is the Sunday ahead
  function sunday(dateStr) {
    var ms = parse(dateStr || todayLA()), dow = new Date(ms).getUTCDay();
    return fmt(ms + (dow === 0 ? 0 : (7 - dow)) * 864e5);
  }
  function at(dateStr) {
    var c = cfg(), people = c.people || [], n = people.length, date = sunday(dateStr);
    var weeks = Math.round((parse(date) - parse(c.start)) / (7 * 864e5));
    var out = { date: date, slides: '', stream: '', table: '', off: false, note: '', changed: false }, jobs = c.jobs || {};
    if (n) {
      var i = ((weeks % n) + n) % n;
      JOBS.forEach(function (j) { out[j] = people[(i + (jobs[j] || 0)) % n]; });
    }
    var ch = (c.changes || {})[date];
    if (ch) {
      out.changed = true;
      if (ch.off) out.off = true;
      JOBS.forEach(function (j) { if (ch[j]) out[j] = ch[j]; });
      if (ch.note) out.note = ch.note;
    }
    return out;
  }
  function list(fromStr, count) {
    var first = sunday(fromStr), out = [];
    for (var k = 0; k < (count || 8); k++) out.push(at(fmt(parse(first) + k * 7 * 864e5)));
    return out;
  }
  function label(dateStr) {
    var d = new Date(parse(dateStr));
    return new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', month: 'short', day: 'numeric' }).format(d);
  }
  function longLabel(dateStr) {
    var d = new Date(parse(dateStr));
    return new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', weekday: 'long', month: 'long', day: 'numeric' }).format(d);
  }
  global.LBCRotation = { JOBS: JOBS, cfg: cfg, sunday: sunday, at: at, list: list, label: label, longLabel: longLabel, today: todayLA, TZ: TZ };
})(window);

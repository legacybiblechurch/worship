/**
 * LBCSheet — the one shared module behind Studio, Control and Display.
 *
 *   library()        the song library (js/songs-data.js)
 *   loadSongs(cb)    this Sunday's songs, in order, with lyrics + video
 *   buildSlides()    lyrics blocks -> congregation-sized slides (ONE implementation,
 *                    so what Studio previews is exactly what the TV shows)
 *   searchLibrary()  fuzzy title search for the "add a song" box
 *   textToBlocks / blocksToText   the plain-text lyric editor format
 *
 * Sunday morning depends on nothing outside this site: no Google, no API.
 * (The file keeps its old name so no page has to change its <script> tag.)
 */
(function (global) {
  'use strict';

  // songs-data.js declares LEGACY_SONGS with `const`, so it is NOT a property of
  // window. Every reader has to fall back to the bare identifier.
  function library() {
    if (typeof global.LEGACY_SONGS !== 'undefined') return global.LEGACY_SONGS;
    if (typeof LEGACY_SONGS !== 'undefined') return LEGACY_SONGS;
    return {};
  }
  function setlist() {
    return Array.isArray(global.WORSHIP_SETLIST) ? global.WORSHIP_SETLIST.slice() : [];
  }

  // ─────────────────────────────────────────── titles, slugs, search

  function slugify(s) {
    return String(s || '').toLowerCase().normalize('NFKD')
      .replace(/&rsquo;|&#39;|&apos;|['’]/g, '').replace(/&amp;|&/g, 'and')
      .replace(/[^\w\s-]/g, '').replace(/[\s_-]+/g, '-').replace(/^-+|-+$/g, '');
  }
  function normTitle(s) {
    return String(s || '').toLowerCase().replace(/&[a-z]+;/g, ' ').replace(/[^a-z0-9 ]/g, '')
      .replace(/\s+/g, ' ').trim();
  }
  function decodeEntities(s) {
    return String(s || '').replace(/&rsquo;|&#39;|&apos;/g, "'").replace(/&amp;/g, '&')
      .replace(/&ldquo;|&rdquo;/g, '"').replace(/&mdash;/g, '—').replace(/&ndash;/g, '–');
  }
  function titleOf(slug) {
    var L = library();
    return decodeEntities((L[slug] && L[slug].title) || slug);
  }

  // exact slug -> exact title -> prefix / contains -> slugified guess
  function resolveSlug(text) {
    var L = library(), guess = slugify(text);
    if (L[guess]) return guess;
    var q = normTitle(text), best = null;
    for (var slug in L) {
      var t = normTitle(L[slug].title || slug);
      if (t === q) return slug;
      if (q && (t.indexOf(q) === 0 || t.indexOf(' ' + q) !== -1 || q.indexOf(t) === 0)) {
        if (!best || t.length < normTitle(L[best].title || best).length) best = slug;
      }
    }
    return best || guess;
  }

  // Ranked matches for a partial title. Word-prefix matches first, then
  // contains, then a loose "all the typed letters appear in order" match that
  // survives a misspelling or two.
  function searchLibrary(query, limit) {
    var L = library(), q = normTitle(query);
    limit = limit || 8;
    if (!q) return [];
    var qWords = q.split(' '), out = [];
    for (var slug in L) {
      var t = normTitle(L[slug].title || slug), score = 0;
      if (t === q) score = 100;
      else if (t.indexOf(q) === 0) score = 90;
      else if (qWords.every(function (w) { return t.split(' ').some(function (tw) { return tw.indexOf(w) === 0; }); })) score = 80;
      else if (t.indexOf(q) !== -1) score = 70;
      else if (subsequence(q.replace(/ /g, ''), t.replace(/ /g, ''))) score = 30;
      if (score) out.push({ slug: slug, title: titleOf(slug), score: score - t.length / 200 });
    }
    return out.sort(function (a, b) { return b.score - a.score; }).slice(0, limit);
  }
  function subsequence(needle, hay) {
    var i = 0;
    for (var j = 0; j < hay.length && i < needle.length; j++) if (hay[j] === needle[i]) i++;
    return i === needle.length && needle.length >= 4;
  }

  function videoId(url) {
    var s = String(url || '').trim();
    var m = s.match(/(?:v=|\/shorts\/|youtu\.be\/|\/embed\/|\/live\/)([A-Za-z0-9_-]{11})/);
    if (m) return m[1];
    return /^[A-Za-z0-9_-]{11}$/.test(s) ? s : '';
  }

  // ─────────────────────────────────────────── this Sunday

  // resolve([{ slug, title, lyrics:[{label,lines}]|null, youtube, ready }])
  // Order is the setlist order. A song that has somehow lost its lyrics still
  // appears (ready:false) so the operator sees the gap instead of a missing song.
  function loadSongs(resolve) {
    var L = library();
    // always async, even though the data is local: callers set up their page
    // after calling this, and a synchronous callback would run before that
    setTimeout(function () { resolve(build()); }, 0);
    function build() { return setlist().map(function (s) {
      var d = L[s];
      var ok = !!(d && d.lyrics && d.lyrics.length);
      return {
        slug: s,
        title: titleOf(s),
        lyrics: ok ? d.lyrics : null,
        youtube: (d && d.youtube && videoId(d.youtube)) ? d.youtube : '',
        ready: ok
      };
    }); }
  }

  // ─────────────────────────────────────────── slides

  // A line the drafting step left too long is split at a natural break -
  // comma first, then a conjunction - never leaving a 1-2 word orphan.
  // Same words, never reordered or dropped.
  var BREAKS = [' and ', ' so ', ' but ', ' yet ', ' where ', ' when ', ' while ',
                ' though ', ' for ', ' to ', ' O '];
  function words(s) { return String(s).trim().split(/\s+/).filter(Boolean).length; }
  function splitLine(line, limit) {
    limit = limit || 48;
    line = String(line);
    if (line.length <= limit || words(line) <= 6) return [line];
    var mid = line.length / 2, best = -1, bestD = 1e9, m, re, at, d;
    re = /[,;:]\s+/g;
    while ((m = re.exec(line))) {
      at = m.index + 1;
      d = Math.abs(at - mid);
      if (words(line.slice(0, at)) >= 3 && words(line.slice(at)) >= 3 && d < bestD) { bestD = d; best = at; }
    }
    if (best < 0) {
      for (var bi = 0; bi < BREAKS.length; bi++) {
        var from = 4, low = line.toLowerCase();
        while ((at = low.indexOf(BREAKS[bi], from)) !== -1) {
          from = at + 1;
          if (words(line.slice(0, at)) < 3 || words(line.slice(at)) < 3) continue;
          d = Math.abs(at - mid);
          if (d < bestD) { bestD = d; best = at; }
        }
      }
    }
    if (best < 0) return [line];
    return splitLine(line.slice(0, best).replace(/[,;:]\s*$/, '').trim(), limit)
      .concat(splitLine(line.slice(best).replace(/^[,;:]\s*/, '').trim(), limit));
  }
  function tidyBlocks(blocks) {
    return (blocks || []).map(function (bl) {
      var out = [];
      (bl.lines || []).forEach(function (l) {
        if (String(l).trim()) out = out.concat(splitLine(String(l).trim()));
      });
      return { label: bl.label || '', lines: out };
    });
  }

  // How many lines fit comfortably depends on how long they are: hymn stanzas
  // (short lines) take four, contemporary songs (long lines) take two.
  function perSlide(lines) {
    var avg = lines.join(' ').length / Math.max(lines.length, 1);
    return avg > 38 ? 2 : avg > 27 ? 3 : 4;
  }

  // Split a block of N lines into the fewest slides that respect the cap, sized
  // as evenly as possible - so 5 lines become 3 + 2, never 4 + a lonely 1.
  function chunkEven(lines, cap) {
    var n = lines.length;
    if (n <= cap) return [lines];
    var count = Math.ceil(n / cap);
    // a slide one line over the cap beats a slide with a single orphaned line
    while (count > 1 && Math.floor(n / count) < 2) count--;
    var base = Math.floor(n / count), extra = n % count, out = [], i = 0;
    for (var k = 0; k < count; k++) {
      var size = base + (k < extra ? 1 : 0);
      out.push(lines.slice(i, i + size));
      i += size;
    }
    return out;
  }

  // lyrics blocks -> [{ label, lines }] slides. The single source of truth.
  function buildSlides(lyrics) {
    var slides = [];
    tidyBlocks(lyrics).forEach(function (block) {
      if (!block.lines.length) return;
      chunkEven(block.lines, perSlide(block.lines)).forEach(function (chunk) {
        slides.push({ label: block.label, lines: chunk });
      });
    });
    return slides;
  }

  // ─────────────────────────────────────────── the editor's plain-text format
  // A blank line starts a new slide. A line in [brackets] on its own names the
  // section (shown on Control only, never on the TV).

  function blocksToText(lyrics) {
    return (lyrics || []).map(function (b) {
      return (b.label ? '[' + b.label + ']\n' : '') + (b.lines || []).join('\n');
    }).join('\n\n');
  }
  function textToBlocks(text) {
    return String(text || '').replace(/\r/g, '').split(/\n\s*\n/).map(function (chunk) {
      var lines = chunk.split('\n').map(function (l) { return l.trim(); }).filter(Boolean);
      if (!lines.length) return null;
      var label = '', m = lines[0].match(/^\[(.*)\]$/);
      if (m) { label = m[1].trim(); lines = lines.slice(1); }
      if (!lines.length) return null;
      return { label: label, lines: lines };
    }).filter(Boolean);
  }

  global.LBCSheet = {
    library: library, setlist: setlist, titleOf: titleOf, decodeEntities: decodeEntities,
    slugify: slugify, resolveSlug: resolveSlug, searchLibrary: searchLibrary, videoId: videoId,
    loadSongs: loadSongs,
    buildSlides: buildSlides, splitLine: splitLine, tidyBlocks: tidyBlocks,
    blocksToText: blocksToText, textToBlocks: textToBlocks
  };
})(window);

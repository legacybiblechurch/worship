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

  // ─────────────────────────────────────────── the order of service
  // js/worship-service.js (written by the Studio) holds the whole Sunday in
  // order: songs, readings, the sermon, the Lord's Table, videos, the logo.
  // An older set that only has songs (WORSHIP_SETLIST) still works.
  function service() {
    if (Array.isArray(global.WORSHIP_SERVICE)) return global.WORSHIP_SERVICE.map(function (it) { return JSON.parse(JSON.stringify(it)); });
    return setlist().map(function (s) { return { type: 'song', slug: s }; });
  }
  // words written once and kept (the Lord's Table…), published alongside the service
  function saved() { return global.WORSHIP_SAVED && typeof global.WORSHIP_SAVED === 'object' ? global.WORSHIP_SAVED : {}; }

  var TYPE_NAMES = { song: 'Song', scripture: 'Reading', sermon: 'Sermon', words: 'Words', video: 'Video', logo: 'Logo' };
  function itemTitle(it) {
    switch (it.type) {
      case 'song': return titleOf(it.slug);
      case 'scripture': return it.ref || 'Scripture reading';
      case 'sermon': return it.title || 'Sermon';
      case 'words': var w = saved()[it.id]; return (w && w.title) || it.id || 'Words';
      case 'video': return it.title || 'Video';
      case 'logo': return it.title || 'Logo';
    }
    return it.type || '';
  }

  // verses -> slides: a few verses per slide, numbered, long verses split at
  // natural breaks like lyrics. The reference and version become the small
  // gold line above the words, so the congregation always knows where it is.
  function buildScriptureSlides(it) {
    var verses = (it.verses || []).filter(function (v) { return v && String(v.text || '').trim(); });
    if (!verses.length) return [];
    var base = String(it.ref || '').replace(/:\s*[\d\s,–-]+$/, '').trim();
    var slides = [], cur = [], nums = [], chars = 0;
    function flush() {
      if (!cur.length) return;
      var a = nums[0], b = nums[nums.length - 1], range = a === b ? String(a) : a + '-' + b;
      slides.push({ label: 'v. ' + range, kicker: (base ? base + ':' + range : 'v. ' + range) + (it.version ? ' · ' + it.version : ''), lines: cur });
      cur = []; nums = []; chars = 0;
    }
    verses.forEach(function (v) {
      var txt = String(v.text).replace(/\s+/g, ' ').trim();
      var parts = splitLine(txt, 56);
      parts[0] = v.n + '  ' + parts[0];
      if (cur.length && (chars + txt.length > 230 || cur.length + parts.length > 5)) flush();
      cur = cur.concat(parts); nums.push(v.n); chars += txt.length;
    });
    flush();
    return slides;
  }
  // sermon -> a title slide, then one slide per point, the title riding above each
  function buildSermonSlides(it) {
    var slides = [{ label: 'Title', kicker: it.passage || 'Sermon', lines: [it.title || 'Sermon'] }];
    (it.points || []).forEach(function (p, i) {
      if (String(p).trim()) slides.push({ label: 'Point ' + (i + 1), kicker: it.title || '', lines: splitLine(String(p).trim(), 56) });
    });
    return slides;
  }

  // one item of the service, with its slides. The ONE place every page agrees on
  // what a reading, a sermon point or a video cue looks like.
  function buildItem(it) {
    var out = { type: it.type, title: itemTitle(it), ready: true, youtube: '', slides: [] };
    if (it.type === 'song') {
      var d = library()[it.slug];
      out.slug = it.slug;
      out.ready = !!(d && d.lyrics && d.lyrics.length);
      out.youtube = (d && d.youtube && videoId(d.youtube)) ? d.youtube : '';
      out.slides = out.ready ? buildSlides(d.lyrics) : [{ label: '', lines: ['No words yet. Open Studio to fix this song'] }];
    } else if (it.type === 'scripture') {
      out.slides = buildScriptureSlides(it);
      out.ready = out.slides.length > 0;
      if (!out.ready) out.slides = [{ label: '', kicker: it.ref || '', lines: ['No passage yet. Open Studio'] }];
    } else if (it.type === 'sermon') {
      out.slides = buildSermonSlides(it);
      out.ready = !!(it.title && String(it.title).trim());
    } else if (it.type === 'words') {
      var w = saved()[it.id];
      out.ready = !!(w && w.lyrics && w.lyrics.length);
      out.slides = out.ready ? buildSlides(w.lyrics) : [{ label: '', lines: ['No words yet. Open Studio'] }];
    } else if (it.type === 'video') {
      out.slides = [{ label: 'Video', lines: [], logo: true, cue: 'Play “' + (it.title || 'the video') + '” on the TV' + (it.note ? '. ' + it.note : '') }];
    } else {
      out.slides = [{ label: 'Logo', lines: [], logo: true, cue: 'The TV shows the church logo' }];
    }
    return out;
  }
  // the whole service, each item with its slides, in order (async like loadSongs)
  function loadService(resolve) {
    setTimeout(function () { resolve(service().map(buildItem)); }, 0);
  }

  // the reading editor's plain-text format: one verse per line, its number first
  function versesToText(verses) {
    return (verses || []).map(function (v) { return v.n + ' ' + String(v.text || '').replace(/\s+/g, ' ').trim(); }).join('\n');
  }
  function textToVerses(text) {
    var n = 0, out = [];
    String(text || '').replace(/\r/g, '').split('\n').forEach(function (line) {
      var s = line.trim(); if (!s) return;
      var m = s.match(/^(\d+)[.:)]?\s+(.*)$/);
      if (m) { n = +m[1]; s = m[2]; } else n++;
      if (s) out.push({ n: n, text: s });
    });
    return out;
  }
  // a passage from bible-api.com: free, no key, public-domain texts (WEB, KJV).
  // Licensed texts (the NASB) come from API.Bible with the church's key, below.
  function fetchPassage(ref, translation) {
    var t = String(translation || 'web').toLowerCase();
    return fetch('https://bible-api.com/' + encodeURIComponent(String(ref).trim()) + '?translation=' + encodeURIComponent(t))
      .then(function (r) {
        if (!r.ok) throw new Error(r.status === 404 ? 'That reference was not found. Try it like “Psalm 24” or “John 3:16-21”.' : 'The Bible service did not answer (' + r.status + '). Try again in a moment.');
        return r.json();
      })
      .then(function (j) {
        return { ref: j.reference || ref, version: String(j.translation_id || t).toUpperCase(),
                 verses: (j.verses || []).map(function (v) { return { n: v.verse, text: String(v.text || '').replace(/\s+/g, ' ').trim() }; }) };
      });
  }

  // ── Scripture from API.Bible, for the texts bible-api.com cannot serve.
  // Needs the church's API.Bible key (the Studio keeps it in this browser only).
  // A reference like "Psalm 24" or "1 John 3:16-18" becomes a passage id like
  // PSA.24 or 1JN.3.16-1JN.3.18. Book names: the full name first, then the
  // short forms people type; matching ignores spaces, dots and case.
  var BIBLE_API = 'https://rest.api.bible/v1';
  var BOOKS = ('GEN genesis gen ge gn|EXO exodus exo ex exod|LEV leviticus lev le lv|NUM numbers num nu nm nb|DEU deuteronomy deut deu de dt|' +
    'JOS joshua josh jos jsh|JDG judges judg jdg jg jdgs|RUT ruth rut ru rth|1SA 1samuel 1sam 1sa 1sm|2SA 2samuel 2sam 2sa 2sm|' +
    '1KI 1kings 1kgs 1ki 1kin|2KI 2kings 2kgs 2ki 2kin|1CH 1chronicles 1chron 1chr 1ch|2CH 2chronicles 2chron 2chr 2ch|EZR ezra ezr|' +
    'NEH nehemiah neh ne|EST esther est es esth|JOB job jb|PSA psalms psalm ps psa pss psm pslm|PRO proverbs prov pro pr prv|' +
    'ECC ecclesiastes eccl ecc ec eccles qoh|SNG songofsolomon songofsongs song sos so canticles cant sng|ISA isaiah isa is|JER jeremiah jer je jr|' +
    'LAM lamentations lam la|EZK ezekiel ezek eze ezk|DAN daniel dan da dn|HOS hosea hos ho|JOL joel jol jl|AMO amos amo am|OBA obadiah obad oba ob|' +
    'JON jonah jon jnh|MIC micah mic mc|NAM nahum nah na nam|HAB habakkuk hab hb|ZEP zephaniah zeph zep zp|HAG haggai hag hg|' +
    'ZEC zechariah zech zec zc|MAL malachi mal ml|MAT matthew matt mat mt|MRK mark mrk mk mr|LUK luke luk lk|JHN john jhn jn joh|' +
    'ACT acts act ac|ROM romans rom ro rm|1CO 1corinthians 1cor 1co|2CO 2corinthians 2cor 2co|GAL galatians gal ga|EPH ephesians eph ep|' +
    'PHP philippians phil php philip pp|COL colossians col co|1TH 1thessalonians 1thess 1thes 1th|2TH 2thessalonians 2thess 2thes 2th|' +
    '1TI 1timothy 1tim 1ti|2TI 2timothy 2tim 2ti|TIT titus tit ti|PHM philemon philem phm phlm pm|HEB hebrews heb he|JAS james jas jm ja|' +
    '1PE 1peter 1pet 1pe 1pt|2PE 2peter 2pet 2pe 2pt|1JN 1john 1jn 1jhn 1jo|2JN 2john 2jn 2jhn 2jo|3JN 3john 3jn 3jhn 3jo|JUD jude jud jd|' +
    'REV revelation revelations rev re apocalypse').split('|').map(function (s) { var p = s.split(' '); return { id: p[0], names: p.slice(1) }; });
  function parseRef(ref) {
    var s = String(ref || '').trim().replace(/[–—]/g, '-')
      .replace(/^(first|1st|i)\s+/i, '1 ').replace(/^(second|2nd|ii)\s+/i, '2 ').replace(/^(third|3rd|iii)\s+/i, '3 ');
    var m = s.match(/^([1-3]?\s*[a-z][a-z .]*?)\s*(\d+)(?::(\d+))?(?:\s*-\s*(?:(\d+):)?(\d+))?$/i);
    if (!m) return null;
    var key = m[1].toLowerCase().replace(/[^a-z0-9]/g, ''), book = null, starts = [];
    for (var i = 0; i < BOOKS.length && !book; i++) {
      if (BOOKS[i].names.indexOf(key) >= 0) book = BOOKS[i];
      else if (BOOKS[i].names[0].indexOf(key) === 0) starts.push(BOOKS[i]);
    }
    if (!book && starts.length === 1) book = starts[0];
    if (!book) return null;
    var ch = +m[2], v1 = m[3] ? +m[3] : 0, ch2 = m[4] ? +m[4] : ch, v2 = m[5] ? +m[5] : 0, id = book.id + '.' + ch;
    if (v1) { id += '.' + v1; if (v2) id += '-' + book.id + '.' + ch2 + '.' + v2; }
    else if (v2) id += '-' + book.id + '.' + v2;   // "Psalm 1-3" is chapters
    return { bookId: book.id, chapter: ch, verse: v1, id: id };
  }
  function bibleCall(path, key) {
    return fetch(BIBLE_API + path, { headers: { 'api-key': key } }).then(function (r) {
      if (r.status === 401 || r.status === 403) throw new Error('That API.Bible key did not work. Check it on api.bible and paste it again.');
      if (r.status === 404) throw new Error('That reference was not found. Try it like “Psalm 24” or “John 3:16-21”.');
      if (!r.ok) throw new Error('API.Bible did not answer (' + r.status + '). Try again in a moment.');
      return r.json();
    });
  }
  // the English Bibles this key may read: [{id, abbr, name}]
  function bibleList(key) {
    return bibleCall('/bibles?language=eng', key).then(function (j) {
      var seen = {};
      return (j.data || []).map(function (b) {
        // the label people see: API.Bible says NASB1995, the church says NASB
        return { id: b.id, abbr: String(b.abbreviation || '').replace(/^eng/, '').toUpperCase().replace(/^NASB1995$/, 'NASB'), name: b.name };
      }).filter(function (b) { if (!b.abbr || seen[b.abbr]) return false; seen[b.abbr] = true; return true; });
    });
  }
  // the same shape fetchPassage gives, from API.Bible: {ref, version, verses}
  function fetchPassageBible(ref, bible, key) {
    var p = parseRef(ref);
    if (!p) return Promise.reject(new Error('Write the reference like “Psalm 24” or “John 3:16-21”.'));
    return bibleCall('/bibles/' + bible.id + '/passages/' + p.id + '?content-type=text&include-verse-numbers=true', key)
      .then(function (j) {
        var d = j.data || {}, text = String(d.content || ''), verses = [], re = /\[(\d+)\]\s*([^\[]*)/g, m;
        while ((m = re.exec(text))) { var t = m[2].replace(/\s+/g, ' ').trim(); if (t) verses.push({ n: +m[1], text: t }); }
        if (!verses.length && text.trim()) verses.push({ n: p.verse || 1, text: text.replace(/\s+/g, ' ').trim() });
        // API.Bible asks that each fetched passage register once (their FUMS pixel)
        var pix = j.meta && j.meta.fumsNoScript && String(j.meta.fumsNoScript).match(/src="([^"]+)"/);
        if (pix) { var im = new Image(); im.src = pix[1]; }
        return { ref: String(d.reference || ref).replace(/^Psalms\b/, 'Psalm'), version: bible.abbr, verses: verses };
      });
  }

  // The church's one room code. Control publishes each slide change to the
  // relay under this code, and the phone remote and the livestream lyrics
  // listen to it, so none of them needs a code typed in. Change it here if it
  // ever has to change, and every page follows.
  var ROOM = '8BSWX2H4DF';

  global.LBCSheet = {
    ROOM: ROOM,
    library: library, setlist: setlist, titleOf: titleOf, decodeEntities: decodeEntities,
    slugify: slugify, resolveSlug: resolveSlug, searchLibrary: searchLibrary, videoId: videoId,
    loadSongs: loadSongs,
    service: service, saved: saved, TYPE_NAMES: TYPE_NAMES, itemTitle: itemTitle,
    buildItem: buildItem, loadService: loadService,
    buildScriptureSlides: buildScriptureSlides, buildSermonSlides: buildSermonSlides,
    versesToText: versesToText, textToVerses: textToVerses, fetchPassage: fetchPassage,
    parseRef: parseRef, bibleList: bibleList, fetchPassageBible: fetchPassageBible,
    buildSlides: buildSlides, splitLine: splitLine, tidyBlocks: tidyBlocks,
    blocksToText: blocksToText, textToBlocks: textToBlocks
  };
})(window);

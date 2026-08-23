/* terminal-daily-bench — the data layer and the day rail's replacement.
   -------------------------------------------------------------------------
   Loaded AFTER assets/site.js, which owns the shell. This file owns:

     * dataUrl / getData  — one way to name a data file, from the site root
     * dayIndex / dayData — the daily rotation, one file per day
     * dayNav             — prev / next / jump, replacing the card rail
     * sortTable          — click-to-sort table headers
     * esc, TH/TD/TR      — the bits every page had its own copy of

   WHY A SECOND FILE rather than more of site.js: the shell is stable and this
   is the part that changes when the data does. Keeping them apart means a data
   change cannot break the header.
   ------------------------------------------------------------------------- */
(function () {
  "use strict";

  var T = window.TDB || {};
  var ROOT = T.ROOT || ".";

  /* ======================================================================
     paths
     ====================================================================== */

  /* Every data path is written FROM THE SITE ROOT, never relative to the page.
     This exists because the old convention was page-relative and two pages got
     it wrong in a way nothing caught: leaderboard/index.html asked for
     "../site_data.json" while its data-root was already "..", so the fetch
     resolved ABOVE the site root, 404'd, was swallowed by a .catch(->null), and
     the page rendered its empty state. An empty page and a broken path looked
     identical.

     So: a path that starts with "../" or "/" cannot be right, and this says so
     loudly instead of fetching nothing. */
  function dataUrl(path) {
    var p = String(path || "");
    if (p.charAt(0) === "/" || p.slice(0, 3) === "../") {
      throw new Error(
        "TDB.dataUrl: '" + p + "' is not site-root-relative. Data paths are " +
        "written from the site root (\"data/index.json\"), never from the page. " +
        "The page's own depth is already in data-root."
      );
    }
    return ROOT + "/" + p;
  }

  /* Fetch JSON, and REPORT a failure rather than resolving to null. A caller
     that genuinely wants to continue without the data catches it and says so on
     the page; what must not happen is a fetch failure quietly becoming the same
     screen as an empty dataset. */
  function getData(path) {
    return fetch(dataUrl(path), { cache: "no-store" }).then(function (r) {
      if (!r.ok) throw new Error(path + ": HTTP " + r.status);
      return r.json();
    });
  }

  /* ======================================================================
     the daily rotation
     ====================================================================== */

  /* One small index plus one file per day. Publishing day N+1 writes ONE new
     file and appends ONE id to the index -- no other file is rewritten and no
     page is regenerated, which is the whole point: the site changes when the
     data does. It also means a reader downloads one day, not the archive. */
  var INDEX_PATH = "data/index.json";
  function dayPath(id) { return "data/days/" + encodeURIComponent(id) + ".json"; }

  function dayIndex() {
    return getData(INDEX_PATH).then(function (idx) {
      var days = (idx && Array.isArray(idx.days) ? idx.days : []).slice();
      /* Newest first, and always sorted here rather than trusting the file:
         an index appended to by hand will eventually be out of order. */
      days.sort().reverse();
      idx.days = days;
      idx.latest = days[0] || null;
      return idx;
    });
  }

  function dayData(id) { return getData(dayPath(id)); }

  /* ======================================================================
     day navigation — arrows, not a wall of cards
     ====================================================================== */

  /* The rail this replaces rendered every published day as a card, which is
     fine at four days and unreadable at a year of them. Arrows step one day;
     the select in the middle jumps anywhere without paging through. The date
     also lives in the URL (?d=YYYY-MM-DD) so a particular day is linkable and
     the browser's back button works. */
  function dayNav(el, opts) {
    if (!el) return;
    var days = (opts && opts.days) || [];
    var active = (opts && opts.active) || days[0];
    var onChange = (opts && opts.onChange) || function () {};
    if (!days.length) {
      el.innerHTML = '<p class="text-muted-foreground font-mono text-sm">no published days</p>';
      return;
    }
    var i = days.indexOf(active);
    if (i < 0) i = 0;

    /* days[] is newest-first, so "newer" walks toward index 0. */
    var newer = i > 0 ? days[i - 1] : null;
    var older = i < days.length - 1 ? days[i + 1] : null;

    function arrow(dir, target, label) {
      var dis = target ? "" : " disabled";
      return '<button type="button" class="tdb-daynav-arrow" data-dir="' + dir + '"' + dis +
        ' aria-label="' + label + '" title="' + label + '">' +
        (dir === "older" ? "&#8249;" : "&#8250;") + "</button>";
    }

    el.innerHTML =
      '<div class="tdb-daynav" role="group" aria-label="Published day">' +
        arrow("older", older, "Older day") +
        '<label class="tdb-daynav-label">' +
          '<span class="sr-only">Choose a published day</span>' +
          '<select class="tdb-daynav-select" aria-label="Published day">' +
            days.map(function (d) {
              return '<option value="' + d + '"' + (d === active ? " selected" : "") +
                ">" + d + "</option>";
            }).join("") +
          "</select>" +
        "</label>" +
        arrow("newer", newer, "Newer day") +
        '<span class="tdb-daynav-pos">' + (i + 1) + " / " + days.length + "</span>" +
      "</div>";

    function go(id) {
      if (!id || id === active) return;
      try {
        var u = new URL(window.location.href);
        u.searchParams.set("d", id);
        window.history.pushState({ d: id }, "", u);
      } catch (e) { /* file:// has no URL API for this; navigation still works */ }
      onChange(id);
    }

    el.querySelectorAll(".tdb-daynav-arrow").forEach(function (b) {
      b.addEventListener("click", function () {
        go(b.getAttribute("data-dir") === "older" ? older : newer);
      });
    });
    el.querySelector(".tdb-daynav-select").addEventListener("change", function (e) {
      go(e.target.value);
    });
  }

  /* The day the URL asks for, if any. */
  function dayFromUrl() {
    try {
      return new URL(window.location.href).searchParams.get("d");
    } catch (e) { return null; }
  }

  /* ======================================================================
     tables
     ====================================================================== */

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  var TH =
    "text-foreground h-10 px-2 text-left align-middle font-medium whitespace-nowrap py-3 text-sm";
  var TD = "p-2 align-middle whitespace-nowrap py-3 text-sm";
  var TR = "hover:bg-muted/50 border-b transition-colors";

  /* Click a header to sort by it; click again to reverse. The arrow is drawn on
     the active column only, so the table always says which order it is in --
     a sorted table that does not show its key is a table you cannot trust. */
  function sortTable(opts) {
    var head = opts.head, body = opts.body, cols = opts.cols;
    var rows = opts.rows, render = opts.render;
    var key = opts.sort || (cols[0] && cols[0].key);
    var dir = opts.dir || "desc";

    function draw() {
      head.innerHTML = '<tr class="' + TR + '">' + cols.map(function (c) {
        var on = c.key === key;
        var caret = on ? (dir === "asc" ? " ▲" : " ▼") : "";
        var align = c.right ? ' style="text-align:right"' : "";
        if (c.sortable === false) {
          /* A non-sortable header still has to LOOK like a header. Bare text
             here rendered "Rank" in dark mixed case beside seven uppercase
             muted labels, so the one column you cannot sort was also the one
             that looked like it was shouting. */
          return '<th class="' + TH + '"' + align + '><span class="tdb-sort" ' +
            'data-static="true">' + esc(c.label) + "</span></th>";
        }
        return '<th class="' + TH + '"' + align + '>' +
          '<button type="button" class="tdb-sort" data-key="' + c.key + '"' +
          (on ? ' data-active="true"' : "") +
          ' aria-label="Sort by ' + esc(c.label) + '">' +
          esc(c.label) + caret + "</button></th>";
      }).join("") + "</tr>";

      var col = cols.filter(function (c) { return c.key === key; })[0] || cols[0];
      var get = col.value || function (r) { return r[col.key]; };
      var sorted = rows.slice().sort(function (a, b) {
        var av = get(a), bv = get(b);
        /* Missing values sink, in BOTH directions: a model with no result for
           this scaffold has not tied for last, it has not been measured. */
        var an = (av == null || av === ""), bn = (bv == null || bv === "");
        if (an !== bn) return an ? 1 : -1;
        if (an && bn) return 0;
        if (typeof av === "number" && typeof bv === "number") {
          return dir === "asc" ? av - bv : bv - av;
        }
        av = String(av); bv = String(bv);
        return dir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
      });
      body.innerHTML = sorted.map(render).join("");

      head.querySelectorAll(".tdb-sort").forEach(function (b) {
        b.addEventListener("click", function () {
          var k = b.getAttribute("data-key");
          if (k === key) { dir = (dir === "asc" ? "desc" : "asc"); }
          else { key = k; dir = "desc"; }
          draw();
        });
      });
    }
    draw();
    return { redraw: function (next) { rows = next || rows; draw(); } };
  }

  /* A visible failure. Called wherever a fetch could not complete, so the page
     says "this did not load" instead of "there is nothing here". */
  function loadError(el, what, err) {
    /* Always says something, even when the container it was handed is gone.
       Silently returning on a null element is how a real failure becomes a
       blank page: the caller thinks it reported, the reader sees nothing, and
       the console is clean because the throw was already caught. */
    console.error("[TDB] could not load " + what + ":", err);
    if (!el) {
      var host = document.querySelector("[data-tdb-canary-host]") || document.body;
      el = document.createElement("div");
      host.insertBefore(el, host.firstChild);
    }
    el.innerHTML =
      '<div class="tdb-loaderr border-y px-6 py-8">' +
        '<p class="font-medium">Could not load ' + esc(what) + ".</p>" +
        '<p class="text-muted-foreground mt-2 font-mono text-sm">' + esc(String(err)) + "</p>" +
        '<p class="text-muted-foreground mt-2 text-sm">This is a failure to read the ' +
          'data, not an empty result. The two are different and the page will not ' +
          'show one as the other.</p>' +
      "</div>";
  }

  window.TDB = Object.assign(T, {
    dataUrl: dataUrl,
    getData: getData,
    dayIndex: dayIndex,
    dayData: dayData,
    dayPath: dayPath,
    dayNav: dayNav,
    dayFromUrl: dayFromUrl,
    sortTable: sortTable,
    loadError: loadError,
    esc: esc,
    TH: TH, TD: TD, TR: TR
  });
})();

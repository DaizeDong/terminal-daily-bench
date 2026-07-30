/* terminal-daily-bench — shared site shell.
   Every page includes this with data-root pointing at the site root, e.g.
     <script src="../assets/site.js" data-root=".."></script>
   It injects the SAME nav + footer everywhere (one source of truth, so pages
   cannot drift), restores the theme, and exposes helpers on window.TDB. */
(function () {
  var self = document.currentScript;
  var ROOT = (self && self.dataset.root) || ".";
  var PAGE = (self && self.dataset.page) || "";

  /* ---- theme (respects the OS, remembers a manual choice) ---- */
  try {
    var saved = localStorage.getItem("tdb-theme");
    if (saved) document.documentElement.setAttribute("data-theme", saved);
  } catch (e) {}
  function toggleTheme() {
    var cur = document.documentElement.getAttribute("data-theme");
    if (!cur) {
      cur = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    }
    var next = cur === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("tdb-theme", next); } catch (e) {}
  }

  var NAV = [
    ["leaderboard", "leaderboard/"],
    ["benchmarks",  "benchmarks/"],
    ["tasks",       "registry/"],
    ["quality",     "quality/"],
    ["docs",        "guide/"],
    ["submit",      "submit/"]
  ];

  function mountShell() {
    var nav = document.createElement("header");
    nav.className = "nav";
    nav.innerHTML =
      '<div class="wrap">' +
        '<a class="brand" href="' + ROOT + '/">terminal<span class="dot">·</span>daily<span class="dot">-</span>bench</a>' +
        '<nav>' +
          NAV.map(function (n) {
            var cur = PAGE === n[0] ? ' aria-current="page"' : "";
            return '<a href="' + ROOT + "/" + n[1] + '"' + cur + ">" + n[0] + "</a>";
          }).join("") +
          '<a href="https://github.com/DaizeDong/terminal-daily-bench">github</a>' +
          '<button class="theme-btn" type="button" aria-label="Toggle colour theme">theme</button>' +
        "</nav>" +
      "</div>";
    document.body.insertBefore(nav, document.body.firstChild);
    nav.querySelector(".theme-btn").addEventListener("click", toggleTheme);

    var f = document.createElement("footer");
    f.innerHTML =
      '<div class="wrap"><div class="row">' +
        '<span class="seal" title="No model or LLM signal can gate an accept. A solve exists only if re-laid protected tests pass.">' +
          "<b>false_accept</b> 0</span>" +
        '<span>tasks mined from real merged pull requests, every day · scored by execution proof only</span>' +
        '<span class="sp"></span>' +
        '<a href="https://github.com/DaizeDong/terminal-daily-bench">github</a>' +
        '<a href="' + ROOT + '/guide/">docs</a>' +
        '<a href="' + ROOT + '/submit/">submit results</a>' +
      "</div></div>";
    document.body.appendChild(f);
  }

  /* ---- data ---- */
  function getJSON(path) {
    return fetch(ROOT + "/" + path, { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error(path + " " + r.status); return r.json(); });
  }

  /* ---- Wilson 95% interval: the honest way to show a rate at small N ---- */
  function wilson(solved, n, z) {
    z = z || 1.959964;
    if (!n) return { lo: 0, hi: 0, p: 0 };
    var p = solved / n, d = 1 + z * z / n;
    var c = (p + z * z / (2 * n)) / d;
    var m = (z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / d;
    return { lo: Math.max(0, c - m), hi: Math.min(1, c + m), p: p };
  }
  function pct(x) { return (x * 100).toFixed(1).replace(/\.0$/, "") + "%"; }

  function rateCell(o) {
    if (!o || !o.n) return '<span class="dash">—</span>';
    var w = wilson(o.solved != null ? o.solved : Math.round(o.rate * o.n), o.n);
    var lo = w.lo * 100, hi = w.hi * 100, p = w.p * 100;
    return '<div class="rate" title="' + pct(w.p) + "  95% CI [" + pct(w.lo) + ", " + pct(w.hi) + ']">' +
      '<span class="n">' + (o.solved != null ? o.solved : Math.round(o.rate * o.n)) + "/" + o.n + "</span>" +
      '<span class="bar"><i style="left:' + lo + "%;width:" + Math.max(1, hi - lo) + '%"></i>' +
      '<b style="left:calc(' + p + "% - 1px)" + '"></b></span>' +
      '<span class="pct">' + pct(w.p) + "</span></div>";
  }

  /* ---- the signature day rail: suites are date-versioned because we are living ---- */
  function dayRail(el, suites, activeId) {
    if (!el) return;
    if (!suites || !suites.length) { el.innerHTML = ""; return; }
    var cells = suites.map(function (s) {
      var on = s.id === activeId ? " on" : "";
      var href = ROOT + "/benchmarks/" + encodeURIComponent(s.id) + "/";
      return '<a class="day' + on + '" href="' + href + '" title="' + (s.status || "") + ' suite">' +
        '<span class="d">' + s.id + "</span>" +
        '<span class="n">' + (s.n_tasks != null ? s.n_tasks + " tasks" : "—") + "</span></a>";
    }).join("");
    el.innerHTML =
      '<div class="rail-wrap"><div class="rail-head">' +
        '<span class="t">daily suites — every day is its own sealed benchmark</span>' +
        '<span class="seal"><b>false_accept</b> 0</span>' +
      "</div><div class=\"rail\">" + cells + "</div></div>";
  }

  window.TDB = { ROOT: ROOT, getJSON: getJSON, wilson: wilson, pct: pct,
                 rateCell: rateCell, dayRail: dayRail };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mountShell);
  } else { mountShell(); }
})();

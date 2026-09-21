/* Dated catalogue changes and observed outcomes. No score is inferred from a missing cell. */
(function (root) {
  "use strict";
  var T = root.TDB = root.TDB || {};
  var scopes = ["new", "retained", "returned", "removed"];
  var scopeLabels = { new: "New tasks", retained: "Retained", returned: "Returning", removed: "Removed" };
  function cleanTaskTitle(text) {
    text = String(text || "").trim();
    text = text.replace(/^(?:fix|feat|perf|refactor|docs|test|chore|build|ci|style)(?:\([^)]*\))?!?:\s*/i, "");
    text = text.replace(/\([^()]*\[redacted-ref\][^()]*\)/gi, "");
    text = text.replace(/\[redacted[^\]]*\]/gi, "");
    text = text.replace(/\b[0-9a-f]{8,64}\b/gi, "").replace(/`/g, "");
    text = text.replace(/\(\s*\)/g, "").replace(/\s+([,;:)])/g, "$1");
    text = text.replace(/\s+/g, " ").replace(/^[ ,:;-]+|[ ,:;-]+$/g, "");
    return text ? text.charAt(0).toUpperCase() + text.slice(1) : "Software maintenance task";
  }
  function taskSuites(task) {
    var ids = (Array.isArray(task.suites) ? task.suites : []).concat(task.suite || []);
    (task.suite_memberships || []).forEach(function (membership) { ids.push(membership.suite); });
    return Array.from(new Set(ids.filter(function (id) { return typeof id === "string" && id; })));
  }
  function newestSuite(a, b) {
    var dated = /^\d{4}-\d{2}-\d{2}$/;
    return Number(dated.test(b)) - Number(dated.test(a)) || String(b).localeCompare(String(a));
  }
  function uniqueTaskCatalogue(site) {
    var tasks = new Map();
    ((site && site.tasks) || []).forEach(function (task) {
      if (!task.id) return;
      var ids = taskSuites(task), latest = ids.slice().sort(newestSuite)[0] || "";
      if (!tasks.has(task.id)) tasks.set(task.id, { source: task, latest: latest, suites: new Set(), memberships: new Map() });
      var entry = tasks.get(task.id);
      if (newestSuite(latest, entry.latest) < 0) { entry.source = task; entry.latest = latest; }
      ids.forEach(function (id) { entry.suites.add(id); });
      (task.suite_memberships || []).forEach(function (membership) {
        if (entry.suites.has(membership.suite)) entry.memberships.set(membership.suite,
          Object.assign({}, entry.memberships.get(membership.suite), membership));
      });
    });
    ((site && site.suites) || []).forEach(function (suite) {
      if (!suite.id) return;
      (suite.task_ids || []).forEach(function (id) { if (tasks.has(id)) tasks.get(id).suites.add(suite.id); });
    });
    return Array.from(tasks.values()).map(function (entry) {
      var ids = Array.from(entry.suites).sort();
      return Object.assign({}, entry.source, {
        suite: ids.slice().sort(newestSuite)[0] || "", suites: ids,
        suite_memberships: ids.map(function (id) { return entry.memberships.get(id) || { suite: id }; })
      });
    });
  }
  function releaseHistory(site) {
    var members = new Map(), seen = new Set(), previous = new Set(), previousDate = null;
    ((site && site.suites) || []).forEach(function (suite) {
      if (/^\d{4}-\d{2}-\d{2}$/.test(suite.id)) {
        if (!members.has(suite.id)) members.set(suite.id, new Set());
        (suite.task_ids || []).forEach(function (id) { if (typeof id === "string" && id) members.get(suite.id).add(id); });
      }
    });
    ((site && site.tasks) || []).forEach(function (task) {
      if (!task.id) return;
      taskSuites(task).forEach(function (id) {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(id)) return;
        if (!members.has(id)) members.set(id, new Set());
        members.get(id).add(task.id);
      });
    });
    return Array.from(members.keys()).sort().map(function (id) {
      var current = members.get(id);
      var release = { id: id, previous: previousDate, ids: Array.from(current).sort(), new: [], retained: [], returned: [], removed: [] };
      current.forEach(function (tid) {
        release[previous.has(tid) ? "retained" : seen.has(tid) ? "returned" : "new"].push(tid);
      });
      previous.forEach(function (tid) { if (!current.has(tid)) release.removed.push(tid); });
      scopes.forEach(function (scope) { release[scope].sort(); });
      current.forEach(function (tid) { seen.add(tid); });
      previous = current; previousDate = id;
      return release;
    });
  }
  function outcomeCoverage(day, ids) {
    var matrix = (day && day.matrix) || {}, tasks = matrix.tasks || [], rows = matrix.rows || [];
    var positions = new Map(tasks.map(function (id, i) { return [id, i]; }));
    var byTask = Object.create(null), evaluated = 0, unsolved = 0, cells = 0;
    ids.forEach(function (id) {
      var i = positions.get(id), passed = 0, n = 0;
      if (i !== undefined) rows.forEach(function (row) {
        var value = (row.g || [])[i];
        if (value === 0 || value === 1) { n += 1; passed += value; }
      });
      byTask[id] = { passed: passed, evaluated: n };
      if (n) { evaluated += 1; cells += n; if (!passed) unsolved += 1; }
    });
    return { tasks: ids.length, evaluated: evaluated, unsolved: unsolved, cells: cells, byTask: byTask };
  }
  function releaseCapabilities(cap, ids) {
    var members = new Set(ids), covered = new Set(), axes = [];
    ((cap && cap.axes) || []).forEach(function (axis) {
      var derived = new Set((axis.task_ids || []).filter(function (id) { return members.has(id); }));
      var declared = new Set((((axis.declared_unverified || {}).task_ids) || []).filter(function (id) { return members.has(id) && !derived.has(id); }));
      derived.forEach(function (id) { covered.add(id); });
      declared.forEach(function (id) { covered.add(id); });
      if (derived.size + declared.size) axes.push({ code: axis.code, name: axis.name, count: derived.size + declared.size, declared: declared.size });
    });
    return { axes: axes, labelled: covered.size };
  }
  function esc(value) { return T.esc(value); }
  function route(path) { return T.routeUrl ? T.routeUrl(path) : (T.ROOT || ".") + "/" + path; }
  function catalogueLink(id, scope) {
    return route("registry/") + "?release=" + encodeURIComponent(id) + (scope ? "&scope=" + encodeURIComponent(scope) : "");
  }
  function renderDigest(host, release, site, cap, day) {
    var count = release.ids.length, members = new Set(release.ids), projects = new Set();
    (site.tasks || []).forEach(function (task) { if (members.has(task.id) && task.repo) projects.add(task.repo); });
    var coverage = outcomeCoverage(day, release.ids), categories = releaseCapabilities(cap, release.ids);
    var compact = host.getAttribute("data-release-digest") === "latest";
    host.setAttribute("data-release-layout", compact ? "summary" : "detail");
    var heading = '<h2>Latest release <a href="' + esc(route("benchmarks/" + release.id + "/")) + '">' + esc(release.id) + '</a></h2>';
    var changes = scopes.map(function (scope) {
      return '<a class="tdb-release-stat" href="' + esc(catalogueLink(release.id, scope)) + '"><strong>' + release[scope].length + '</strong><span>' + scopeLabels[scope] + '</span></a>';
    }).join("");
    var historyNote = release.previous ? "Compared with " + release.previous + ". New means first seen in the available dated release history." : "First release in the available dated history; all listed tasks are first appearances.";
    var resultText = !day ? 'No evaluation published for this release date.' : coverage.evaluated
      ? coverage.unsolved + ' of ' + coverage.evaluated + ' evaluated tasks have no passing model result. ' + (count - coverage.evaluated) + ' tasks have no published outcome.'
      : 'No published outcomes for this release’s tasks on ' + release.id + '.';
    var coverageText = cap ? categories.axes.length + ' capability categories' : 'Capability coverage unavailable';
    var metadata = '<p class="tdb-release-intro">' + count + ' tasks · ' + projects.size + ' projects · ' + esc(coverageText) + '</p>';
    var notes = '<p class="tdb-release-note">' + esc(historyNote) + '</p><p class="tdb-release-outcome">' + esc(resultText) + '</p>';
    if (compact) {
      host.innerHTML = heading + metadata + '<div class="tdb-release-stats">' + changes + '</div>';
    } else {
      notes += '<p class="tdb-release-note">' + (cap ? categories.labelled + ' of ' + count + ' tasks have capability labels. ' : '') +
        'Categories describe the work involved; author labels are not independently verified. Tasks can have more than one label.</p>' +
        '<div class="tdb-release-categories">' + categories.axes.map(function (axis) {
          return '<a href="' + esc(catalogueLink(release.id) + '&capability=' + encodeURIComponent(axis.code)) + '">' + esc(T.capabilityLabel ? T.capabilityLabel(axis.code, axis.name) : axis.name || axis.code) + ' <span>' + axis.count + '</span></a>';
        }).join("") + '</div>';
      host.innerHTML = metadata + '<details class="tdb-release-notes"><summary>Release notes</summary><div>' + notes + '</div></details>';
    }
  }
  function renderReleaseTasks(host, release, site, day) {
    var source = new Map((site.tasks || []).map(function (task) { return [task.id, task]; }));
    var state = new URLSearchParams(root.location.search).get("scope") || "all";
    if (scopes.indexOf(state) < 0) state = "all";
    function render() {
      var ids = state === "all" ? release.ids : release[state], coverage = outcomeCoverage(day, ids);
      var hasLanguages = ids.some(function (id) { var task = source.get(id); return task && String(task.language || "").trim(); });
      var filters = ["all"].concat(scopes).map(function (scope) {
        var n = scope === "all" ? release.ids.length : release[scope].length;
        return '<button type="button" data-release-scope="' + scope + '" aria-pressed="' + (state === scope) + '">' + (scope === "all" ? "All tasks" : scopeLabels[scope]) + ' <span>' + n + '</span></button>';
      }).join("");
      var rows = ids.map(function (id) {
        var task = source.get(id), result = coverage.byTask[id];
        if (!task) return "";
        var label = result.evaluated ? result.passed + "/" + result.evaluated : "—";
        return '<tr><td><a href="' + esc(route("registry/" + id + "/") + '?date=' + release.id) + '">' + esc(cleanTaskTitle(task.title)) + '</a></td>' +
          '<td>' + esc((task.repo || "").split("/").pop() || "—") + '</td>' +
          (hasLanguages ? '<td>' + esc(task.language || "—") + '</td>' : '') +
          '<td class="tdb-num">' + esc(task.n_fail_to_pass == null ? "—" : task.n_fail_to_pass) + '</td><td class="tdb-num">' + esc(label) + '</td></tr>';
      }).join("");
      host.innerHTML = '<div class="tdb-release-filters" role="group" aria-label="Task changes">' + filters + '</div>' +
        (rows ? '<div class="tdb-catalog-table-wrap" data-tdb-suite-tasks><div class="overflow-x-auto"><table class="tdb-catalog-table tdb-release-task-table"><thead><tr><th>Task</th><th>Project</th>' +
          (hasLanguages ? '<th>Language</th>' : '') + '<th class="tdb-num">Target tests</th><th class="tdb-num" title="Passing / evaluated configurations on ' + esc(release.id) + '">Observed passes</th></tr></thead><tbody>' + rows + '</tbody></table></div></div>' : '<p class="tdb-empty">No tasks in this group.</p>');
      if (T.mountSuiteTables) T.mountSuiteTables();
      var toolbar = host.querySelector(".tdb-detail-toolbar"), scopeFilters = host.querySelector(".tdb-release-filters");
      if (toolbar && scopeFilters) {
        toolbar.classList.add("tdb-release-toolbar");
        toolbar.insertBefore(scopeFilters, toolbar.firstChild);
      }
    }
    host.addEventListener("click", function (event) {
      var button = event.target.closest("[data-release-scope]");
      if (!button) return;
      state = button.getAttribute("data-release-scope");
      var url = new URL(root.location.href);
      if (state === "all") url.searchParams.delete("scope"); else url.searchParams.set("scope", state);
      url.searchParams.delete("page");
      root.history.pushState(null, "", url); render();
    });
    root.addEventListener("popstate", function () {
      var wanted = new URLSearchParams(root.location.search).get("scope"); state = scopes.indexOf(wanted) >= 0 ? wanted : "all"; render();
    });
    render();
  }
  var caseDays = Object.create(null);
  function renderSelectedCases(day) {
    var hosts = Array.from(root.document.querySelectorAll("[data-case-task]"));
    if (!hosts.length) return;
    var observedDate = hosts[0].getAttribute("data-case-observed-date");
    var title = root.document.querySelector("[data-case-date]");
    if (title) title.textContent = "Observed results on " + observedDate;
    if (day && day.date === observedDate) caseDays[observedDate] = Promise.resolve(day);
    if (!caseDays[observedDate]) caseDays[observedDate] = T.dayData(observedDate);
    caseDays[observedDate].then(function (observedDay) {
      var coverage = outcomeCoverage(observedDay, hosts.map(function (host) { return host.getAttribute("data-case-task"); }));
      hosts.forEach(function (host) {
        var id = host.getAttribute("data-case-task"), result = coverage.byTask[id], note = host.querySelector(".tdb-case-outcome");
        note.textContent = result.evaluated ? result.passed + "/" + result.evaluated + " configurations passed" : "No published outcome";
        var link = host.querySelector("[data-case-link]");
        link.href = route("registry/" + id + "/") + "?date=" + encodeURIComponent(observedDate) + "#model-outcomes";
      });
    }).catch(function (error) {
      hosts.forEach(function (host) { T.loadError(host.querySelector(".tdb-case-outcome"), "example outcomes", error); });
    });
  }
  T.cleanTaskTitle = T.cleanTaskTitle || cleanTaskTitle;
  T.uniqueTaskCatalogue = uniqueTaskCatalogue;
  T.releaseHistory = releaseHistory;
  T.outcomeCoverage = outcomeCoverage;
  T.releaseCapabilities = releaseCapabilities;
  T.renderSelectedCases = renderSelectedCases;
  if (typeof module !== "undefined" && module.exports) module.exports = { cleanTaskTitle: cleanTaskTitle, uniqueTaskCatalogue: uniqueTaskCatalogue, releaseHistory: releaseHistory, outcomeCoverage: outcomeCoverage, releaseCapabilities: releaseCapabilities };
  if (!root.document || !T.getJSON || T.redirecting) return;
  var hosts = Array.from(root.document.querySelectorAll("[data-release-digest]"));
  if (!hosts.length) return;
  hosts.forEach(function (host) { host.setAttribute("aria-busy", "true"); });
  Promise.all([T.getJSON("site_data.json"), T.getJSON("data/capability.json").catch(T.fetchFailed("the capability catalogue")), T.dayIndex()]).then(function (loaded) {
    var site = loaded[0], cap = loaded[1], index = loaded[2], history = releaseHistory(site);
    hosts.forEach(function (host) {
      var wanted = host.getAttribute("data-release-digest"), release = wanted === "latest" ? history[history.length - 1] : history.find(function (item) { return item.id === wanted; });
      if (!release) { host.innerHTML = '<p class="tdb-empty">No dated release history is available.</p>'; host.removeAttribute("aria-busy"); return; }
      var data = (index.days || []).indexOf(release.id) >= 0 ? T.dayData(release.id) : Promise.resolve(null);
      data.then(function (day) {
        renderDigest(host, release, site, cap, day);
        var taskHost = root.document.querySelector('[data-release-tasks="' + release.id + '"]');
        if (taskHost) renderReleaseTasks(taskHost, release, site, day);
      }).catch(function (error) { T.loadError(host, "release outcomes", error); }).finally(function () { host.removeAttribute("aria-busy"); });
    });
  }).catch(function (error) { hosts.forEach(function (host) { T.loadError(host, "release history", error); host.removeAttribute("aria-busy"); }); });
})(typeof window !== "undefined" ? window : globalThis);

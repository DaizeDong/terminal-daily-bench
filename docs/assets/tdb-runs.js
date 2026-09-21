/* Read published task outcomes and individual attempts without inferring logs. */
(function (root) {
  "use strict";
  var T = root.TDB = root.TDB || {}, PAGE_SIZE = 20;
  function number(value, integer) {
    return typeof value === "number" && isFinite(value) && value >= 0 && (!integer || Number.isInteger(value));
  }
  function binary(value) { return value === 0 || value === 1; }
  function cellKey(model, scaffold) { return JSON.stringify([model, scaffold]); }
  function taskRunData(day, details, task) {
    var cells = new Map(), matrices = [], seenScaffolds = new Set();
    if (!day || typeof day.date !== "string") return { available:false, reason:"day", runs:[], outcomes:[] };
    if (day.matrices && typeof day.matrices === "object") matrices = Object.keys(day.matrices).map(function (key) { return day.matrices[key]; });
    if (day.matrix) matrices.push(day.matrix);
    try {
      matrices.forEach(function (matrix) {
        if (!matrix || !Array.isArray(matrix.tasks) || !Array.isArray(matrix.rows) || typeof matrix.scaffold !== "string") throw Error("matrix");
        if (seenScaffolds.has(matrix.scaffold)) return;
        seenScaffolds.add(matrix.scaffold);
        var index = matrix.tasks.indexOf(task);
        if (index < 0) return;
        var models = new Set();
        matrix.rows.forEach(function (row) {
          if (!row || typeof row.model !== "string" || !Array.isArray(row.g) || row.g.length !== matrix.tasks.length || models.has(row.model)) throw Error("matrix");
          models.add(row.model);
          var value = row.g[index];
          if (value === null) return;
          if (!binary(value)) throw Error("matrix");
          cells.set(cellKey(row.model, matrix.scaffold), { model:row.model, scaffold:matrix.scaffold, outcome:value });
        });
      });
    } catch (error) { return { available:false, reason:"matrix", runs:[], outcomes:[] }; }
    var outcomes = Array.from(cells.values()), runs = [], ids = new Set(), attempts = new Set(), groups = new Map();
    if (details !== null && details !== undefined) {
      if (details.schema !== "tdb-run-details-v1" || details.date !== day.date || !Array.isArray(details.runs)) return { available:false, reason:"telemetry", runs:[], outcomes:outcomes };
      try {
        details.runs.forEach(function (run) {
          if (!run || run.task_id !== task) return;
          var key = cellKey(run.model, run.scaffold), cell = cells.get(key);
          if (!cell || typeof run.id !== "string" || !run.id || ids.has(run.id) || !binary(run.outcome)) throw Error("identity");
          var repeated = run.attempt_index !== undefined;
          if (repeated && (!number(run.attempt_index, true) || !number(run.trial_count, true) || run.trial_count < 1 || run.attempt_index >= run.trial_count || run.cell_outcome !== cell.outcome)) throw Error("attempt");
          if (!repeated && run.outcome !== cell.outcome) throw Error("outcome");
          ["cost_usd", "wall_sec", "input_tokens", "output_tokens", "command_count", "tool_call_count"].forEach(function (field) {
            if (run[field] !== null && run[field] !== undefined && !number(run[field], /tokens|_count$/.test(field))) throw Error("metric");
          });
          if (number(run.command_count) && number(run.tool_call_count) && run.command_count > run.tool_call_count) throw Error("metric");
          if (!Array.isArray(run.steps)) throw Error("steps");
          run.steps.forEach(function (step) {
            if (!step || ["kind", "title", "detail", "status"].some(function (field) { return typeof step[field] !== "string"; })) throw Error("steps");
          });
          var index = repeated ? run.attempt_index : 0, attemptKey = JSON.stringify([key, index]);
          if (attempts.has(attemptKey)) throw Error("duplicate");
          attempts.add(attemptKey); ids.add(run.id);
          if (!groups.has(key)) groups.set(key, []);
          groups.get(key).push(run);
          runs.push(Object.assign({}, run));
        });
        groups.forEach(function (group, key) {
          var count = group[0].trial_count || 1;
          if (group.length !== count || group.some(function (run) { return (run.trial_count || 1) !== count; })) throw Error("incomplete");
          if (Number(group.reduce(function (sum, run) { return sum + run.outcome; }, 0) * 2 > count) !== cells.get(key).outcome) throw Error("majority");
        });
      } catch (error) { return { available:false, reason:"telemetry", runs:[], outcomes:outcomes }; }
    }
    var compare = function (a, b) { return a.model.localeCompare(b.model) || a.scaffold.localeCompare(b.scaffold) || (a.attempt_index || 0) - (b.attempt_index || 0); };
    runs.sort(compare); outcomes.sort(compare);
    runs.forEach(function (run) {
      var group = groups.get(cellKey(run.model, run.scaffold));
      run.cell_passes = group.reduce(function (sum, item) { return sum + item.outcome; }, 0);
    });
    return { available:true, date:day.date, runs:runs, outcomes:outcomes, telemetry:!!details,
      aggregation:day.aggregation || null, models:Array.from(new Set(outcomes.map(function (r) { return r.model; }))).sort(),
      scaffolds:Array.from(new Set(outcomes.map(function (r) { return r.scaffold; }))).sort() };
  }
  function runPage(rows, filters) {
    filters = filters || {};
    var selected = rows.filter(function (row) { return (!filters.model || row.model === filters.model) && (!filters.scaffold || row.scaffold === filters.scaffold); });
    var pages = Math.max(1, Math.ceil(selected.length / PAGE_SIZE));
    var page = Number.isInteger(Number(filters.page)) ? Math.max(1, Math.min(pages, Number(filters.page))) : 1;
    var target = filters.run ? selected.findIndex(function (row) { return row.id === filters.run; }) : -1;
    if (target >= 0) page = Math.floor(target / PAGE_SIZE) + 1;
    return { rows:selected.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE), total:selected.length,
      page:page, pages:pages, start:selected.length ? (page - 1) * PAGE_SIZE + 1 : 0,
      end:Math.min(page * PAGE_SIZE, selected.length), selectedRunFound:target >= 0 };
  }
  function runUrl(value, state) {
    var url = new URL(value);
    if (T.canonicalUrl) url = T.canonicalUrl(url.href);
    ["d", "scaffold", "run_page", "run-page", "model", "agent", "effort", "run"].forEach(function (key) { url.searchParams.delete(key); });
    if (state.date) url.searchParams.set("date", state.date);
    if (state.model) url.searchParams.set("model", state.model);
    if (state.scaffold) { var parts = state.scaffold.split("@"); url.searchParams.set("agent", parts[0]); url.searchParams.set("effort", parts[1] || "default"); }
    if (state.run) url.searchParams.set("run", state.run);
    if (state.page > 1) url.searchParams.set("run-page", state.page);
    url.searchParams.sort();
    return url;
  }
  Object.assign(T, { taskRunData:taskRunData, taskRunPage:runPage, taskRunUrl:runUrl });
  if (!root.document) return;
  var esc = T.esc || function (value) { return String(value == null ? "" : value).replace(/[&<>"']/g, function (x) { return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[x]; }); };
  function modelLabel(value) { return T.modelLabel ? T.modelLabel(value) : value; }
  function settingLabel(value) { var parts = value.split("@"); return (T.agentLabel ? T.agentLabel(parts[0]) : parts[0]) + ", " + (parts[1] || "default") + " effort"; }
  function metric(value, suffix) { return number(value) ? value.toLocaleString("en-US", {maximumFractionDigits:2}) + (suffix || "") : "Not published"; }
  function outcome(value) { return value === 1 ? "Solved" : "Not solved"; }
  function readState() {
    var p = new URL(root.location.href).searchParams, agent = p.get("agent"), effort = p.get("effort");
    return { date:p.get("date") || p.get("d") || "", model:p.get("model") || "",
      scaffold:agent ? agent + (effort && effort !== "default" ? "@" + effort : "") : "",
      page:Number(p.get("run-page") || p.get("run_page")) || 1, run:p.get("run") || "" };
  }
  function mount() {
    if (T.redirecting) return;
    var host = document.querySelector("[data-task-runs]");
    if (!host || !T.getData || !T.dayData) return;
    var task = host.getAttribute("data-task-runs"), state = readState(), dates = [], runDates = [], epoch = 0, data = null, loadingError = false;
    var initialNote = "", detailsCache = Object.create(null), indexFailed = false, taskFiles = {};
    host.innerHTML = '<h2>Model attempts</h2><p class="tdb-run-note" role="status">Loading published results…</p>';
    function writeState(push) { var url = runUrl(root.location.href, state); root.history[push ? "pushState" : "replaceState"]({}, "", url.href); }
    function options(items, selected, label) { return items.map(function (value) { return '<option value="' + esc(value) + '"' + (value === selected ? ' selected' : '') + '>' + esc(label(value)) + '</option>'; }).join(""); }
    function fact(label, value) { return '<span>' + esc(label) + ': <strong>' + esc(value) + '</strong></span>'; }
    function attemptHTML(run) {
      var index = run.attempt_index || 0, count = run.trial_count || 1;
      var verdict = 'Published task result: ' + outcome(run.cell_outcome == null ? run.outcome : run.cell_outcome) +
        (count > 1 ? ' by majority vote (' + run.cell_passes + ' of ' + count + ' attempts passed).' : '.');
      var steps = run.steps.length ? '<ol class="tdb-run-steps">' + run.steps.map(function (step) {
        return '<li><strong>' + esc(step.title) + '</strong><p>' + esc(step.detail) + '</p><span>' + esc(step.status === "recorded" ? "Recorded action; completion not independently reported" : step.status) + '</span></li>';
      }).join("") + '</ol>' : '<p class="tdb-run-note">Action logs were not published for this attempt. Its recorded outcome and available measurements are shown above.</p>';
      var permalink = runUrl(root.location.href, Object.assign({}, state, {model:run.model, scaffold:run.scaffold, run:run.id}));
      permalink.hash = "model-outcomes";
      return '<details data-run="' + esc(run.id) + '"' + (state.run === run.id ? ' open' : '') + '><summary><strong>' + esc(modelLabel(run.model)) + '</strong><span>' + esc(settingLabel(run.scaffold)) + '</span><span>Attempt ' + (index + 1) + ' of ' + count + '</span><span class="tdb-run-outcome">' + (run.outcome ? 'Passed' : 'Did not pass') + '</span></summary><div class="tdb-run-facts">' +
        fact('Commands', number(run.command_count, true) ? metric(run.command_count) : 'Not recorded') +
        fact('Tool calls', number(run.tool_call_count, true) ? metric(run.tool_call_count) : 'Not recorded') +
        fact('Elapsed time', metric(run.wall_sec, ' s')) + fact('Recorded cost', number(run.cost_usd) ? '$' + run.cost_usd.toFixed(4) : 'Not published') +
        fact('Input tokens', metric(run.input_tokens)) + fact('Output tokens', metric(run.output_tokens)) + '</div><p class="tdb-run-note">' + esc(verdict) + '</p>' + steps +
        '<a class="tdb-navlink" href="' + esc(permalink.href) + '">Link to this attempt</a></details>';
    }
    function draw() {
      var actual = data && data.available && data.runs.length > 0;
      var source = actual ? data.runs : (data ? data.outcomes : []), page = runPage(source, state);
      state.page = page.page;
      var models = data && data.models || Array.from(new Set(source.map(function (r) { return r.model; }))).sort();
      var settings = data && data.scaffolds || Array.from(new Set(source.map(function (r) { return r.scaffold; }))).sort();
      if (state.model && models.indexOf(state.model) < 0) models.push(state.model);
      if (state.scaffold && settings.indexOf(state.scaffold) < 0) settings.push(state.scaffold);
      var note = initialNote;
      if (loadingError) note += ' Per-attempt measurements could not be loaded. Available published task outcomes are shown below.';
      else if (data && !data.available) note += ' Per-attempt records could not be verified. Available published task outcomes are shown below.';
      else if (!actual && source.length) note += ' Published task outcomes are available for this date. Individual attempt measurements and action logs were not published.';
      else if (actual) note += ' Each row is one recorded attempt. The published task result uses a majority vote across all attempts for the same model and setting. Failed attempts are included in the measurements.';
      var body;
      if (!source.length) body = '<p class="tdb-run-note">No task-level outcomes are published for this task on the selected date. This does not mean the task failed.</p>';
      else if (!page.total) body = '<p class="tdb-run-note">No published results match the selected model and setting. Choose another filter to view available results.</p>';
      else if (actual) body = page.rows.map(attemptHTML).join("");
      else body = page.rows.map(function (row) { return '<details><summary><strong>' + esc(modelLabel(row.model)) + '</strong><span>' + esc(settingLabel(row.scaffold)) + '</span><span class="tdb-run-outcome">' + esc(outcome(row.outcome)) + '</span></summary><p class="tdb-run-note">This is the published task outcome. Command counts and other attempt details are not available.</p></details>'; }).join("");
      host.innerHTML = '<h2>Model attempts</h2><p class="tdb-run-note">' + esc(note.trim()) + '</p><div class="tdb-run-controls">' +
        '<label>Evaluation date<select data-run-filter="date">' + options(dates, state.date, function (x) { return x; }) + '</select></label>' +
        '<label>Model<select data-run-filter="model"><option value="">All models</option>' + options(models, state.model, modelLabel) + '</select></label>' +
        '<label>Agent and effort<select data-run-filter="scaffold"><option value="">All settings</option>' + options(settings, state.scaffold, settingLabel) + '</select></label></div>' +
        '<p class="tdb-run-note" role="status" aria-live="polite">' + (page.total ? page.start + '–' + page.end + ' of ' + page.total + (actual ? ' attempts' : ' published outcomes') : 'No matching results') + '</p>' +
        (state.run && !page.selectedRunFound ? '<p class="tdb-run-note">The requested attempt is not available in this selection.</p>' : '') +
        '<div class="tdb-run-list">' + body + '</div><div class="tdb-run-pager"><button type="button" data-run-page="prev"' + (page.page <= 1 ? ' disabled' : '') + '>Previous</button><span>Page ' + page.page + ' of ' + page.pages + '</span><button type="button" data-run-page="next"' + (page.page >= page.pages ? ' disabled' : '') + '>Next</button></div>';
    }
    async function loadDate(push) {
      var ticket = ++epoch;
      host.setAttribute("aria-busy", "true");
      try {
        var dayPromise = T.dayData(state.date);
        var file = encodeURIComponent(state.date) + '.json';
        if (taskFiles[state.date]) {
          file = taskFiles[state.date][task] || null;
          if (file && file !== state.date + '/tasks/' + task + '.json') throw Error("task path");
        }
        var detailsPromise = runDates.indexOf(state.date) < 0 || !file ? Promise.resolve(null) : (detailsCache[state.date] || (detailsCache[state.date] = T.getData('data/run-details/' + file)));
        var results = await Promise.allSettled([dayPromise, detailsPromise]);
        if (ticket !== epoch) return;
        if (results[0].status !== "fulfilled") throw Error("day");
        loadingError = indexFailed || results[1].status !== "fulfilled";
        if (loadingError) delete detailsCache[state.date];
        data = taskRunData(results[0].value, loadingError ? null : results[1].value, task);
        if (state.run && !state.model && !state.scaffold) {
          var target = data.runs.find(function (run) { return run.id === state.run; });
          if (target) { state.model = target.model; state.scaffold = target.scaffold; }
        }
        draw(); writeState(push);
      } catch (error) {
        if (ticket !== epoch) return;
        host.innerHTML = '<h2>Model attempts</h2><p class="tdb-run-note" role="status">Published results could not be loaded. <button type="button" data-run-retry>Try again</button></p>';
      } finally { if (ticket === epoch) host.removeAttribute("aria-busy"); }
    }
    host.addEventListener("change", function (event) {
      var filter = event.target.getAttribute("data-run-filter"); if (!filter) return;
      state[filter] = event.target.value; state.page = 1; state.run = ""; initialNote = "";
      if (filter === "date") loadDate(true); else { draw(); writeState(true); }
    });
    host.addEventListener("click", function (event) {
      var button = event.target.closest("button"); if (!button) return;
      if (button.hasAttribute("data-run-retry")) { loadDate(false); return; }
      var direction = button.getAttribute("data-run-page"); if (!direction) return;
      state.page += direction === "next" ? 1 : -1; state.run = ""; draw(); writeState(true);
    });
    host.addEventListener("toggle", function (event) {
      var detail = event.target, id = detail.getAttribute && detail.getAttribute("data-run");
      if (!id || !detail.isConnected) return;
      if (detail.open && state.run !== id) { state.run = id; writeState(false); }
      else if (!detail.open && state.run === id) { state.run = ""; writeState(false); }
    }, true);
    root.addEventListener("popstate", function () { state = readState(); if (dates.indexOf(state.date) < 0) state.date = dates[0]; loadDate(false); });
    Promise.allSettled([T.dayIndex(), T.getData('data/run-details/index.json'), T.getData('site_data.json')]).then(function (results) {
      if (results[0].status !== "fulfilled" || !Array.isArray(results[0].value.days) || !results[0].value.days.length) throw Error("index");
      dates = results[0].value.days.slice();
      var index = results[1].status === "fulfilled" && results[1].value;
      if (index && index.schema === "tdb-run-details-index-v1" && Array.isArray(index.dates)) runDates = index.dates;
      else indexFailed = true;
      if (index && index.task_files && typeof index.task_files === "object") taskFiles = index.task_files;
      if (dates.indexOf(state.date) < 0) {
        if (state.date) initialNote = 'The requested date is not published. Showing an available evaluation date.';
        var catalogue = results[2].status === "fulfilled" && results[2].value;
        var info = catalogue && Array.isArray(catalogue.tasks) && catalogue.tasks.find(function (row) { return row.id === task; });
        var memberships = info && T.taskSuites ? T.taskSuites(info) : info && info.suites || [];
        state.date = dates.find(function (date) { return memberships.indexOf(date) >= 0; }) || dates[0];
      }
      return loadDate(false);
    }).catch(function () { host.innerHTML = '<h2>Model attempts</h2><p class="tdb-run-note" role="status">Published result dates could not be loaded. Reload the page to try again.</p>'; });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount); else mount();
})(typeof window !== "undefined" ? window : globalThis);

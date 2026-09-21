/* Comparisons are always made on published, paired observations. */
(function () {
  "use strict";
  var T = window.TDB;
  var valid = function (x) { return x === 0 || x === 1; };
  var numeric = function (x) { return typeof x === "number" && isFinite(x) && x >= 0; };
  var label = function (x) { return T.modelLabel(x); };
  var esc = function (x) { return T.esc(x); };
  function rate(solved, n) { return { solved: solved, n: n, rate: n ? solved / n : null }; }
  function tally(values) {
    var n = 0, solved = 0;
    values.forEach(function (v) { if (valid(v)) { n++; solved += v; } });
    return rate(solved, n);
  }
  function withRepeats(value, day, model, scaffold, tasks) {
    var repeat = T.resultStats(day, model, scaffold, tasks);
    return repeat && repeat.n === value.n ? Object.assign(value, { repeat: repeat }) : value;
  }
  function pairRepeats(pair, firstDay, secondDay, first, second) {
    var tasks = Object.keys(pair.groups).reduce(function (ids, key) {
      return ids.concat(pair.groups[key].map(function (task) { return task.id; }));
    }, []);
    pair.a = withRepeats(pair.a, firstDay, first, firstDay.matrix.scaffold, tasks);
    pair.b = withRepeats(pair.b, secondDay, second, secondDay.matrix.scaffold, tasks);
    pair.delta = pair.n ? pair.a.rate - pair.b.rate : null;
    return pair;
  }
  function axesFor(grid, cap) {
    if (!cap || !Array.isArray(cap.axes)) return [];
    var floor = numeric(cap.floor) ? cap.floor : (cap.publish_gate && numeric(cap.publish_gate.min_tasks) ? cap.publish_gate.min_tasks : null);
    return cap.axes.map(function (axis) {
      var ids = new Set((axis.task_ids || []).concat((axis.declared_unverified || {}).task_ids || []));
      var cols = Array.isArray(axis.cols) ? axis.cols.filter(function (i) { return Number.isInteger(i) && i >= 0 && i < grid.tasks.length; }) :
        grid.tasks.filter(function (task) { return ids.has(task.id); }).map(function (task) { return task.index; });
      cols = Array.from(new Set(cols));
      var names = { filesystem: "Files and folders", build: "Building software", debug: "Debugging", impl: "Implementation", test: "Testing", data: "Data processing", net: "Networking", sec: "Security", ops: "System administration", vcs: "Version control", perf: "Performance", reverse: "Reverse engineering", ml: "Machine learning", orch: "Workflow automation" };
      return { code: axis.code, name: names[axis.name] || axis.name, cols: cols, minTasks: numeric(axis.minTasks) ? axis.minTasks : floor,
        declared: numeric(axis.nDeclared) ? axis.nDeclared : ((axis.declared_unverified || {}).task_ids || []).length };
    });
  }
  function measuredPair(a, b, tasks) {
    var groups = { both: [], a_only: [], b_only: [], neither: [] }, missing = [], as = 0, bs = 0;
    tasks.forEach(function (task) {
      var av = a.values[task.index], bv = b.values[task.otherIndex === undefined ? task.index : task.otherIndex];
      var item = Object.assign({}, task, { a: av, b: bv });
      if (!valid(av) || !valid(bv)) { missing.push(item); return; }
      groups[av === 1 ? (bv === 1 ? "both" : "a_only") : (bv === 1 ? "b_only" : "neither")].push(item);
      as += av; bs += bv;
    });
    var n = tasks.length - missing.length;
    return { groups: groups, missing: missing, n: n, a: rate(as, n), b: rate(bs, n), delta: n ? (as - bs) / n : null };
  }
  function compareModels(day, site, cap, first, second) {
    var grid = T.taskGrid(day, site), failure = { available: false, reason: grid.reason || "selection", grid: grid };
    if (!grid.available) return failure;
    var a = grid.rows.find(function (r) { return r.model === first; }), b = grid.rows.find(function (r) { return r.model === second; });
    if (!a || !b || first === second) return failure;
    var result = pairRepeats(measuredPair(a, b, grid.tasks), day, day, first, second);
    result.axes = axesFor(grid, cap).map(function (axis) {
      var paired = pairRepeats(measuredPair(a, b, axis.cols.map(function (i) { return grid.tasks[i]; })), day, day, first, second);
      return Object.assign({}, axis, paired, { preliminary: axis.minTasks === null || paired.n < axis.minTasks || axis.declared > 0 });
    });
    return Object.assign(result, { available: true, grid: grid, first: first, second: second });
  }
  function modelProfile(day, site, cap, model) {
    var grid = T.taskGrid(day, site), row = grid.rows.find(function (r) { return r.model === model; });
    if (!grid.available || !row) return { available: false, reason: grid.reason || "selection", grid: grid };
    var peers = grid.rows.filter(function (r) { return r.model !== model; });
    var axes = axesFor(grid, cap).map(function (axis) {
      var ownTasks = axis.cols.filter(function (i) { return valid(row.values[i]); }).map(function (i) { return grid.tasks[i].id; });
      var ownRate = withRepeats(tally(axis.cols.map(function (i) { return row.values[i]; })), day, model, grid.scaffold, ownTasks);
      var pairN = 0, peerSolved = 0, modelSolved = 0, peerCount = 0;
      peers.forEach(function (peer) {
        var paired = pairRepeats(measuredPair(row, peer, axis.cols.map(function (i) { return grid.tasks[i]; })), day, day, model, peer.model);
        if (paired.n) {
          peerCount++; pairN += paired.n;
          modelSolved += paired.a.solved; peerSolved += paired.b.solved;
        }
      });
      return Object.assign({}, axis, ownRate, { pairs: pairN, peers: peerCount,
        peerRate: pairN ? peerSolved / pairN : null, delta: pairN ? (modelSolved - peerSolved) / pairN : null,
        preliminary: axis.minTasks === null || ownRate.n < axis.minTasks || axis.declared > 0 });
    });
    var examples = grid.tasks.filter(function (t) { return valid(row.values[t.index]); }).map(function (task) {
      var peer = tally(peers.map(function (r) { return r.values[task.index]; }));
      return Object.assign({}, task, { outcome: row.values[task.index], peerSolved: peer.solved, peerN: peer.n, peerRate: peer.rate });
    });
    function representative(outcome) {
      return examples.filter(function (t) { return t.outcome === outcome; }).sort(function (a, b) {
        if (!!a.peerN !== !!b.peerN) return a.peerN ? -1 : 1;
        return (outcome ? a.peerRate - b.peerRate : b.peerRate - a.peerRate) || a.id.localeCompare(b.id);
      }).slice(0, 6);
    }
    return { available: true, grid: grid, model: model, overall: withRepeats(tally(row.values), day, model, grid.scaffold,
        grid.tasks.filter(function (task) { return valid(row.values[task.index]); }).map(function (task) { return task.id; })), axes: axes,
      solved: representative(1), failed: representative(0) };
  }
  function settingsKey(day) {
    var m = day && day.matrix;
    if (!m || typeof m.scaffold !== "string" || !m.scaffold) return null;
    function stable(x) {
      if (Array.isArray(x)) return x.map(stable);
      if (x && typeof x === "object") {
        var result = {}; Object.keys(x).sort().forEach(function (key) { result[key] = stable(x[key]); }); return result;
      }
      return x;
    }
    return JSON.stringify(stable({ scaffold: m.scaffold, settings: m.settings || null, aggregation: day.aggregation || null }));
  }
  function compareReleases(before, after, site, model) {
    var old = T.taskGrid(before, site), current = T.taskGrid(after, site);
    if (!old.available || !current.available) return { available: false, reason: "matrix" };
    if (!settingsKey(before) || settingsKey(before) !== settingsKey(after)) return { available: false, reason: "settings" };
    var a = old.rows.find(function (r) { return r.model === model; }), b = current.rows.find(function (r) { return r.model === model; });
    if (!a || !b) return { available: false, reason: "model" };
    var oldTasks = new Map(old.tasks.map(function (t) { return [t.id, t]; }));
    var newTasks = new Map(current.tasks.map(function (t) { return [t.id, t]; }));
    var shared = old.tasks.filter(function (t) { return newTasks.has(t.id); }).map(function (t) {
      return Object.assign({}, t, { otherIndex: newTasks.get(t.id).index });
    });
    return Object.assign(pairRepeats(measuredPair(a, b, shared), before, after, model, model), { available: true, before: before.date, after: after.date, model: model,
      shared: shared.length,
      added: current.tasks.filter(function (t) { return !oldTasks.has(t.id); }).map(function (t) { return Object.assign({}, t, { outcome: b.values[t.index] }); }),
      removed: old.tasks.filter(function (t) { return !newTasks.has(t.id); }).map(function (t) { return Object.assign({}, t, { outcome: a.values[t.index] }); }) });
  }
  function efficiencyData(day, details, options) {
    options = options || {};
    if (!details) return { available: false, reason: "missing", rows: [] };
    if (details.schema !== "tdb-run-details-v1" || details.date !== day.date || !Array.isArray(details.runs)) return { available: false, reason: "invalid", rows: [] };
    var groups = new Map(), seen = new Set(), runIds = new Set(), invalid = false;
    details.runs.forEach(function (run) {
      if (!run || typeof run.model !== "string" || typeof run.scaffold !== "string" || typeof run.task_id !== "string" || !valid(run.outcome)) { invalid = true; return; }
      var multiple = run.attempt_index !== undefined;
      if (multiple && (!Number.isInteger(run.attempt_index) || run.attempt_index < 0 || typeof run.id !== "string" || !run.id || !valid(run.cell_outcome))) { invalid = true; return; }
      var key = JSON.stringify([run.model, run.scaffold, run.task_id, multiple ? run.attempt_index : null]);
      if (seen.has(key)) { invalid = true; return; } seen.add(key);
      if (typeof run.id === "string" && run.id) {
        if (runIds.has(run.id)) { invalid = true; return; }
        runIds.add(run.id);
      }
      if (run.cost_usd != null && !numeric(run.cost_usd) ||
          [run.command_count, run.tool_call_count].some(function (value) { return value != null && (!Number.isSafeInteger(value) || value < 0); }) ||
          run.command_count != null && run.tool_call_count != null && run.command_count > run.tool_call_count) { invalid = true; return; }
      var entry = (day.leaderboard || []).find(function (r) { return r.model === run.model; });
      if (!entry || !entry[run.scaffold] || !(entry[run.scaffold].n > 0)) { invalid = true; return; }
      var matrix = day.matrices && day.matrices[run.scaffold] || (day.matrix && day.matrix.scaffold === run.scaffold ? day.matrix : null);
      var cellOutcome = valid(run.cell_outcome) ? run.cell_outcome : run.outcome;
      if (matrix) {
        var taskIndex = matrix.tasks.indexOf(run.task_id), matrixRow = matrix.rows.find(function (r) { return r.model === run.model; });
        if (taskIndex < 0 || !matrixRow || matrixRow.g[taskIndex] !== cellOutcome) { invalid = true; return; }
      }
      var bits = run.scaffold.split("@"), effort = bits[1] || "default";
      if (options.agent && bits[0] !== options.agent || options.effort && effort !== options.effort) return;
      if (options.query && (run.model + " " + label(run.model)).toLowerCase().indexOf(options.query.toLowerCase()) < 0) return;
      var groupKey = JSON.stringify([run.model, run.scaffold]);
      if (!groups.has(groupKey)) groups.set(groupKey, { model: run.model, scaffold: run.scaffold, agent: bits[0], effort: effort,
        n: 0, solved: 0, costSum: 0, costN: 0, commandSum: 0, commandN: 0, toolSum: 0, toolN: 0,
        cells: new Map(), costCells: new Map(), commandCells: new Map(), toolCells: new Map() });
      var g = groups.get(groupKey); g.n++; g.solved += run.outcome;
      if (g.cells.has(run.task_id) && g.cells.get(run.task_id) !== cellOutcome) invalid = true;
      g.cells.set(run.task_id, cellOutcome);
      if (numeric(run.cost_usd)) { g.costSum += run.cost_usd; g.costN++; g.costCells.set(run.task_id, cellOutcome); }
      if (numeric(run.command_count)) { g.commandSum += run.command_count; g.commandN++; g.commandCells.set(run.task_id, cellOutcome); }
      if (numeric(run.tool_call_count)) { g.toolSum += run.tool_call_count; g.toolN++; g.toolCells.set(run.task_id, cellOutcome); }
    });
    if (invalid) return { available: false, reason: "invalid", rows: [] };
    var rows = Array.from(groups.values()).map(function (r) {
      function subset(cells) {
        return withRepeats(tally(Array.from(cells.values())), day, r.model, r.scaffold, Array.from(cells.keys()));
      }
      var all = subset(r.cells), cost = subset(r.costCells), commands = subset(r.commandCells), tools = subset(r.toolCells);
      delete r.cells; delete r.costCells; delete r.commandCells; delete r.toolCells;
      return Object.assign(r, { rate: all.rate, repeat: all.repeat || null, taskN: all.n, taskSolved: all.solved, meanCost: r.costN ? r.costSum / r.costN : null,
        meanCommands: r.commandN ? r.commandSum / r.commandN : null, meanTools: r.toolN ? r.toolSum / r.toolN : null,
        costRate: cost.rate, costRepeat: cost.repeat || null, costSolved: cost.solved, costTaskN: cost.n,
        commandRate: commands.rate, commandRepeat: commands.repeat || null, commandSolved: commands.solved, commandTaskN: commands.n,
        toolRate: tools.rate, toolRepeat: tools.repeat || null, toolSolved: tools.solved, toolTaskN: tools.n });
    }).sort(function (a, b) { return label(a.model).localeCompare(label(b.model)) || a.scaffold.localeCompare(b.scaffold); });
    return { available: true, rows: rows };
  }
  function efficiencyMetric(rows, requested) {
    return ["commands", "tools", "cost"].includes(requested) ? requested : "commands";
  }

  function createInsights(host, callbacks) {
    callbacks = callbacks || {};
    var state = { context: null, model: "", compare: [], baseline: "", metric: "commands", metricExplicit: false,
      efficiencyPage: 1, focusAfterRender: "", group: "a_only", page: 1, scaffold: "" };
    var snapshot = null, detailCache = new Map(), historyCache = new Map(), generation = 0, efficiencyRows = [];
    function link(path) { return T.routeUrl ? T.routeUrl(path) : "../" + path; }
    function pct(x) { return x === null ? "—" : (x * 100).toFixed(1) + "%"; }
    function diff(x) { return x === null ? "—" : (x > 0 ? "+" : "") + (100 * x).toFixed(1) + " pp"; }
    function settings() {
      var day = selectedDay(), parts = String((day.matrix || {}).scaffold || "").split("@");
      return T.agentLabel(parts[0] || "Published agent") + ", " + (parts[1] || "default") + " effort";
    }
    function selectedDay(day) {
      day = day || state.context.day;
      var matrix = day.matrices && day.matrices[state.scaffold];
      return matrix ? Object.assign({}, day, { matrix: matrix }) : day;
    }
    function settingSelect() {
      var matrices = state.context.day.matrices || {}, keys = Object.keys(matrices);
      if (keys.length < 2) return "";
      return '<label><span>Published setting</span><select data-insight="scaffold">' + keys.map(function (key) {
        var parts = key.split("@"); return '<option value="' + esc(key) + '"' + (key === state.scaffold ? " selected" : "") + '>' + esc(T.agentLabel(parts[0]) + ", " + (parts[1] || "default") + " effort") + '</option>';
      }).join("") + '</select></label>';
    }
    function modelOptions(models, selected) {
      return models.map(function (id) { return '<option value="' + esc(id) + '"' + (id === selected ? " selected" : "") + '>' + esc(label(id)) + '</option>'; }).join("");
    }
    function modelSelect(key, text, models, selected) {
      return '<label><span>' + esc(text) + '</span><select data-insight="' + esc(key) + '">' + modelOptions(models, selected) + '</select></label>';
    }
    function nav(view, text, model) { return '<button type="button" data-insight-view="' + esc(view) + '"' + (model ? ' data-insight-model="' + esc(model) + '"' : "") + '>' + esc(text) + '</button>'; }
    function table(columns, rows, cls) {
      return '<div class="tdb-insight-scroll"><table class="tdb-insight-table ' + (cls || "") + '"><thead><tr>' + columns.map(function (s) { return '<th scope="col">' + esc(s) + '</th>'; }).join("") + '</tr></thead><tbody>' + rows.join("") + '</tbody></table></div>';
    }
    function td(html, number) { return '<td' + (number ? ' class="tdb-insight-number"' : "") + '>' + html + '</td>'; }
    function th(text) { return '<th scope="row">' + esc(text) + '</th>'; }
    function score(solved, n, repeat) { return n ? T.scoreCell(solved, n, repeat) : '<span class="tdb-insight-unavailable">Not evaluated</span>'; }
    function variationNote() {
      var aggregation = selectedDay().aggregation, runs = aggregation && aggregation.trials_per_cell;
      return "Scores use per-task majority outcomes" + (Number.isInteger(runs) && runs > 1 ? " (" + (Math.floor(runs / 2) + 1) + " of " + runs + " runs)" : "") + ". \u00b1 shows run standard deviation.";
    }
    function taskLink(task) {
      return task.href ? '<a href="' + esc(link("registry/" + encodeURIComponent(task.id) + "/")) + '">' + esc(task.title) + '</a>' : esc(task.title);
    }
    function note(text) { return '<p class="tdb-insight-note">' + esc(text) + '</p>'; }
    function empty(text) { return '<p class="tdb-empty" role="status">' + esc(text) + '</p>'; }
    function scoreSummary(name, result) {
      var estimate = T.scoreEstimate(result.solved, result.n, result.repeat);
      return { label: name, rate: estimate ? estimate.p : null, rate_sd: estimate ? estimate.sd : null,
        rate_runs: estimate ? estimate.runs : null, n: result.n };
    }
    function publish(title, columns, rows, notes, scores) {
      var percents = ["rate", "rate_sd", "paired_peer_gap"];
      var numbers = ["solved", "evaluated", "peer_pairs", "peer_models", "outcome_a", "outcome_b", "baseline_outcome", "current_outcome", "mean_cost_usd", "mean_commands", "mean_tool_calls", "cost_n", "command_n", "tool_n", "all_n", "cost_tasks", "command_tasks", "tool_tasks", "all_tasks"];
      var definitions = columns.map(function (key) { return { key: key, label: key.replace(/_/g, " "), type: /_runs$/.test(key) ? "number" : percents.includes(key) || /^success_rate_/.test(key) ? "percent" : numbers.includes(key) ? "number" : "text" }; });
      snapshot = { date: state.context.day.date, view: state.context.mode, title: title, columns: definitions,
        rows: rows.map(function (values) { var row = {}; columns.forEach(function (key, i) { row[key] = values[i] === undefined ? null : values[i]; }); return row; }), notes: notes || [] };
      if (scores) snapshot.scores = scores;
      if (state.context.mode === "efficiency") snapshot.metric = state.metric;
      updateUrl();
      if (callbacks.onChange) callbacks.onChange(snapshot);
    }
    function failure(text) {
      var controls = state.context && state.context.mode !== "efficiency" ? settingSelect() : "";
      host.innerHTML = (controls ? '<div class="tdb-insight-tools">' + controls + '</div>' : "") + empty(text);
      publish("Results unavailable", [], [], [text]);
    }
    function sourceModels() {
      var grid = T.taskGrid(selectedDay(), state.context.site);
      return grid.rows.map(function (r) { return r.model; }).sort(function (a, b) { return label(a).localeCompare(label(b)); });
    }
    function modelTools(models, extra) {
      return '<div class="tdb-insight-tools">' + modelSelect("model", "Model", models, state.model) + settingSelect() + (extra || "") + '</div>';
    }
    function setSelections(models) {
      if (!models.includes(state.model)) state.model = models[0] || "";
      if (!models.includes(state.compare[0])) state.compare[0] = state.model || models[0] || "";
      if (!models.includes(state.compare[1]) || state.compare[1] === state.compare[0]) state.compare[1] = models.find(function (m) { return m !== state.compare[0]; }) || "";
    }
    function taskList(tasks, headings, values) {
      var query = (state.context.query || "").toLowerCase();
      var filtered = tasks.filter(function (t) { return !query || (t.title + " " + t.id + " " + t.project).toLowerCase().includes(query); });
      var page = T.pageSlice(filtered, state.page, 20); state.page = page.page;
      var content = filtered.length ? table(["Task"].concat(headings), page.items.map(function (task) {
        return '<tr><th scope="row">' + taskLink(task) + '<small>' + esc(task.project || task.id) + '</small></th>' + values(task).map(function (v) { return td(esc(v), true); }).join("") + '</tr>';
      })) : empty("No tasks in this group match the search.");
      if (filtered.length) content += '<div class="tdb-insight-pager"><span>' + esc((page.page - 1) * 20 + 1) + '–' + esc(Math.min(page.page * 20, page.total)) + ' of ' + esc(page.total) + ' tasks</span><button type="button" data-insight-page="-1"' + (page.page === 1 ? " disabled" : "") + '>Previous</button><button type="button" data-insight-page="1"' + (page.page * 20 >= page.total ? " disabled" : "") + '>Next</button></div>';
      return { html: content, tasks: filtered };
    }
    function groupButtons(groups, labels) {
      return '<div class="tdb-insight-groups" role="group" aria-label="Task outcome group">' + Object.keys(labels).map(function (key) {
        return '<button type="button" data-insight-group="' + esc(key) + '" aria-pressed="' + (state.group === key) + '"><span>' + esc(labels[key]) + '</span><strong>' + esc(groups[key].length) + '</strong></button>';
      }).join("") + '</div>';
    }
    function comparison(models) {
      if (models.length < 2) { failure("This date needs at least two models with published task outcomes for comparison."); return; }
      if (!["both", "a_only", "b_only", "neither"].includes(state.group)) state.group = "a_only";
      var result = compareModels(selectedDay(), state.context.site, state.context.cap, state.compare[0], state.compare[1]);
      if (!result.available) { failure("Task-level results could not be compared. Choose another date."); return; }
      var first = label(result.first), second = label(result.second);
      var labels = { a_only: first + " only", b_only: second + " only", both: "Both solved", neither: "Neither solved" };
      var scope = result.n + " shared evaluated tasks · " + result.missing.length + " excluded for missing outcomes · " + settings() + ".";
      scope += " " + variationNote();
      var tasks = taskList(result.groups[state.group], [first, second], function (t) { return [t.a ? "Majority solved" : "Majority not solved", t.b ? "Majority solved" : "Majority not solved"]; });
      host.innerHTML = '<div class="tdb-insight-tools">' + modelSelect("first", "Model A", models, result.first) + modelSelect("second", "Model B", models, result.second) + settingSelect() + nav("history", "Compare releases", result.first) + '</div>' + note(result.n + " shared tasks") +
        '<div class="tdb-pair-scores">' + '<div><span>' + esc(first) + '</span>' + score(result.a.solved, result.n, result.a.repeat) + nav("profile", "View profile", result.first) + '</div><div><span>' + esc(second) + '</span>' + score(result.b.solved, result.n, result.b.repeat) + nav("profile", "View profile", result.second) + '</div></div>' +
        (result.axes.length ? '<details class="tdb-insight-details"><summary>Compare capabilities</summary>' + table(["Capability", first, second, "A − B", "Shared N"], result.axes.map(function (axis) {
          return '<tr>' + th(axis.name + (axis.preliminary ? " · preliminary" : "")) + td(score(axis.a.solved, axis.n, axis.a.repeat)) + td(score(axis.b.solved, axis.n, axis.b.repeat)) + td(esc(diff(axis.delta)), true) + td(esc(axis.n), true) + '</tr>';
        }), "tdb-pair-capabilities") + '</details>' : note("Capability definitions are unavailable for this date.")) +
        groupButtons(result.groups, labels) + tasks.html;
      publish("Model comparison: " + first + " / " + second + ": " + labels[state.group], ["task_id", "title", "model_a", "model_b", "outcome_a", "outcome_b"], tasks.tasks.map(function (t) { return [t.id, t.title, result.first, result.second, t.a, t.b]; }), [scope, "Selected group: " + labels[state.group], "Rates use paired evaluated tasks; missing outcomes are excluded."], [scoreSummary(first, result.a), scoreSummary(second, result.b)]);
    }
    function effortRows(model) { return (state.context.rows || []).filter(function (r) { return r.model === model; }); }
    function profile(models) {
      var data = modelProfile(selectedDay(), state.context.site, state.context.cap, state.model);
      if (!data.available) { failure("Model profiles need published task outcomes. Choose another date."); return; }
      var efforts = effortRows(data.model);
      function examples(items, title) {
        return '<section><h3>' + esc(title) + '</h3>' + (items.length ? '<ul class="tdb-insight-examples">' + items.map(function (t) { return '<li>' + taskLink(t) + '<span>' + esc(t.peerN ? t.peerSolved + "/" + t.peerN + " peers majority solved" : "No evaluated peers") + '</span></li>'; }).join("") + '</ul>' : note("No matching evaluated tasks.")) + '</section>';
      }
      var scope = settings() + ". " + data.overall.solved + "/" + data.overall.n + " evaluated tasks solved. All capability bars use 0–100%.";
      scope += " " + variationNote();
      host.innerHTML = modelTools(models, nav("compare", "Compare models", data.model) + nav("history", "Compare releases", data.model)) + note(data.overall.solved + "/" + data.overall.n + " tasks solved") +
        (data.axes.length ? table(["Capability", "Success rate", "Solved / tasks", "Paired peer gap", "Peer pairs / models"], data.axes.map(function (a) {
          return '<tr>' + th(a.name + (a.preliminary ? " · preliminary" : "")) + td(score(a.solved, a.n, a.repeat)) + td(esc(a.solved + "/" + a.n), true) + td(esc(diff(a.delta)), true) + td(esc(a.pairs + " / " + a.peers), true) + '</tr>';
        }), "tdb-profile-capabilities") : note("Capability definitions are unavailable.")) +
        '<div class="tdb-insight-examples-grid">' + examples(data.solved, "Standout successes") + examples(data.failed, "Missed tasks") + '</div>' +
        '<h3>Tested settings</h3>' + (efforts.length ? table(["Agent", "Effort", "Success rate", "Solved / tasks"], efforts.map(function (r) {
          return '<tr>' + th(T.agentLabel(r.agent)) + td(esc(r.effort || "default")) + td(score(r.solved, r.n, T.resultStats(state.context.day, r.model, r.scaffold || r.agent + (r.effort && r.effort !== "default" ? "@" + r.effort : "")))) + td(esc(r.solved + "/" + r.n), true) + '</tr>';
        })) : empty("No effort summaries were published for this model."));
      publish("Model profile: " + label(data.model), ["model", "capability", "solved", "evaluated", "rate", "rate_sd", "rate_runs", "paired_peer_gap", "peer_pairs", "peer_models", "preliminary"], data.axes.map(function (a) { return [data.model, a.name, a.solved, a.n, a.rate, a.repeat ? a.repeat.sd : null, a.repeat ? a.repeat.runs : null, a.delta, a.pairs, a.peers, a.preliminary]; }), [scope, "Peer differences use paired tasks. Effort summaries may use different task sets."]);
    }
    function loadDetails(date) {
      if (detailCache.has(date)) return detailCache.get(date);
      var promise = T.getData("data/run-details/index.json").then(function (index) {
        if (!index || index.schema !== "tdb-run-details-index-v1" || !Array.isArray(index.dates)) throw new Error("Invalid run-details index");
        if (!index.dates.includes(date)) return null;
        return T.getData("data/run-details/" + encodeURIComponent(date) + ".json");
      });
      detailCache.set(date, promise); return promise;
    }
    function metricDefinition() {
      if (state.metric === "cost") return { prefix: "cost", mean: "meanCost", label: "Cost", unit: "USD", exportMean: "mean_cost_usd" };
      if (state.metric === "tools") return { prefix: "tool", mean: "meanTools", label: "Tool calls", unit: "tool calls", exportMean: "mean_tool_calls" };
      return { prefix: "command", mean: "meanCommands", label: "Commands", unit: "commands", exportMean: "mean_commands" };
    }
    function successBounds(row, prefix) {
      return T.scoreEstimate(row[prefix + "Solved"], row[prefix + "TaskN"], row[prefix + "Repeat"]) ||
        { p: null, sd: null, runs: null, lo: null, hi: null };
    }
    function scatter(rows) {
      var metric = metricDefinition(), cost = state.metric === "cost", prefix = metric.prefix;
      var points = rows.filter(function (r) { return r[metric.mean] !== null; });
      if (!points.length) return empty("Recorded " + metric.label.toLowerCase() + " are unavailable for these results.");
      var max = Math.max.apply(null, points.map(function (r) { return r[metric.mean]; })) || 1;
      var padding = window.getComputedStyle ? window.getComputedStyle(host) : {};
      var width = Math.max(280, (host.clientWidth || 880) - (parseFloat(padding.paddingLeft) || 0) - (parseFloat(padding.paddingRight) || 0));
      var left = 52, right = width - 20, span = right - left;
      var svg = '<svg viewBox="0 0 ' + width + ' 310" role="img" aria-label="Majority task accuracy versus mean ' + metric.label.toLowerCase() + ' per attempt on measured tasks. Exact values and coverage are in the table below.">';
      [0, 25, 50, 75, 100].forEach(function (tick) {
        var y = 250 - tick * 2.1;
        svg += '<line x1="' + left + '" y1="' + y + '" x2="' + right + '" y2="' + y + '" class="tdb-plot-grid"/><text x="' + (left - 10) + '" y="' + (y + 4) + '" text-anchor="end">' + tick + '%</text>';
      });
      (width < 480 ? [0, .5, 1] : [0, .25, .5, .75, 1]).forEach(function (part) { svg += '<text x="' + (left + part * span) + '" y="270" text-anchor="' + (part === 0 ? 'start' : part === 1 ? 'end' : 'middle') + '">' + esc(cost ? "$" + (max * part).toFixed(2) : (max * part).toFixed(1)) + '</text>'; });
      svg += '<text x="' + (width / 2) + '" y="298" text-anchor="middle">Mean ' + metric.label.toLowerCase() + ' per attempt' + (cost ? ' (USD)' : '') + '</text>';
      points.forEach(function (r) {
        var bounds = successBounds(r, prefix), x = (left + r[metric.mean] / max * span).toFixed(2);
        var description = label(r.model) + ", " + r.effort + ": " + pct(bounds.p) + " majority accuracy" +
          ", " + r[metric.mean].toFixed(3) + " " + metric.unit + " per attempt, " + r[prefix + "N"] + " recorded attempts, " + r[prefix + "TaskN"] + " unique tasks";
        svg += '<g tabindex="0" class="tdb-efficiency-point" aria-label="' + esc(description) + '"><circle cx="' + x + '" cy="' + (250 - bounds.p * 210).toFixed(2) + '" r="5"/><title>' + esc(description) + '</title></g>';
      });
      return '<div class="tdb-efficiency-plot">' + svg + '</svg></div>';
    }
    function efficiency() {
      var current = ++generation, context = state.context;
      host.innerHTML = empty("Loading published attempt measurements\u2026");
      publish("Efficiency", [], [], ["Attempt measurements are loading."]);
      loadDetails(context.day.date).then(function (details) {
        if (current !== generation || state.context.mode !== "efficiency") return;
        var data = efficiencyData(context.day, details, { query: context.query, agent: context.agent, effort: context.effort });
        if (!data.available) { failure(data.reason === "invalid" ? "Published attempt measurements could not be read. Reload the page or choose another date." : "Command and tool-call measurements were not published for this date."); return; }
        var rows = data.rows;
        efficiencyRows = rows;
        state.metric = efficiencyMetric(rows, state.metricExplicit ? state.metric : null);
        var metric = metricDefinition(), prefix = metric.prefix, cost = state.metric === "cost", page = T.pageSlice(rows, state.efficiencyPage, 25);
        state.efficiencyPage = page.page;
        var measured = rows.some(function (r) { return r[prefix + "N"] > 0; });
        var scope = "Means include passing and failed attempts. Accuracy uses tasks with recorded measurements. " + variationNote();
        var definition = "Commands count recorded terminal calls; a batch of shell commands counts once. Tool calls also include actions such as reading or editing files. Missing counts remain unavailable.";
        var controls = '<div class="tdb-insight-tools"><label><span>Metric</span><select data-insight="metric">' + [["commands", "Commands per attempt"], ["tools", "Tool calls per attempt"], ["cost", "Cost per attempt (USD)"]].map(function (item) { return '<option value="' + item[0] + '"' + (state.metric === item[0] ? " selected" : "") + '>' + item[1] + '</option>'; }).join("") + '</select></label></div>';
        host.innerHTML = controls + (measured ? scatter(rows) + table(["Model / setting", "Success rate", "Mean " + metric.label.toLowerCase() + " / attempt", "Recorded attempts", "Measured tasks"], page.items.map(function (r) {
            var n = r[prefix + "TaskN"], solved = r[prefix + "Solved"], mean = r[metric.mean], recorded = r[prefix + "N"];
            return '<tr><th scope="row">' + esc(label(r.model)) + '<small>' + esc(T.agentLabel(r.agent) + ", " + r.effort) + '</small></th>' + td(n ? score(solved, n, r[prefix + "Repeat"]) : esc("No records")) + td(esc(mean === null ? "Not published" : (cost ? "$" + mean.toFixed(4) : mean.toFixed(2))), true) + td(esc(recorded + " / " + r.n), true) + td(esc(n + " / " + r.taskN), true) + '</tr>';
          })) + '<div class="tdb-insight-pager"><span>' + esc((page.page - 1) * 25 + 1) + '\u2013' + esc(Math.min(page.page * 25, page.total)) + ' of ' + esc(page.total) + ' settings</span><button type="button" data-efficiency-page="-1"' + (page.page === 1 ? " disabled" : "") + '>Previous</button><button type="button" data-efficiency-page="1"' + (page.page * 25 >= page.total ? " disabled" : "") + '>Next</button></div>' : empty(rows.length ? "Recorded " + metric.label.toLowerCase() + " are unavailable for this date and selection." : "No published attempts match these model or setting filters."));
        var columns = ["model", "agent", "effort", "success_rate_all", "success_rate_all_sd", "success_rate_all_runs", "all_n", "all_tasks"];
        ["command", "tool", "cost"].forEach(function (key) { columns = columns.concat(["success_rate_" + key + "_subset", "success_rate_" + key + "_subset_sd", "success_rate_" + key + "_subset_runs", key === "command" ? "mean_commands" : key === "tool" ? "mean_tool_calls" : "mean_cost_usd", key + "_n", key + "_tasks"]); });
        publish("Efficiency: " + metric.label.toLowerCase() + " per attempt", columns, rows.map(function (r) {
          var values = [r.model, r.agent, r.effort, r.rate, r.repeat ? r.repeat.sd : null, r.repeat ? r.repeat.runs : null, r.n, r.taskN];
          ["command", "tool", "cost"].forEach(function (key) { var bounds = successBounds(r, key); values = values.concat([r[key + "Rate"], bounds.sd, bounds.runs, r[key === "command" ? "meanCommands" : key === "tool" ? "meanTools" : "meanCost"], r[key + "N"], r[key + "TaskN"]]); });
          return values;
        }), [scope, definition]);
        if (state.focusAfterRender) {
          var target = host.querySelector(state.focusAfterRender);
          if (target && target.disabled) target = host.querySelector('[data-efficiency-page]:not(:disabled)');
          if (target) target.focus({ preventScroll: true });
          state.focusAfterRender = "";
        }
      }).catch(function () { if (current === generation && state.context.mode === "efficiency") { detailCache.delete(context.day.date); failure("Attempt measurements could not be loaded. Reload the page or choose another date."); } });
    }
    function loadHistory() {
      var dates = (state.context.days || []).slice(0, 12), active = state.context.day;
      if (!dates.includes(active.date)) dates.push(active.date);
      return Promise.all(dates.map(function (date) {
        if (date === active.date) return Promise.resolve({ day: active });
        if (!historyCache.has(date)) historyCache.set(date, T.dayData(date).then(function (day) { return { day: day }; }).catch(function () { historyCache.delete(date); return { error: date }; }));
        return historyCache.get(date);
      }));
    }
    function history(models) {
      var current = ++generation;
      if (!models.length) { failure("Release comparisons need task-level results for the selected date. Choose another date."); return; }
      host.innerHTML = empty("Loading releases with task-level results…"); publish("Release comparison", [], [], ["Release data is loading."]);
      loadHistory().then(function (items) {
        if (current !== generation || state.context.mode !== "history") return;
        var days = items.filter(function (r) { return r.day && r.day.date !== state.context.day.date && T.taskGrid(r.day, state.context.site).available; }).map(function (r) { return r.day; });
        var errors = items.filter(function (r) { return r.error; }).length;
        if (!days.length) { failure(errors ? "Other release data could not be loaded. Reload the page to compare releases." : "No other recent release has task-level outcomes. Historical comparison is unavailable."); return; }
        if (!days.some(function (d) { return d.date === state.baseline; })) state.baseline = days[0].date;
        var before = days.find(function (d) { return d.date === state.baseline; });
        var compare = compareReleases(selectedDay(before), selectedDay(), state.context.site, state.model);
        var tools = modelTools(models, '<label><span>Baseline release</span><select data-insight="baseline">' + days.map(function (d) { return '<option value="' + esc(d.date) + '"' + (d.date === state.baseline ? " selected" : "") + '>' + esc(d.date) + '</option>'; }).join("") + '</select></label>' + nav("compare", "Compare models", state.model));
        var coverage = "Showing up to 12 recent releases with published matrices. " + (errors ? errors + " releases could not be loaded. " : "") + "Same task IDs and published setting are required; task revisions are not independently verified.";
        if (!compare.available) {
          var reason = compare.reason === "settings" ? "These releases use different or unspecified settings. Outcome changes cannot be compared." : "This model has no task outcomes in the baseline release. Choose another model or baseline.";
          host.innerHTML = tools + (errors ? note(errors + " releases could not be loaded.") : "") + empty(reason); publish("Release comparison unavailable", [], [], [reason]); return;
        }
        var groups = Object.assign({}, compare.groups, { added: compare.added, removed: compare.removed });
        var labels = { b_only: "Newly solved", a_only: "No longer solved", both: "Solved in both", neither: "Unsolved in both", added: "Added tasks", removed: "Removed tasks" };
        if (!Object.prototype.hasOwnProperty.call(labels, state.group)) state.group = "b_only";
        var changedSet = state.group === "added" || state.group === "removed";
        var tasks = taskList(groups[state.group], changedSet ? ["Available outcome"] : [before.date, state.context.day.date], function (t) {
          function text(v) { return v === 1 ? "Majority solved" : v === 0 ? "Majority not solved" : "Not evaluated"; }
          return changedSet ? [text(t.outcome)] : [text(t.a), text(t.b)];
        });
        var scope = compare.n + " paired evaluated tasks from " + compare.shared + " shared IDs. " + compare.missing.length + " shared tasks excluded for missing outcomes. Current − baseline: " + diff(compare.delta === null ? null : -compare.delta) + ".";
        scope += " " + variationNote();
        host.innerHTML = tools + (errors ? note(errors + " releases could not be loaded.") : "") + note(compare.n + " shared tasks") + '<div class="tdb-pair-scores"><div><span>' + esc(before.date) + '</span>' + score(compare.a.solved, compare.n, compare.a.repeat) + '</div><div><span>' + esc(state.context.day.date) + '</span>' + score(compare.b.solved, compare.n, compare.b.repeat) + '</div></div>' +
          groupButtons(groups, labels) + tasks.html;
        publish("Release comparison: " + label(state.model) + ": " + labels[state.group], ["task_id", "title", "baseline", "current", "baseline_outcome", "current_outcome", "group"], tasks.tasks.map(function (t) { return [t.id, t.title, before.date, state.context.day.date, state.group === "removed" ? t.outcome : t.a, state.group === "added" ? t.outcome : t.b, state.group]; }), [scope, coverage], [scoreSummary(before.date, compare.a), scoreSummary(state.context.day.date, compare.b)]);
      });
    }
    function render() {
      generation++;
      if (!state.context) return;
      var matrices = state.context.day.matrices || {};
      if (!matrices[state.scaffold]) state.scaffold = (state.context.day.matrix || {}).scaffold || "";
      var models = sourceModels(); setSelections(models);
      if (state.context.mode === "compare") comparison(models);
      else if (state.context.mode === "profile") profile(models);
      else if (state.context.mode === "efficiency") efficiency();
      else if (state.context.mode === "history") history(models);
    }
    function updateUrl() {
      try {
        var url = new URL(window.location.href);
        if (["profile", "history"].includes(state.context.mode)) url.searchParams.set("model", state.model);
        if (state.context.mode === "compare") { url.searchParams.delete("compare"); state.compare.forEach(function (model) { if (model) url.searchParams.append("compare", model); }); }
        if (state.context.mode === "history" && state.baseline) url.searchParams.set("baseline", state.baseline);
        if (state.context.mode === "efficiency") {
          if (state.metricExplicit) url.searchParams.set("metric", state.metric); else url.searchParams.delete("metric");
          if (state.efficiencyPage > 1) url.searchParams.set("efficiency-page", state.efficiencyPage); else url.searchParams.delete("efficiency-page");
        }
        if (["compare", "history"].includes(state.context.mode)) url.searchParams.set("outcome", state.group);
        if (state.context.day.matrices && state.context.mode !== "efficiency") {
          var parts = state.scaffold.split("@"); url.searchParams.set("agent", parts[0]); url.searchParams.set("effort", parts[1] || "default");
        }
        window.history.replaceState(window.history.state, "", url);
      } catch (error) { /* Local previews may not support URL history. */ }
    }
    host.addEventListener("change", function (event) {
      var key = event.target.dataset.insight;
      if (!key) return;
      if (key === "first") state.compare[0] = event.target.value;
      else if (key === "second") { state.compare[1] = event.target.value; if (state.compare[0] === state.compare[1]) state.compare[0] = sourceModels().find(function (m) { return m !== state.compare[1]; }); }
      else if (["model", "baseline", "metric", "scaffold"].includes(key)) state[key] = event.target.value;
      else return;
      if (key === "metric") { state.metricExplicit = true; state.efficiencyPage = 1; }
      if (key === "scaffold" && callbacks.onSetting) callbacks.onSetting(state.scaffold);
      state.page = 1; render(); updateUrl();
      var input = host.querySelector('[data-insight="' + key + '"]'); if (input) input.focus({ preventScroll: true });
    });
    host.addEventListener("click", function (event) {
      var button = event.target.closest("button"); if (!button) return;
      if (button.dataset.insightView) {
        if (button.dataset.insightModel) { state.model = button.dataset.insightModel; state.compare[0] = state.model; }
        if (callbacks.onNavigate) callbacks.onNavigate(button.dataset.insightView, state.model); return;
      }
      var selector;
      if (button.dataset.insightGroup) { state.group = button.dataset.insightGroup; state.page = 1; selector = '[data-insight-group="' + state.group + '"]'; }
      else if (button.dataset.insightPage) { state.page += Number(button.dataset.insightPage); selector = '[data-insight-page="' + button.dataset.insightPage + '"]'; }
      else if (button.dataset.efficiencyPage) {
        state.efficiencyPage += Number(button.dataset.efficiencyPage);
        selector = '[data-efficiency-page="' + button.dataset.efficiencyPage + '"]'; state.focusAfterRender = selector;
      }
      else return;
      render();
      var next = host.querySelector(selector); if (next) next.focus({ preventScroll: true });
    });
    if (window.ResizeObserver) {
      var plotWidth = host.clientWidth;
      new window.ResizeObserver(function () {
        var width = host.clientWidth;
        if (!width || width === plotWidth) return;
        plotWidth = width;
        var plot = host.querySelector('.tdb-efficiency-plot');
        if (plot && state.context && state.context.mode === "efficiency") plot.outerHTML = scatter(efficiencyRows);
      }).observe(host);
    }
    return {
      update: function (context) {
        if (!state.context || state.context.day.date !== context.day.date || state.context.mode !== context.mode || state.context.query !== context.query) state.page = 1;
        if (state.context && (state.context.day.date !== context.day.date || state.context.query !== context.query || state.context.agent !== context.agent || state.context.effort !== context.effort)) state.efficiencyPage = 1;
        state.context = context; render(); updateUrl();
      },
      readUrl: function () {
        try { var p = new URL(window.location.href).searchParams; state.model = p.get("model") || ""; state.compare = p.getAll("compare").slice(0, 2); state.baseline = p.get("baseline") || ""; state.metric = efficiencyMetric([], p.get("metric")); state.metricExplicit = ["commands", "tools", "cost"].includes(p.get("metric")); state.efficiencyPage = /^\d+$/.test(p.get("efficiency-page") || "") ? Math.max(1, Number(p.get("efficiency-page"))) : 1; state.group = p.get("outcome") || "a_only"; state.scaffold = (p.get("agent") || "") + (p.get("effort") && p.get("effort") !== "default" ? "@" + p.get("effort") : ""); } catch (e) { /* Use defaults. */ }
      },
      select: function (model) { state.model = model; state.compare[0] = model; state.page = 1; },
      snapshot: function () { return snapshot; },
      clear: function (message) { generation++; snapshot = null; host.innerHTML = empty(message); }
    };
  }
  Object.assign(T, { compareModels: compareModels, modelProfile: modelProfile, compareReleases: compareReleases,
    efficiencyData: efficiencyData, efficiencyMetric: efficiencyMetric, createInsights: createInsights });
})();

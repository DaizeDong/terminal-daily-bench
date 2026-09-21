/* Daily task outcomes. Every cell keeps its original model and task index. */
(function () {
  "use strict";
  var T = window.TDB;
  var own = function (o, k) { return Object.prototype.hasOwnProperty.call(o, k); };
  var label = function (model) { return T.modelLabel(model); };
  var compare = function (a, b) { return String(a).localeCompare(String(b)); };

  function taskGrid(day, site) {
    var matrix = day && day.matrix;
    var unavailable = function (reason) {
      return { available: false, reason: reason, date: day && day.date, rows: [], tasks: [] };
    };
    if (!matrix || !Array.isArray(matrix.tasks) || !Array.isArray(matrix.rows) ||
        !matrix.tasks.length || !matrix.rows.length) return unavailable("missing");
    var ids = new Set(), models = new Set();
    if (matrix.tasks.some(function (id) {
      if (typeof id !== "string" || !id || ids.has(id)) return true;
      ids.add(id); return false;
    })) return unavailable("invalid");
    if (matrix.rows.some(function (r) {
      if (!r || typeof r.model !== "string" || !r.model || models.has(r.model) ||
          !Array.isArray(r.g) || r.g.length !== matrix.tasks.length) return true;
      models.add(r.model);
      for (var i = 0; i < r.g.length; i++) {
        if (r.g[i] !== 0 && r.g[i] !== 1 && r.g[i] !== null) return true;
      }
      return false;
    })) return unavailable("invalid");
    var catalogue = Object.create(null);
    ((site && site.tasks) || []).forEach(function (task) {
      if (task && typeof task.id === "string") catalogue[task.id] = task;
    });
    return {
      available: true, date: day.date, scaffold: matrix.scaffold || "", aggregation: day.aggregation || null,
      rows: matrix.rows.map(function (r) { return { model: r.model, values: r.g.slice() }; }),
      tasks: matrix.tasks.map(function (id, i) {
        var task = own(catalogue, id) ? catalogue[id] : {};
        return { id: id, index: i, title: T.cleanTaskTitle ? T.cleanTaskTitle(task.title) : task.title || ("Task " + (i + 1)),
          project: task.repo || "", href: own(catalogue, id) ?
            (T.routeUrl ? T.routeUrl("registry/" + encodeURIComponent(id) + "/") : "../registry/" + encodeURIComponent(id) + "/") : null };
      })
    };
  }

  function tally(values) {
    var solved = 0, n = 0;
    values.forEach(function (value) {
      if (value === 0 || value === 1) { n++; solved += value; }
    });
    return { solved: solved, n: n, rate: n ? solved / n : null };
  }

  function rankBySolved(items, key) {
    var previous = null, rank = null;
    items.slice().sort(function (a, b) {
      return (b.n > 0) - (a.n > 0) || b.solved - a.solved || compare(a[key], b[key]);
    }).forEach(function (item, i) {
      if (!item.n) { item.rank = null; return; }
      if (item.solved !== previous) rank = i + 1;
      item.rank = rank; previous = item.solved;
    });
  }

  function taskView(grid, opts) {
    opts = opts || {};
    if (!grid || !grid.available) return { rows: [], tasks: [] };
    var modelQuery = String(opts.modelQuery || "").trim().toLowerCase();
    var taskQuery = String(opts.taskQuery || "").trim().toLowerCase();
    var rows = grid.rows.filter(function (r) {
      return (r.model + " " + label(r.model)).toLowerCase().indexOf(modelQuery) >= 0;
    });
    var tasks = grid.tasks.filter(function (task) {
      return (task.title + " " + task.project + " " + task.id).toLowerCase().indexOf(taskQuery) >= 0;
    });
    var measuredRows = rows.map(function (r) {
      return Object.assign({}, r, tally(tasks.map(function (task) { return r.values[task.index]; })));
    });
    var measuredTasks = tasks.map(function (task) {
      return Object.assign({}, task, tally(rows.map(function (r) { return r.values[task.index]; })));
    });
    rankBySolved(measuredRows, "model"); rankBySolved(measuredTasks, "id");
    measuredRows.sort(function (a, b) {
      if (!!a.n !== !!b.n) return a.n ? -1 : 1;
      var delta = opts.modelOrder === "name" ? compare(label(a.model), label(b.model)) :
        opts.modelOrder === "rate" ? b.rate - a.rate : b.solved - a.solved;
      return delta || compare(a.model, b.model);
    });
    measuredTasks.sort(function (a, b) {
      if (!!a.n !== !!b.n) return a.n ? -1 : 1;
      var delta = opts.taskOrder === "name" ? compare(a.title, b.title) :
        opts.taskOrder === "hardest" ? a.rate - b.rate : b.solved - a.solved;
      return delta || compare(a.id, b.id);
    });
    return { rows: measuredRows, tasks: measuredTasks };
  }

  function createTaskExplorer(host, onChange) {
    var esc = T.esc;
    var state = { grid: null, view: { rows: [], tasks: [] }, modelQuery: "", taskQuery: "",
      modelOrder: "solved", taskOrder: "solved", display: "heatmap", zoom: "overview",
      modelPage: 1, taskPage: 1, rankPage: 1, selected: null };
    var geometry = null, chartRows = [], chartTasks = [], frozen = false;
    var publishedDay = null, publishedSite = null;
    var stateKeys = { taskQuery: "task-query", modelOrder: "model-order", taskOrder: "task-order",
      display: "layout", zoom: "zoom", modelPage: "model-page", taskPage: "task-page", rankPage: "rank-page" };
    var defaults = { taskQuery: "", modelOrder: "solved", taskOrder: "solved", display: "heatmap",
      zoom: "overview", modelPage: 1, taskPage: 1, rankPage: 1 };
    function restore() {
      var p = new URLSearchParams(window.location.search);
      Object.keys(stateKeys).forEach(function (key) {
        var value = p.get(stateKeys[key]);
        if (key.indexOf("Page") >= 0) state[key] = /^\d+$/.test(value || "") ? Math.max(1, Number(value)) : 1;
        else state[key] = value || defaults[key];
      });
      if (["heatmap", "ranking"].indexOf(state.display) < 0) state.display = "heatmap";
      if (["overview", "detail"].indexOf(state.zoom) < 0) state.zoom = "overview";
      if (["solved", "rate", "name"].indexOf(state.modelOrder) < 0) state.modelOrder = "solved";
      if (["solved", "hardest", "name"].indexOf(state.taskOrder) < 0) state.taskOrder = "solved";
      state.selected = p.get("selected-model") && p.get("selected-task") ?
        { model: p.get("selected-model"), id: p.get("selected-task") } : null;
      frozen = !!state.selected;
    }
    function save(push) {
      if (host.hidden) return;
      var u = new URL(window.location.href);
      Object.keys(stateKeys).forEach(function (key) {
        if (state[key] === defaults[key]) u.searchParams.delete(stateKeys[key]);
        else u.searchParams.set(stateKeys[key], state[key]);
      });
      ["model", "task"].forEach(function (key) {
        if (frozen && state.selected) u.searchParams.set("selected-" + key, state.selected[key === "task" ? "id" : key]);
        else u.searchParams.delete("selected-" + key);
      });
      if (publishedDay && publishedDay.matrices && state.grid && state.grid.scaffold) {
        var parts = state.grid.scaffold.split("@");
        u.searchParams.set("agent", parts[0]); u.searchParams.set("effort", parts[1] || "default");
      }
      if (T.canonicalUrl) u = T.canonicalUrl(u.href);
      if (u.href !== window.location.href) window.history[push ? "pushState" : "replaceState"](null, "", u);
      document.dispatchEvent(new CustomEvent("tdb:results"));
    }
    host.innerHTML =
      '<div class="tdb-explorer-tools">' +
        '<div class="tdb-explorer-switch" role="group" aria-label="Task results layout">' +
          '<button type="button" data-layout="heatmap" aria-pressed="true">Heatmap</button>' +
          '<button type="button" data-layout="ranking" aria-pressed="false">Task ranking</button></div>' +
        '<label><span class="sr-only">Search tasks or projects</span><input type="search" ' +
          'data-control="taskQuery" placeholder="Search tasks or projects" autocomplete="off"></label>' +
        '<label><span class="sr-only">Model order</span><select data-control="modelOrder" aria-label="Model order">' +
          '<option value="solved">Models: most solved</option><option value="rate">Models: highest rate</option>' +
          '<option value="name">Models: name</option></select></label>' +
        '<label><span class="sr-only">Task order</span><select data-control="taskOrder" aria-label="Task order">' +
          '<option value="solved">Tasks: most solved</option><option value="hardest">Tasks: lowest success rate</option>' +
          '<option value="name">Tasks: name</option></select></label>' +
        '<label data-task-setting-wrap hidden><span class="sr-only">Evaluation setting</span><select data-task-setting aria-label="Evaluation setting"></select></label>' +
        '<button type="button" data-action="reset" hidden>Reset</button>' +
      '</div><p class="tdb-explorer-scope"></p>' +
      '<div class="tdb-explorer-content"></div>' +
      '<div class="tdb-explorer-selection" role="status" aria-live="polite" hidden></div>' +
      '<div class="tdb-heatmap-tooltip" role="tooltip" hidden></div>';
    var content = host.querySelector(".tdb-explorer-content");
    var scope = host.querySelector(".tdb-explorer-scope");
    var selection = host.querySelector(".tdb-explorer-selection");
    var tooltip = host.querySelector(".tdb-heatmap-tooltip");

    function settings(includeMethod) {
      var parts = String(state.grid.scaffold).split("@");
      var aggregation = state.grid.aggregation;
      return T.agentLabel(parts[0] || "Published agent") + " / " + (parts[1] || "default") +
        (includeMethod && aggregation && aggregation.method === "strict_majority" ? ", strict majority across " + aggregation.trials_per_cell + " trials per task" : "");
    }
    function resetPages() { state.modelPage = state.taskPage = state.rankPage = 1; state.selected = null; frozen = false; }
    function pager(kind, page, size, total, noun) {
      var pages = Math.max(1, Math.ceil(total / size));
      if (pages < 2) return "";
      return '<div class="tdb-explorer-pager" role="group" aria-label="' + noun + ' pages">' +
        '<span>' + ((page - 1) * size + 1) + '&ndash;' + Math.min(page * size, total) + ' of ' + total + ' ' + noun.toLowerCase() + '</span>' +
        '<button type="button" data-page="' + kind + '" data-step="-1"' + (page <= 1 ? ' disabled' : '') +
          ' aria-label="Previous ' + noun.toLowerCase() + '">Previous</button>' +
        '<button type="button" data-page="' + kind + '" data-step="1"' + (page >= pages ? ' disabled' : '') +
          ' aria-label="Next ' + noun.toLowerCase() + '">Next</button></div>';
    }
    function showSelection(row, task, pin) {
      if (!row || !task) return;
      state.selected = { model: row.model, id: task.id };
      if (pin) frozen = true;
      selection.hidden = !frozen;
      var value = row.values[task.index];
      var outcome = value === 1 ? "Solved" : value === 0 ? "Not solved" : "Not evaluated";
      var title = task.href ? '<a href="' + esc(task.href) + '">' + esc(task.title) + '</a>' : esc(task.title);
      selection.innerHTML = '<div><strong>' + esc(label(row.model)) + '</strong><span class="tdb-outcome" data-outcome="' +
        (value === null ? "missing" : value) + '">' + outcome + '</span></div>' +
        '<p>' + title + (task.project ? '<span class="tdb-explorer-project">' + esc(task.project) + '</span>' : '') + '</p>' +
        '<p class="tdb-explorer-detail">' + task.solved + '/' + task.n + ' models solved' +
          (frozen ? ' <button type="button" data-action="unpin">Clear selection</button>' : '') + '</p>';
      var canvas = content.querySelector("canvas");
      if (canvas) canvas.setAttribute("aria-label", label(row.model) + ": " + task.title + ". " + outcome +
        ". Use arrow keys to explore, Enter to keep this selection.");
      if (pin) save(false);
    }
    function fitText(ctx, text, width) {
      if (ctx.measureText(text).width <= width) return text;
      while (text.length && ctx.measureText(text + "…").width > width) text = text.slice(0, -1);
      return text + "…";
    }
    function paintChart() {
      var canvas = content.querySelector("canvas");
      if (!canvas || host.hidden || !chartRows.length || !chartTasks.length) return;
      var wrapper = canvas.parentElement, ctx = canvas.getContext("2d");
      var compact = wrapper.clientWidth < 640;
      var width = Math.max(compact ? 620 : 760, wrapper.clientWidth);
      var left = compact ? 180 : 270, top = 94, rowHeight = 27;
      var countX = compact ? 126 : 208, nameWidth = compact ? 106 : 188;
      var height = top + chartRows.length * rowHeight + 14;
      var dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(width * dpr); canvas.height = Math.round(height * dpr);
      canvas.style.width = width + "px"; canvas.style.height = height + "px";
      ctx.scale(dpr, dpr);
      var dark = document.documentElement.classList.contains("dark");
      var colors = dark ? { ink: "#e2e9f5", muted: "#a1aec5", paper: "#131d31", solved: "#93b4ff", failed: "#34445e", line: "#28374f", missing: "#131d31" } :
        { ink: "#18243b", muted: "#61708b", paper: "#fcfdff", solved: "#315aba", failed: "#e1e8f2", line: "#ccd6e6", missing: "#fcfdff" };
      var cellWidth = (width - left - 12) / chartTasks.length;
      geometry = { width: width, height: height, left: left, top: top, rowHeight: rowHeight, cellWidth: cellWidth };
      ctx.fillStyle = colors.paper; ctx.fillRect(0, 0, width, height);
      ctx.fillStyle = colors.muted; ctx.font = '12px "Geist", sans-serif';
      ctx.fillText("Model", 8, top - 12); ctx.fillText("Solved", countX, top - 12);
      ctx.fillText("Models solving each task", left, 15);
      var population = state.view.rows.length;
      chartTasks.forEach(function (task, j) {
        var x = left + j * cellWidth, bar = population ? 40 * task.solved / population : 0;
        ctx.fillStyle = colors.solved;
        if (bar) ctx.fillRect(x, 62 - bar, Math.max(1, cellWidth - (cellWidth >= 5 ? 1 : 0)), bar);
      });
      ctx.fillStyle = colors.muted; ctx.fillText("0", left - 14, 64);
      ctx.fillText(String(population), left - 24, 30);
      var tickStep = Math.max(1, Math.ceil(chartTasks.length / 8));
      chartTasks.forEach(function (task, j) {
        if (j % tickStep === 0) ctx.fillText(String((state.taskPage - 1) * (state.zoom === "detail" ? 80 : 500) + j + 1), left + j * cellWidth, 81);
      });
      chartRows.forEach(function (row, i) {
        var y = top + i * rowHeight;
        ctx.fillStyle = colors.ink; ctx.font = '13px "Geist", sans-serif';
        ctx.fillText(fitText(ctx, label(row.model), nameWidth), 8, y + 18);
        ctx.font = '12px "Google Sans Code", monospace'; ctx.fillStyle = colors.muted;
        ctx.fillText(row.solved + "/" + row.n, countX, y + 18);
        chartTasks.forEach(function (task, j) {
          var value = row.values[task.index], x = left + j * cellWidth;
          ctx.fillStyle = value === 1 ? colors.solved : value === 0 ? colors.failed : colors.missing;
          ctx.fillRect(x, y + 3, Math.max(1, cellWidth - (cellWidth >= 5 ? 1 : 0)), rowHeight - 6);
          if (value === null) {
            ctx.strokeStyle = colors.line; ctx.lineWidth = 1;
            ctx.beginPath(); ctx.moveTo(x, y + rowHeight - 3); ctx.lineTo(x + cellWidth, y + 3); ctx.stroke();
          }
        });
      });
      if (state.selected) {
        var ri = chartRows.findIndex(function (row) { return row.model === state.selected.model; });
        var ti = chartTasks.findIndex(function (task) { return task.id === state.selected.id; });
        if (ri >= 0 && ti >= 0) {
          ctx.strokeStyle = colors.ink; ctx.lineWidth = 2;
          ctx.strokeRect(left + ti * cellWidth - 1, top + ri * rowHeight + 2, Math.max(cellWidth, 3), rowHeight - 4);
        }
      }
    }
    function render() {
      state.view = taskView(state.grid, state);
      if (state.selected && (!state.view.rows.some(function (r) { return r.model === state.selected.model; }) ||
          !state.view.tasks.some(function (t) { return t.id === state.selected.id; }))) {
        state.selected = null; frozen = false;
      }
      if (typeof onChange === "function") onChange({ models: state.view.rows.length,
        tasks: state.view.tasks.length, available: !!(state.grid && state.grid.available) });
      geometry = null;
      selection.innerHTML = "";
      selection.hidden = true;
      tooltip.hidden = true;
      host.querySelectorAll("[data-layout]").forEach(function (button) {
        button.setAttribute("aria-pressed", String(button.dataset.layout === state.display));
      });
      host.querySelector('[data-control="modelOrder"]').parentElement.hidden = state.display === "ranking";
      host.querySelector('[data-action="reset"]').hidden = !state.taskQuery && state.taskOrder === "solved" && state.modelOrder === "solved";
      if (!state.grid || !state.grid.available) {
        scope.textContent = "";
        content.innerHTML = '<p class="tdb-empty">' + (state.grid && state.grid.reason === "invalid" ?
          'These task results could not be read. Please try reloading the page.' :
          'Task-level results were not published for this date. Choose another date to explore the heatmap.') + '</p>';
        return;
      }
      scope.textContent = settings();
      if (!state.view.rows.length || !state.view.tasks.length) {
        content.innerHTML = '<p class="tdb-empty">No matching results. Try a different model or task search.</p>';
        return;
      }
      if (state.display === "ranking") {
        var page = T.pageSlice(state.view.tasks, state.rankPage, 25); state.rankPage = page.page;
        content.innerHTML = '<div class="tdb-explorer-table-scroll"><table class="tdb-task-ranking"><thead><tr>' +
          '<th scope="col">Task</th><th scope="col">Models solved</th><th scope="col">Success rate</th></tr></thead><tbody>' +
          page.items.map(function (task) {
            var title = task.href ? '<a href="' + esc(task.href) + '">' + esc(task.title) + '</a>' : esc(task.title);
            return '<tr><th scope="row">' + title + '<span class="tdb-explorer-project">' + esc(task.project) + '</span></th>' +
              '<td class="tabular-nums" data-label="Models solved">' + task.solved + '/' + task.n + '</td><td>' + T.scoreCell(task.solved, task.n) + '</td></tr>';
          }).join("") + '</tbody></table></div>' + pager("rankPage", page.page, 25, page.total, "Tasks");
        return;
      }
      var rowPage = T.pageSlice(state.view.rows, state.modelPage, 40); state.modelPage = rowPage.page;
      var taskSize = state.zoom === "detail" ? 80 : 500;
      // pageSlice deliberately caps general tables at 100; the dense overview has its own bounded window.
      var taskPages = Math.max(1, Math.ceil(state.view.tasks.length / taskSize));
      state.taskPage = Math.min(state.taskPage, taskPages);
      chartRows = rowPage.items;
      chartTasks = state.view.tasks.slice((state.taskPage - 1) * taskSize, state.taskPage * taskSize);
      content.innerHTML = '<div class="tdb-heatmap-key"><span><i data-outcome="1"></i>Solved</span>' +
        '<span><i data-outcome="0"></i>Not solved</span><span><i data-outcome="missing"></i>Not evaluated</span>' +
        '<div role="group" aria-label="Heatmap density"><button type="button" data-zoom="overview" aria-pressed="' + (state.zoom === "overview") + '">Overview</button>' +
        '<button type="button" data-zoom="detail" aria-pressed="' + (state.zoom === "detail") + '">Detail</button></div></div>' +
        '<div class="tdb-heatmap-scroll"><canvas tabindex="0" role="img" aria-label="Model by task outcomes. Use arrow keys to explore cells; Enter keeps a selection."></canvas></div>' +
        '<div class="tdb-explorer-pages">' + pager("modelPage", state.modelPage, 40, state.view.rows.length, "Models") +
          pager("taskPage", state.taskPage, taskSize, state.view.tasks.length, "Tasks") + '</div>' +
        '<p class="tdb-explorer-help">Each column is a task. Bars count the models that solved it. Select a cell for details.</p>';
      paintChart();
      if (state.selected) {
        var selectedRow = state.view.rows.find(function (r) { return r.model === state.selected.model; });
        var selectedTask = state.view.tasks.find(function (t) { return t.id === state.selected.id; });
        if (selectedRow && selectedTask) showSelection(selectedRow, selectedTask, frozen);
      }
    }
    function point(event) {
      var canvas = event.target.closest("canvas");
      if (!canvas || !geometry) return null;
      var rect = canvas.getBoundingClientRect();
      var x = (event.clientX - rect.left) * geometry.width / rect.width;
      var y = (event.clientY - rect.top) * geometry.height / rect.height;
      var column = Math.floor((x - geometry.left) / geometry.cellWidth);
      var row = Math.floor((y - geometry.top) / geometry.rowHeight);
      return row >= 0 && row < chartRows.length && column >= 0 && column < chartTasks.length ? { row: row, column: column } : null;
    }
    function revealCell(row, column) {
      var canvas = content.querySelector("canvas");
      if (!canvas || !geometry) return;
      var wrapper = canvas.parentElement, x = geometry.left + column * geometry.cellWidth;
      if (x < wrapper.scrollLeft + 8) wrapper.scrollLeft = Math.max(0, x - 8);
      else if (x + geometry.cellWidth > wrapper.scrollLeft + wrapper.clientWidth - 8) {
        wrapper.scrollLeft = x + geometry.cellWidth - wrapper.clientWidth + 8;
      }
      var y = canvas.getBoundingClientRect().top + geometry.top + row * geometry.rowHeight;
      if (y < 80) window.scrollBy(0, y - 80);
      else if (y + geometry.rowHeight > window.innerHeight - (selection.hidden ? 24 : selection.offsetHeight + 28)) {
        window.scrollBy(0, y + geometry.rowHeight - window.innerHeight + (selection.hidden ? 24 : selection.offsetHeight + 28));
      }
    }
    host.addEventListener("input", function (event) {
      if (event.target.dataset.control !== "taskQuery") return;
      state.taskQuery = event.target.value; resetPages(); render(); save(false);
    });
    host.addEventListener("change", function (event) {
      if (event.target.hasAttribute("data-task-setting")) {
        var setting = event.target.value, at = setting.lastIndexOf("@"), u = new URL(window.location.href);
        u.searchParams.set("agent", at < 0 ? setting : setting.slice(0, at));
        if (at >= 0) u.searchParams.set("effort", setting.slice(at + 1)); else u.searchParams.delete("effort");
        window.history.pushState(null, "", T.canonicalUrl ? T.canonicalUrl(u.href) : u);
        window.dispatchEvent(new PopStateEvent("popstate")); return;
      }
      var key = event.target.dataset.control;
      if (key !== "modelOrder" && key !== "taskOrder") return;
      state[key] = event.target.value; resetPages(); render(); save(false);
    });
    host.addEventListener("click", function (event) {
      var hit = point(event);
      if (hit) { tooltip.hidden = true; showSelection(chartRows[hit.row], chartTasks[hit.column], true); paintChart(); revealCell(hit.row, hit.column); return; }
      var button = event.target.closest("button");
      if (!button) return;
      if (button.dataset.layout) { state.display = button.dataset.layout; state.selected = null; }
      else if (button.dataset.zoom) { state.zoom = button.dataset.zoom; state.taskPage = 1; state.selected = null; }
      else if (button.dataset.page) { state[button.dataset.page] += Number(button.dataset.step); state.selected = null; }
      else if (button.dataset.action === "reset") {
        state.taskQuery = ""; state.modelOrder = state.taskOrder = "solved"; resetPages();
        host.querySelector('[data-control="taskQuery"]').value = "";
        host.querySelector('[data-control="modelOrder"]').value = "solved";
        host.querySelector('[data-control="taskOrder"]').value = "solved";
      } else if (button.dataset.action === "unpin") { frozen = false; state.selected = null; }
      else return;
      if (!state.selected) frozen = false;
      var focusSelector = button.dataset.layout ? '[data-layout="' + state.display + '"]' :
        button.dataset.zoom ? '[data-zoom="' + state.zoom + '"]' :
        button.dataset.page ? '[data-page="' + button.dataset.page + '"][data-step="' + button.dataset.step + '"]' : null;
      render(); save(true);
      if (focusSelector) {
        var nextFocus = host.querySelector(focusSelector);
        if (nextFocus && nextFocus.disabled && button.dataset.page) {
          nextFocus = host.querySelector('[data-page="' + button.dataset.page + '"]:not(:disabled)');
        }
        if (nextFocus) nextFocus.focus({ preventScroll: true });
      }
    });
    host.addEventListener("pointermove", function (event) {
      if (frozen || event.pointerType === "touch") return;
      var hit = point(event);
      if (!hit) { tooltip.hidden = true; return; }
      var row = chartRows[hit.row], task = chartTasks[hit.column], value = row.values[task.index];
      tooltip.textContent = label(row.model) + " · " + (value === 1 ? "Solved" : value === 0 ? "Not solved" : "Not evaluated") + "\n" + task.title;
      tooltip.hidden = false;
      tooltip.style.left = Math.max(12, Math.min(event.clientX + 16, window.innerWidth - Math.min(360, window.innerWidth - 24) - 12)) + "px";
      tooltip.style.top = Math.max(12, Math.min(event.clientY + 16, window.innerHeight - tooltip.offsetHeight - 12)) + "px";
      if (state.selected && state.selected.model === chartRows[hit.row].model && state.selected.id === chartTasks[hit.column].id) return;
      showSelection(chartRows[hit.row], chartTasks[hit.column], false); paintChart();
    });
    host.addEventListener("pointerleave", function () { tooltip.hidden = true; });
    host.addEventListener("focusin", function (event) {
      if (event.target.tagName === "CANVAS" && !state.selected && chartRows.length && chartTasks.length) {
        showSelection(chartRows[0], chartTasks[0], false); paintChart();
      }
    });
    host.addEventListener("keydown", function (event) {
      if (event.target.tagName !== "CANVAS" || !chartRows.length || !chartTasks.length) return;
      if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End", "Enter", "Escape"].indexOf(event.key) < 0) return;
      event.preventDefault();
      tooltip.hidden = true;
      if (event.key === "Escape") { frozen = false; state.selected = null; selection.innerHTML = ""; selection.hidden = true; paintChart(); save(false); return; }
      var row = state.selected ? chartRows.findIndex(function (r) { return r.model === state.selected.model; }) : 0;
      var column = state.selected ? chartTasks.findIndex(function (t) { return t.id === state.selected.id; }) : 0;
      row = Math.max(0, row); column = Math.max(0, column);
      if (event.key === "ArrowUp") row--; if (event.key === "ArrowDown") row++;
      if (event.key === "ArrowLeft") column--; if (event.key === "ArrowRight") column++;
      if (event.key === "Home") column = 0; if (event.key === "End") column = chartTasks.length - 1;
      row = Math.max(0, Math.min(chartRows.length - 1, row)); column = Math.max(0, Math.min(chartTasks.length - 1, column));
      showSelection(chartRows[row], chartTasks[column], true); paintChart(); revealCell(row, column);
    });
    if (typeof ResizeObserver !== "undefined") new ResizeObserver(paintChart).observe(host);
    if (typeof MutationObserver !== "undefined") new MutationObserver(paintChart).observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return {
      update: function (day, site, query) {
        publishedDay = day; publishedSite = site;
        restore();
        var p = new URLSearchParams(window.location.search), effort = p.get("effort");
        var requested = (p.get("agent") || "") + (effort && effort !== "default" ? "@" + effort : "");
        var matrices = day.matrices || {}, keys = Object.keys(matrices), selected = matrices[requested] || day.matrix;
        var picker = host.querySelector("[data-task-setting]");
        host.querySelector("[data-task-setting-wrap]").hidden = keys.length < 2;
        picker.innerHTML = keys.map(function (key) { return '<option value="' + esc(key) + '"' +
          (selected && selected.scaffold === key ? ' selected' : '') + '>' + esc(key.replace(/@/g, " · ").replace(/_/g, " ")) + '</option>'; }).join("");
        state.grid = taskGrid(Object.assign({}, day, {matrix: selected}), site); state.modelQuery = query || "";
        host.querySelector('[data-control="taskQuery"]').value = state.taskQuery;
        host.querySelector('[data-control="modelOrder"]').value = state.modelOrder;
        host.querySelector('[data-control="taskOrder"]').value = state.taskOrder;
        render(); save(false);
        return { models: state.view.rows.length, tasks: state.view.tasks.length, available: state.grid.available };
      },
      snapshot: function () {
        var common = { date: state.grid && state.grid.date, view: "tasks", title: state.display === "ranking" ? "Task ranking" : "Task outcomes",
          notes: [state.grid && state.grid.available ? settings(true) : "Task outcomes unavailable", state.modelQuery ? "Models matching: " + state.modelQuery : "All shown models", state.taskQuery ? "Tasks matching: " + state.taskQuery : "All shown tasks"] };
        if (state.display === "ranking") return Object.assign(common, {
          columns: [{key:"task",label:"Task"},{key:"project",label:"Project"},{key:"solved",label:"Models solved",type:"number"},{key:"n",label:"Models evaluated",type:"number"},{key:"rate",label:"Success rate",type:"percent"}],
          rows: state.view.tasks.map(function (task) { return { task:task.title,project:task.project,solved:task.solved,n:task.n,rate:task.rate }; }) });
        return Object.assign(common, { columns: [{key:"task",label:"Task"}].concat(state.view.rows.map(function (r,i) { return {key:"m"+i,label:label(r.model)}; })),
          rows: state.view.tasks.map(function (task) { var row={task:task.title}; state.view.rows.forEach(function (r,i) { row["m"+i]=r.values[task.index]===1?"Solved":r.values[task.index]===0?"Not solved":"Not evaluated"; }); return row; }) });
      },
      clear: function (message) { state.grid = null; state.selected = null; geometry = null; tooltip.hidden = true; selection.hidden = true; scope.textContent = ""; selection.innerHTML = ""; content.innerHTML = '<p class="tdb-empty">' + esc(message) + '</p>'; },
      repaint: paintChart
    };
  }
  Object.assign(T, { taskGrid: taskGrid, taskView: taskView, createTaskExplorer: createTaskExplorer });
})();

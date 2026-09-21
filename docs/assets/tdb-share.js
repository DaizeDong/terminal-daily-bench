/* Share and export the selected results, including their evaluation scope. */
(function (root) {
  "use strict";
  var T = root.TDB = root.TDB || {};
  function printable(value, column) {
    if (value === null || value === undefined || (typeof value === "number" && !isFinite(value))) return "";
    if (column && column.type === "percent" && typeof value === "number") return (value * 100).toFixed(1) + "%";
    return String(value);
  }
  function csvCell(value, numeric) {
    var text = value === null || value === undefined ? "" : String(value);
    if (!numeric && typeof value === "string" && /^[\s]*[=+\-@]/.test(text)) text = "'" + text;
    return '"' + text.replace(/"/g, '""') + '"';
  }
  function dataCell(value, column) {
    return csvCell(column && column.type === "percent" ? printable(value, column) : value,
      typeof value === "number" && isFinite(value));
  }
  function csvText(snapshot, link) {
    var lines = [["Terminal-Daily", snapshot.title], ["Evaluation date", snapshot.date], ["View", snapshot.view]];
    if (link) lines.push(["Source", link]);
    (snapshot.notes || []).filter(Boolean).forEach(function (note) { lines.push(["Scope", note]); });
    var encoded = lines.map(function (line) { return line.map(function (value) { return csvCell(value, false); }).join(","); });
    if (Array.isArray(snapshot.scores) && snapshot.scores.length) {
      encoded.push("", csvCell("Paired success rate", false),
        ["Result", "Majority accuracy", "Run SD", "Runs", "Tasks"].map(function (label) { return csvCell(label, false); }).join(","));
      snapshot.scores.forEach(function (score) {
        encoded.push([csvCell(score.label, false)].concat(["rate", "rate_sd"].map(function (key) {
          return dataCell(score[key], {type: "percent"});
        }), [dataCell(score.rate_runs), dataCell(score.n)]).join(","));
      });
    }
    encoded.push("", snapshot.columns.map(function (column) { return csvCell(column.label, false); }).join(","));
    snapshot.rows.forEach(function (row) { encoded.push(snapshot.columns.map(function (column) {
      return dataCell(row[column.key], column);
    }).join(",")); });
    return "\ufeff" + encoded.join("\r\n") + "\r\n";
  }
  function xml(value) { return String(value == null ? "" : value).replace(/[&<>"']/g, function (c) { return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&apos;"}[c]; }); }
  function runSD(row, column) {
    var value = row[column.key], sd = row[column.key + "_sd"], runs = row[column.key + "_runs"];
    return column.type === "percent" && Number.isFinite(value) && value >= 0 && value <= 1 &&
      Number.isFinite(sd) && sd >= 0 && Number.isInteger(runs) && runs >= 2 ? { sd: sd, runs: runs } : null;
  }
  function errorText(repeat) {
    return " \u00b1 " + (repeat.sd * 100).toFixed(1) + "%";
  }
  function wrap(text, limit) {
    var lines = [], current = "";
    String(text || "").split(/\s+/).forEach(function (word) {
      if (current.length + word.length + 1 > limit && current) { lines.push(current); current = ""; }
      if (word.length > limit) { if (current) lines.push(current); while (word.length > limit) { lines.push(word.slice(0, limit)); word = word.slice(limit); } current = word; }
      else current += (current ? " " : "") + word;
    });
    if (current) lines.push(current);
    return lines;
  }
  function svgText(snapshot, options) {
    options = options || {};
    var width = 1200, padding = 36, maxHeight = 4096, maxRows = 48, shortened = false;
    var keys = snapshot.imageColumns, explicitColumns = Array.isArray(keys) && keys.length > 0;
    if (!explicitColumns) {
      if (snapshot.view === "efficiency") {
        var metric = snapshot.metric || (/tool calls/i.test(snapshot.title || "") ? "tools" : /cost/i.test(snapshot.title || "") ? "cost" : "commands");
        var prefix = metric === "tools" ? "tool" : metric === "cost" ? "cost" : "command";
        keys = ["model", "agent", "effort", "success_rate_" + prefix + "_subset",
          prefix === "command" ? "mean_commands" : prefix === "tool" ? "mean_tool_calls" : "mean_cost_usd", prefix + "_n", prefix + "_tasks"];
      } else if (snapshot.view === "profile") keys = ["model", "capability", "rate", "evaluated", "paired_peer_gap", "peer_pairs", "preliminary"];
      else if (snapshot.view === "capability") keys = ["model", "overall"].concat(snapshot.columns.filter(function (c) { return c.type === "percent" && /^cap:/.test(c.key); }).map(function (c) { return c.key; }));
    }
    var maxColumns = snapshot.view === "capability" ? 16 : 7;
    var valueColumns = explicitColumns ? snapshot.columns : snapshot.columns.filter(function (column) { return !/_(?:sd|runs)$/.test(column.key); });
    var columns = Array.isArray(keys) && keys.length ? keys.map(function (key) { return valueColumns.find(function (column) { return column.key === key; }); }).filter(Boolean).slice(0, maxColumns) : valueColumns.slice(0, maxColumns);
    if (!columns.length) columns = snapshot.columns.slice(0, 7);
    var imageLabels = snapshot.view === "efficiency" ? { model: "Model", agent: "Agent", effort: "Effort",
      success_rate_cost_subset: "Success rate", success_rate_command_subset: "Success rate", success_rate_tool_subset: "Success rate",
      mean_cost_usd: "Mean cost / attempt (USD)", mean_commands: "Mean commands / attempt", mean_tool_calls: "Mean tool calls / attempt",
      cost_n: "Measured attempts", command_n: "Measured attempts", tool_n: "Measured attempts",
      cost_tasks: "Measured tasks", command_tasks: "Measured tasks", tool_tasks: "Measured tasks" } : {};
    columns = columns.map(function (column) { return Object.assign({}, column, {label: imageLabels[column.key] || column.label}); });
    if (snapshot.view === "capability") width = Math.min(2400, Math.max(1200, 372 + (columns.length - 1) * 134));
    var rows = snapshot.rows.slice(0, maxRows), renderedRows = 0;
    function visibleError(row, column) { return snapshot.view === "capability" ? null : runSD(row, column); }
    var sizes = columns.map(function (_, i) { return i === 0 ? 300 : (width - padding * 2 - 300) / Math.max(1, columns.length - 1); });
    if (columns.length === 1) sizes[0] = width - padding * 2;
    var parts = [], y = 38;
    function text(value, x, at, size, color, weight, numeric) { parts.push('<text x="' + x + '" y="' + at + '" font-size="' + (size || 15) + '" fill="' + (color || "#15223b") + '"' + (weight ? ' font-weight="' + weight + '"' : '') + (numeric ? ' class="number"' : '') + '>' + xml(value) + '</text>'); }
    function scoreBar(value, repeat, x, at, span) {
      if (!Number.isFinite(value) || value < 0 || value > 1) return;
      parts.push('<rect x="' + x + '" y="' + at + '" width="' + span + '" height="3" fill="#eef2f8"/><rect x="' + x + '" y="' + at + '" width="' + (span * value) + '" height="3" fill="#315aba"/>');
      if (repeat) {
        var lo = x + Math.max(0, value - repeat.sd) * span, hi = x + Math.min(1, value + repeat.sd) * span, barY = at + 1.5;
        parts.push('<path d="M' + lo + ' ' + barY + 'H' + hi + 'M' + lo + ' ' + (barY - 3) + 'V' + (barY + 3) + 'M' + hi + ' ' + (barY - 3) + 'V' + (barY + 3) + '" stroke="#15223b" fill="none"/>');
      }
    }
    function bounded(value, limit, maxLines) {
      var raw = String(value == null ? "" : value), maxChars = limit * maxLines;
      if (raw.length > maxChars) { raw = raw.slice(0, maxChars - 1) + "…"; shortened = true; }
      var lines = wrap(raw, limit);
      if (lines.length > maxLines) { lines = lines.slice(0, maxLines); lines[maxLines - 1] = lines[maxLines - 1].slice(0, limit - 1) + "…"; shortened = true; }
      return lines;
    }
    text("Terminal-Daily", padding, y, 17, "#315aba", 600); y += 38;
    bounded(snapshot.title, 60, 3).forEach(function (line) { text(line, padding, y, 29, null, 600); y += 35; });
    text((snapshot.date || "") + " · " + snapshot.rows.length + (snapshot.rows.length === 1 ? " row" : " rows"), padding, y, 15, "#586c8c"); y += 28;
    var notes = (snapshot.imageNotes || snapshot.notes || []).filter(Boolean).slice();
    var scores = Array.isArray(snapshot.scores) ? snapshot.scores.slice(0, 4) : [];
    var runCounts = Array.from(new Set(rows.flatMap(function (row) {
      return columns.map(function (column) { var repeat = visibleError(row, column); return repeat ? repeat.runs : null; }).filter(function (runs) { return runs !== null; });
    }).concat(scores.map(function (score) { var repeat = visibleError(score, {key: "rate", type: "percent"}); return repeat ? repeat.runs : null; }).filter(function (runs) { return runs !== null; })))).sort(function (a, b) { return a - b; });
    if (runCounts.length) notes.unshift("Scores use task majority; \u00b1 shows run standard deviation across " + runCounts.join(" / ") + " recorded runs.");
    if (notes.length > 6) shortened = true;
    notes.slice(0, 6).forEach(function (note) { bounded(note, 118, 3).forEach(function (line) { text(line, padding, y, 14, "#586c8c"); y += 21; }); });
    y += 16;
    if (scores.length) {
      text("Paired success rate", padding, y, 16, null, 600); y += 26;
      scores.forEach(function (score) {
        var repeat = visibleError(score, {key: "rate", type: "percent"}), start = padding + 320;
        var value = printable(score.rate, {type: "percent"}) || "Not evaluated";
        if (repeat) value += errorText(repeat);
        value += "  N=" + score.n;
        if (repeat) value += "  " + repeat.runs + " runs";
        var labels = bounded(score.label, 34, 2);
        labels.forEach(function (line, i) { text(line, padding, y + i * 19, 14); });
        text(value, start, y, 14, null, null, true);
        scoreBar(score.rate, repeat, start, y + 10, width - padding - start);
        y += Math.max(44, labels.length * 19 + 16);
      });
      y += 16;
    }
    if (options.chart && /^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(options.chart.url || "") &&
        Number.isFinite(options.chart.width) && options.chart.width > 0 && Number.isFinite(options.chart.height) && options.chart.height > 0) {
      var scale = Math.min((width - padding * 2) / options.chart.width, (maxHeight - y - 100) / options.chart.height);
      var imageHeight = options.chart.height * scale, imageWidth = options.chart.width * scale;
      parts.push('<image x="' + padding + '" y="' + y + '" width="' + imageWidth + '" height="' + imageHeight + '" href="' + xml(options.chart.url) + '"/>');
      y += imageHeight + 25;
      text("Current chart page. Blue: solved. Pale: not solved. Hatched: not evaluated.", padding, y, 14, "#586c8c"); y += 25;
    } else {
      var x = padding;
      columns.forEach(function (c, i) { bounded(c.label, Math.floor(sizes[i] / 8), 3).forEach(function (line, j) { text(line, x + 8, y + j * 18, 13, "#586c8c"); }); x += sizes[i]; }); y += 62;
      rows.some(function (row) {
        var cells = columns.map(function (column, i) {
          var value = printable(row[column.key], column) || "—";
          if (column.key === "model" && T.modelLabel) value = T.modelLabel(value);
          if (column.key === "agent" && T.agentLabel) value = T.agentLabel(value);
          var repeat = visibleError(row, column);
          if (repeat) value += errorText(repeat);
          var metadata = [];
          if (snapshot.view === "capability" && /^cap:/.test(column.key)) {
            if (Number.isFinite(row[column.key + ":n"])) metadata.push("N=" + row[column.key + ":n"]);
            if (row[column.key + ":labels"] === "Preliminary") metadata.push("preliminary");
          }
          var limit = Math.max(9, Math.floor((sizes[i] - 16) / 8));
          return repeat ? [value].concat(metadata.length ? bounded(metadata.join(" "), limit, 2) : []) : bounded([value].concat(metadata).join(" "), limit, 3);
        });
        var height = Math.max(38, Math.max.apply(null, cells.map(function (lines) { return lines.length; })) * 20 + 20), x = padding;
        if (y + height > maxHeight - 100) return true;
        parts.push('<path d="M' + padding + ' ' + (y - 18) + 'H' + (width - padding) + '" stroke="#d9e2ef"/>');
        cells.forEach(function (lines, i) {
          var repeat = visibleError(row, columns[i]);
          lines.forEach(function (line, j) {
            var fontSize = repeat ? Math.min(14, Math.max(8.5, (sizes[i] - 16) / (line.length * .62))) : 14;
            text(line, x + 8, y + j * 20, fontSize, null, null, ["number", "percent"].includes(columns[i].type));
          });
          var value = row[columns[i].key];
          if (columns[i].type === "percent") scoreBar(value, repeat, x + 8, y + height - 27, sizes[i] - 16);
          x += sizes[i];
        }); y += height; renderedRows++; return false;
      });
      if (renderedRows < snapshot.rows.length || columns.length < snapshot.columns.length) {
        y += 12; text("Image: first " + renderedRows + (renderedRows === 1 ? " row" : " rows") + " and " + columns.length + " columns. CSV includes every selected result.", padding, y, 14, "#586c8c"); y += 24;
      }
    }
    if (shortened) { text("Long text shortened for the image. CSV retains the full text.", padding, y, 14, "#586c8c"); y += 24; }
    var height = Math.min(maxHeight, Math.ceil(y + padding));
    return '<svg xmlns="http://www.w3.org/2000/svg" width="' + width + '" height="' + height + '" viewBox="0 0 ' + width + ' ' + height + '"><style>' + (options.fontCss || "") + 'text{font-family:Geist,Arial,sans-serif}text.number{font-family:"Google Sans Code",monospace}</style><rect width="100%" height="100%" fill="#fbfcfe"/>' + parts.join("") + '</svg>';
  }
  function shareUrl(snapshot) {
    var url = T.canonicalUrl ? T.canonicalUrl(root.location.href) : new URL(root.location.href);
    if (!url.searchParams.has("date") && snapshot && snapshot.date) url.searchParams.set("date", snapshot.date);
    ["audit", "cache", "v"].forEach(function (key) { url.searchParams.delete(key); });
    url.searchParams.sort();
    return url.href;
  }
  function rasterSize(width, height) {
    if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) throw new Error("Invalid image dimensions");
    var scale = Math.min(2, 8192 / width, 8192 / height, Math.sqrt(20000000 / (width * height)));
    return { width: Math.max(1, Math.floor(width * scale)), height: Math.max(1, Math.floor(height * scale)) };
  }
  Object.assign(T, { resultsCSV: csvText, resultsSVG: svgText, resultsShareUrl: shareUrl, resultsRasterSize: rasterSize });
  if (!root.document) return;
  var fontPromise;
  function fontCss() {
    if (!fontPromise) fontPromise = Promise.all([["Geist", "geist-latin.woff2"], ["Google Sans Code", "google-sans-code-latin.woff2"]].map(function (font) {
      return fetch(T.ROOT + "/assets/fonts/" + font[1]).then(function (r) { if (!r.ok) throw new Error("Font could not be loaded"); return r.arrayBuffer(); }).then(function (buffer) {
        var bytes = new Uint8Array(buffer), binary = ""; for (var i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
        return '@font-face{font-family:"' + font[0] + '";src:url(data:font/woff2;base64,' + btoa(binary) + ') format("woff2")}';
      });
    })).then(function (fonts) { return fonts.join(""); }).catch(function (error) { fontPromise = null; throw error; });
    return fontPromise;
  }
  function save(blob, filename) {
    var link = document.createElement("a"), url = URL.createObjectURL(blob);
    link.href = url; link.download = filename; document.body.appendChild(link); link.click(); link.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 30000);
  }
  function mount() {
    var host = document.querySelector(".tdb-result-heading");
    if (!host || typeof T.leaderboardSnapshot !== "function") return;
    var tools = document.createElement("div"); tools.className = "tdb-result-tools";
    tools.innerHTML = '<button type="button" data-share>Share view</button><details><summary>Export</summary><div class="tdb-export-menu"><button type="button" data-export="csv">CSV table</button><button type="button" data-export="svg">SVG image</button><button type="button" data-export="png">PNG image</button></div></details><span class="tdb-tool-status" role="status" aria-live="polite"></span><input class="tdb-share-link" aria-label="Link to this result" readonly hidden>';
    host.appendChild(tools);
    var status = tools.querySelector('[role="status"]'), busy = false;
    function refresh() { var snapshot = T.leaderboardSnapshot(), available = !busy && snapshot && snapshot.rows && snapshot.rows.length; tools.querySelectorAll("[data-export]").forEach(function (b) { b.disabled = !available; }); }
    tools.addEventListener("click", async function (event) {
      var button = event.target.closest("button"); if (!button || busy) return;
      var snapshot = T.leaderboardSnapshot();
      if (button.hasAttribute("data-share")) {
        var link = shareUrl(snapshot);
        try { await navigator.clipboard.writeText(link); status.textContent = "Link copied"; }
        catch (error) { var input = tools.querySelector("input"); input.hidden = false; input.value = link; input.focus(); input.select(); status.textContent = "Copy the selected link"; }
        return;
      }
      var format = button.getAttribute("data-export"); if (!format || !snapshot || !snapshot.rows || !snapshot.rows.length) return;
      busy = true; refresh(); status.textContent = "Preparing export…";
      try {
        var filename = "terminal-daily-" + (snapshot.date || "results") + "-" + String(snapshot.view || "results").replace(/[^a-z0-9-]/gi, "-");
        if (format === "csv") save(new Blob([csvText(snapshot, shareUrl(snapshot))], {type:"text/csv;charset=utf-8"}), filename + ".csv");
        else {
          var chart = snapshot.view === "tasks" && document.querySelector('#task-explorer [data-layout="heatmap"][aria-pressed="true"]') ? document.querySelector("#task-explorer canvas") : null;
          var chartSnapshot = chart ? {url:chart.toDataURL("image/png"),width:chart.width,height:chart.height} : null;
          await document.fonts.ready;
          var svg = svgText(snapshot, {fontCss:await fontCss(),chart:chartSnapshot});
          if (format === "svg") save(new Blob([svg], {type:"image/svg+xml;charset=utf-8"}), filename + ".svg");
          else {
            var image = new Image(), url = URL.createObjectURL(new Blob([svg], {type:"image/svg+xml;charset=utf-8"}));
            try { await new Promise(function (resolve, reject) { image.onload=resolve; image.onerror=reject; image.src=url; });
              var canvas=document.createElement("canvas"), dimensions=rasterSize(image.width,image.height); canvas.width=dimensions.width;canvas.height=dimensions.height;
              canvas.getContext("2d").drawImage(image,0,0,canvas.width,canvas.height);
              var blob=await new Promise(function(resolve){canvas.toBlob(resolve,"image/png");}); if(!blob)throw new Error("Image could not be created");save(blob,filename+".png");
            } finally { URL.revokeObjectURL(url); }
          }
        }
        status.textContent = "Export ready"; tools.querySelector("details").open = false;
      } catch (error) { status.textContent = "Export could not be created. Try again."; }
      finally { busy = false; refresh(); }
    });
    document.addEventListener("tdb:results", refresh); refresh();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount); else mount();
})(typeof window !== "undefined" ? window : globalThis);

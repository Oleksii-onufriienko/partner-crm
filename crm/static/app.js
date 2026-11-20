(function () {
  "use strict";
  var root = document.documentElement;

  // Тема: светлая / тёмная (по умолчанию — как в системе)
  function effectiveTheme() {
    var t = root.getAttribute("data-theme");
    if (t) return t;
    return window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  document.querySelectorAll("[data-theme-toggle]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var next = effectiveTheme() === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try { localStorage.setItem("theme", next); } catch (e) { /* приватный режим */ }
    });
  });

  // Подтверждение опасных действий
  document.addEventListener("submit", function (e) {
    var msg = e.target.getAttribute("data-confirm");
    if (msg && !window.confirm(msg)) e.preventDefault();
  });

  // Автоотправка фильтров
  document.querySelectorAll("[data-autosubmit]").forEach(function (el) {
    el.addEventListener("change", function () { el.form.submit(); });
  });

  // Ступень → коэффициент по умолчанию (если поле не меняли вручную)
  var stufe = document.querySelector("select[data-coefs]");
  var coef = document.querySelector("input[name=coef]");
  if (stufe && coef) {
    var defaults = JSON.parse(stufe.getAttribute("data-coefs"));
    var touched = coef.value !== "";
    coef.addEventListener("input", function () { touched = coef.value !== ""; });
    stufe.addEventListener("change", function () {
      if (touched && coef.dataset.auto !== "1") return;
      var v = defaults[stufe.value];
      coef.value = v === null || v === undefined ? "" : String(v).replace(".", ",");
      coef.dataset.auto = "1";
      touched = false;
    });
  }

  // Копирование ссылки-приглашения
  document.querySelectorAll("[data-copy]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var input = document.getElementById(btn.getAttribute("data-copy"));
      input.select();
      var done = function () { btn.textContent = "Скопировано"; };
      if (navigator.clipboard) navigator.clipboard.writeText(input.value).then(done, function () {
        document.execCommand("copy"); done();
      }); else { document.execCommand("copy"); done(); }
    });
  });

  // Форма встречи: при смене человека подгружаем его контакты, сохраняя введённое
  var owner = document.querySelector("[data-owner-reload]");
  if (owner) {
    owner.addEventListener("change", function () {
      var form = owner.form, url = new URL(window.location.href);
      ["date", "time", "duration_min", "format", "stage", "status", "expected_ke", "title", "note"].forEach(function (n) {
        var el = form.elements[n];
        if (!el) return;
        var v = el.length && !el.tagName ? (Array.prototype.find.call(el, function (r) { return r.checked; }) || {}).value : el.value;
        if (v) url.searchParams.set(n, v); else url.searchParams.delete(n);
      });
      url.searchParams.set("person", owner.value);
      url.searchParams.delete("contact_id");
      window.location.href = url.toString();
    });
  }

  // План: «Для всех недель» → во все недели строки
  document.querySelectorAll("[data-fill-row]").forEach(function (inp) {
    inp.addEventListener("input", function () {
      var row = inp.closest("tr");
      row.querySelectorAll("input.s-in").forEach(function (cell) { cell.value = inp.value; });
    });
  });

  // Самооценка: число рядом с ползунком
  document.querySelectorAll("input[type=range][data-out]").forEach(function (r) {
    var out = document.getElementById(r.getAttribute("data-out"));
    r.addEventListener("input", function () { if (out) out.textContent = r.value; });
  });

  // Годовой план: «На год» → делим на 12 месяцев
  document.querySelectorAll("[data-fill-year]").forEach(function (inp) {
    inp.addEventListener("input", function () {
      var v = parseFloat(inp.value.replace(",", "."));
      var row = inp.closest("tr");
      row.querySelectorAll("input.s-in").forEach(function (cell) {
        cell.value = isNaN(v) ? "" : String(Math.round(v / 12 * 10) / 10);
      });
    });
  });

  // Потенциальная сделка → «оформить»: переносим данные в форму сделки
  document.querySelectorAll("[data-to-deal]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var f = document.getElementById("deal-form");
      if (!f) return;
      f.elements.product.value = btn.getAttribute("data-product");
      f.elements.ke.value = btn.getAttribute("data-ke");
      f.elements.from_potential.value = btn.getAttribute("data-to-deal");
      f.scrollIntoView({ behavior: "smooth", block: "center" });
      f.elements.date.focus();
    });
  });
  // ---------------------------------------------------------- график активности (статистика)
  var NS = "http://www.w3.org/2000/svg";
  var MON = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
  var MON_NOM = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"];

  function svgEl(tag, attrs, parent) {
    var e = document.createElementNS(NS, tag);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }
  function niceStep(max) {
    if (max <= 4) return 1;
    var raw = max / 4, p = Math.pow(10, Math.floor(Math.log10(raw))), n = raw / p;
    return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p;
  }

  function initChart(root) {
    var data = JSON.parse(root.getAttribute("data-chart"));
    var plot = root.querySelector(".ts-plot"), svg = plot.querySelector("svg"), tip = plot.querySelector(".ts-tip");
    var hidden = {}, idx = null, n = data.labels.length;
    var color = function (i) { return "var(--s" + (i + 1) + ")"; };

    function label(iso, long) {
      var p = iso.split("-"), d = +p[2], m = +p[1];
      if (data.mode === "month") return long ? MON_NOM[m - 1] + " " + p[0] : MON[m - 1];
      if (long) return (data.mode === "week" ? "Неделя с " : "") + d + " " + MON[m - 1] + " " + p[0];
      return d + " " + MON[m - 1];
    }

    function render() {
      var W = Math.max(280, plot.clientWidth), H = 260, L = 36, R = 14, T = 10, B = 28;
      svg.setAttribute("viewBox", "0 0 " + W + " " + H);
      svg.setAttribute("height", H);
      while (svg.firstChild) svg.removeChild(svg.firstChild);
      tip.hidden = true;
      var vis = [];
      data.series.forEach(function (s, i) { if (!hidden[s.key]) vis.push({ s: s, i: i }); });
      var max = 0;
      vis.forEach(function (o) { o.s.values.forEach(function (v) { if (v !== null && v > max) max = v; }); });
      var step = niceStep(max), top = Math.max(step, Math.ceil(max / step) * step);
      var span = W - L - R;
      var x = function (i) { return n === 1 ? L + span / 2 : L + i * span / (n - 1); };
      var y = function (v) { return T + (H - T - B) * (1 - v / top); };

      for (var v = 0; v <= top + 1e-9; v += step) {
        svgEl("line", { x1: L, x2: W - R, y1: y(v), y2: y(v), "class": "ts-grid" }, svg);
        svgEl("text", { x: L - 8, y: y(v) + 4, "class": "ts-ylab", "text-anchor": "end" }, svg).textContent = String(v);
      }
      var every = Math.max(1, Math.ceil(n / Math.max(2, Math.floor(span / 70))));
      for (var i = 0; i < n; i += every) {
        if (n - 1 - i < every / 2 && i !== 0 && i !== n - 1) continue;
        svgEl("text", { x: x(i), y: H - 8, "class": "ts-xlab", "text-anchor": i === 0 ? "start" : "middle" }, svg).textContent = label(data.labels[i]);
      }
      if (n > 1 && (n - 1) % every !== 0) {
        svgEl("text", { x: x(n - 1), y: H - 8, "class": "ts-xlab", "text-anchor": "end" }, svg).textContent = label(data.labels[n - 1]);
      }

      if (!vis.length) {
        svgEl("text", { x: L + span / 2, y: H / 2, "class": "ts-empty", "text-anchor": "middle" }, svg).textContent = "Все линии скрыты — включите нужные выше";
        return;
      }
      vis.forEach(function (o) {
        var d = "", pen = false;
        o.s.values.forEach(function (val, k) {
          if (val === null) { pen = false; return; }
          d += (pen ? "L" : "M") + x(k).toFixed(1) + " " + y(val).toFixed(1) + " ";
          pen = true;
        });
        var path = svgEl("path", { d: d, "class": "ts-line" }, svg);
        path.style.stroke = color(o.i);
      });

      var cross = svgEl("line", { y1: T, y2: H - B, "class": "ts-cross" }, svg);
      cross.style.display = "none";
      var dots = vis.map(function (o) {
        var c = svgEl("circle", { r: 4, "class": "ts-dot" }, svg);
        c.style.fill = color(o.i);
        c.style.display = "none";
        return c;
      });
      var hit = svgEl("rect", { x: L - 10, y: 0, width: span + 20, height: H - B + 6, fill: "transparent" }, svg);

      function show(k) {
        idx = k;
        cross.setAttribute("x1", x(k)); cross.setAttribute("x2", x(k)); cross.style.display = "";
        vis.forEach(function (o, j) {
          var val = o.s.values[k];
          dots[j].style.display = val === null ? "none" : "";
          if (val !== null) { dots[j].setAttribute("cx", x(k)); dots[j].setAttribute("cy", y(val)); }
        });
        tip.textContent = "";
        var h = document.createElement("div"); h.className = "h"; h.textContent = label(data.labels[k], true); tip.appendChild(h);
        vis.forEach(function (o) {
          var r = document.createElement("div"); r.className = "r";
          var key = document.createElement("i"); key.style.borderTopColor = color(o.i); r.appendChild(key);
          var b = document.createElement("b"); b.textContent = o.s.values[k] === null ? "—" : String(o.s.values[k]); r.appendChild(b);
          var sp = document.createElement("span"); sp.textContent = o.s.label; r.appendChild(sp);
          tip.appendChild(r);
        });
        tip.hidden = false;
        var px = x(k) / W * plot.clientWidth, tw = tip.offsetWidth;
        tip.style.left = (px + 14 + tw > plot.clientWidth ? Math.max(0, px - 14 - tw) : px + 14) + "px";
        tip.style.top = "4px";
      }
      function hide() { idx = null; cross.style.display = "none"; dots.forEach(function (d) { d.style.display = "none"; }); tip.hidden = true; }
      hit.addEventListener("pointermove", function (e) {
        var r = svg.getBoundingClientRect(), px = (e.clientX - r.left) * (W / r.width);
        var k = n === 1 ? 0 : Math.round((px - L) / (span / (n - 1)));
        show(Math.max(0, Math.min(n - 1, k)));
      });
      hit.addEventListener("pointerleave", hide);
      svg.onkeydown = function (e) {
        if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
          e.preventDefault();
          var k = idx === null ? n - 1 : idx + (e.key === "ArrowRight" ? 1 : -1);
          show(Math.max(0, Math.min(n - 1, k)));
        } else if (e.key === "Escape") hide();
      };
      svg.onblur = hide;
    }

    root.querySelectorAll(".ts-key").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var key = btn.getAttribute("data-key"), on = btn.getAttribute("aria-pressed") === "true";
        btn.setAttribute("aria-pressed", on ? "false" : "true");
        if (on) hidden[key] = true; else delete hidden[key];
        render();
      });
    });
    root.querySelectorAll("[data-all]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var show = btn.getAttribute("data-all") === "1";
        root.querySelectorAll(".ts-key").forEach(function (k) {
          k.setAttribute("aria-pressed", show ? "true" : "false");
          if (show) delete hidden[k.getAttribute("data-key")]; else hidden[k.getAttribute("data-key")] = true;
        });
        render();
      });
    });
    render();
    if (window.ResizeObserver) new ResizeObserver(function () { render(); }).observe(plot);
    else window.addEventListener("resize", render);
  }
  document.querySelectorAll(".ts[data-chart]").forEach(initChart);
})();

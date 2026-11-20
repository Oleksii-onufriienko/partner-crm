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
})();

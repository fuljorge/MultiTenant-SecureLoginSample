/*
 * Indicador de força da senha (specs/001-identity-access, RF-032; OWASP ASVS 2.1.8).
 * Só orienta: quem decide é a política do realm (tamanho, lista de senhas vazadas,
 * histórico). Heurística local, sem dependência e sem enviar a senha a lugar nenhum.
 */
(function () {
  "use strict";

  var MIN_LENGTH = 12;
  var COMMON = ["senha", "password", "qwerty", "123456", "admin", "abcdef", "keycloak"];
  var LABELS = ["Fraca", "Fraca", "Razoável", "Boa", "Forte"];

  function hasSequence(value) {
    var lower = value.toLowerCase();
    for (var i = 0; i + 2 < lower.length; i++) {
      var a = lower.charCodeAt(i);
      var b = lower.charCodeAt(i + 1);
      var c = lower.charCodeAt(i + 2);
      if ((b === a + 1 && c === b + 1) || (b === a - 1 && c === b - 1)) return true;
    }
    return false;
  }

  function score(value) {
    if (value.length < MIN_LENGTH) return 0;
    var points = 1;
    if (value.length >= 16) points++;
    if (value.length >= 20) points++;
    var classes = 0;
    if (/[a-z]/.test(value)) classes++;
    if (/[A-Z]/.test(value)) classes++;
    if (/[0-9]/.test(value)) classes++;
    if (/[^A-Za-z0-9]/.test(value)) classes++;
    if (classes >= 3) points++;
    if (/(.)\1{2,}/.test(value)) points--;
    if (hasSequence(value)) points--;
    var lower = value.toLowerCase();
    for (var i = 0; i < COMMON.length; i++) {
      if (lower.indexOf(COMMON[i]) !== -1) {
        points--;
        break;
      }
    }
    return Math.max(0, Math.min(4, points));
  }

  function attach(input) {
    var meter = document.createElement("div");
    meter.className = "cap-strength";
    meter.setAttribute("data-level", "0");
    var bar = document.createElement("div");
    bar.className = "cap-strength__bar";
    bar.appendChild(document.createElement("span"));
    var text = document.createElement("p");
    text.className = "cap-strength__text";
    text.id = input.id + "-strength";
    text.setAttribute("aria-live", "polite");
    meter.appendChild(bar);
    meter.appendChild(text);
    var group = input.closest(".pf-v5-c-form__group") || input.parentElement;
    group.appendChild(meter);
    input.setAttribute("aria-describedby", text.id);

    function update() {
      var value = input.value;
      if (!value) {
        meter.setAttribute("data-level", "0");
        text.textContent = "";
        return;
      }
      var level = score(value);
      meter.setAttribute("data-level", String(level));
      text.textContent =
        "Força da senha: " +
        LABELS[level] +
        (value.length < MIN_LENGTH ? " (mínimo de " + MIN_LENGTH + " caracteres)" : "");
    }

    input.addEventListener("input", update);
    update();
  }

  function init() {
    var input = document.getElementById("password-new");
    if (input) attach(input);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

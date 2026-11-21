document.querySelectorAll("form[data-confirmer]").forEach(function (f) {
  f.addEventListener("submit", function (e) {
    if (!window.confirm(f.getAttribute("data-confirmer"))) e.preventDefault();
  });
});

// Restauration : l'utilisateur doit taper le mot demandé (ex. RESTAURER).
document.querySelectorAll("form[data-confirmer-saisie]").forEach(function (f) {
  f.addEventListener("submit", function (e) {
    var mot = f.getAttribute("data-confirmer-saisie");
    var saisie = window.prompt("Toutes les données actuelles seront remplacées (elles sont d'abord sauvegardées).\nTapez " + mot + " pour confirmer :");
    if (saisie === null || saisie.trim() !== mot) { e.preventDefault(); return; }
    f.querySelector("input[name=confirmation]").value = saisie.trim();
  });
});

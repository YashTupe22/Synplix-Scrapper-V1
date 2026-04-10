const form = document.getElementById("lead-form");

if (form) {
  form.addEventListener("submit", () => {
    document.body.classList.add("is-loading");
  });
}

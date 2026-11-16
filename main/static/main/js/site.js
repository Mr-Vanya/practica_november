document.addEventListener("DOMContentLoaded", () => {
  const search = document.querySelector("[data-live-search]");
  if (!search) return;
  search.addEventListener("input", () => {
    const form = search.form;
    if (!form) return;
    clearTimeout(window.searchTimer);
    window.searchTimer = setTimeout(() => form.requestSubmit(), 350);
  });
});

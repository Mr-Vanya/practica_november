document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-filter-toggle]").forEach((checkbox) => {
    const controls = checkbox.dataset.filterToggle
      .split(",")
      .map((id) => document.getElementById(id.trim()))
      .filter(Boolean);
    if (!controls.length) return;
    const syncControl = () => {
      controls.forEach((control) => {
        control.disabled = !checkbox.checked;
        if (!checkbox.checked) control.value = "";
      });
    };
    checkbox.addEventListener("change", syncControl);
    syncControl();
  });

  const search = document.querySelector("[data-live-search]");
  if (search) {
    search.addEventListener("input", () => {
      const form = search.form;
      if (!form) return;
      clearTimeout(window.searchTimer);
      window.searchTimer = setTimeout(() => form.requestSubmit(), 350);
    });
  }

  const quantityInputs = [...document.querySelectorAll("[data-cart-quantity]")];
  const grandTotal = document.querySelector("#cart-grand-total");
  const saveStatus = document.querySelector("#cart-save-status");
  if (!quantityInputs.length || !grandTotal) return;

  const formatter = new Intl.NumberFormat("ru-RU", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
  const normalizedQuantity = (input) => {
    const value = Number.parseInt(input.value, 10);
    return Math.min(99, Math.max(1, Number.isFinite(value) ? value : 1));
  };

  const updateTotals = () => {
    let total = 0;
    quantityInputs.forEach((input) => {
      const lineTotal = normalizedQuantity(input) * (Number.parseFloat(input.dataset.unitPrice) || 0);
      total += lineTotal;
      const line = input.closest("[data-cart-row]")?.querySelector("[data-cart-line-total]");
      if (line) line.textContent = `${formatter.format(lineTotal)} ₽`;
    });
    grandTotal.textContent = `${formatter.format(total)} ₽`;
  };

  const saveQuantity = async (input) => {
    const form = input.closest("form[data-cart-quantity-form]");
    if (!form) return;
    input.value = String(normalizedQuantity(input));
    updateTotals();
    if (saveStatus) saveStatus.textContent = "Сохраняю…";
    try {
      const response = await fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        headers: { "X-Requested-With": "XMLHttpRequest" }
      });
      if (!response.ok) throw new Error("Не удалось сохранить количество");
      const data = await response.json();
      input.value = String(data.quantity);
      updateTotals();
      if (saveStatus) saveStatus.textContent = "Количество сохранено";
    } catch (error) {
      if (saveStatus) saveStatus.textContent = "Не удалось сохранить количество. Проверьте соединение и обновите страницу.";
    }
  };

  quantityInputs.forEach((input) => {
    let timer;
    input.addEventListener("input", () => {
      updateTotals();
      clearTimeout(timer);
      timer = setTimeout(() => saveQuantity(input), 400);
    });
    input.addEventListener("change", () => {
      clearTimeout(timer);
      saveQuantity(input);
    });
    input.closest("[data-cart-row]")?.querySelectorAll("[data-quantity-step]").forEach((button) => {
      button.addEventListener("click", () => {
        const step = Number.parseInt(button.dataset.quantityStep, 10) || 0;
        input.value = String(Math.min(99, Math.max(1, normalizedQuantity(input) + step)));
        input.dispatchEvent(new Event("input", { bubbles: true }));
      });
    });
  });
  updateTotals();
});

document.addEventListener("DOMContentLoaded", () => {
  const returnDialog = document.querySelector("[data-return-dialog]");
  const openReturnDialog = document.querySelector("[data-open-return-dialog]");
  if (returnDialog && openReturnDialog) {
    openReturnDialog.addEventListener("click", () => returnDialog.showModal());
    returnDialog.querySelector("[data-close-return-dialog]")?.addEventListener("click", () => returnDialog.close());
    returnDialog.addEventListener("click", (event) => {
      if (event.target === returnDialog) returnDialog.close();
    });

    const returnProduct = returnDialog.querySelector("[data-return-product]");
    const returnQuantity = returnDialog.querySelector("[data-return-quantity]");
    const updateReturnQuantities = () => {
      if (!returnProduct || !returnQuantity) return;
      const orderedQuantity = Number.parseInt(
        returnProduct.selectedOptions[0]?.dataset.orderedQuantity || "0",
        10
      );
      const previousValue = Number.parseInt(returnQuantity.value || "1", 10);
      returnQuantity.replaceChildren();
      for (let quantity = 1; quantity <= orderedQuantity; quantity += 1) {
        const option = document.createElement("option");
        option.value = String(quantity);
        const unit = quantity === 1 ? "товар" : quantity < 5 ? "товара" : "товаров";
        option.textContent = `${quantity} ${unit}`;
        returnQuantity.append(option);
      }
      returnQuantity.value = String(Math.min(Math.max(previousValue, 1), orderedQuantity));
    };
    returnProduct?.addEventListener("change", updateReturnQuantities);
    updateReturnQuantities();
  }

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

  const catalogSection = document.querySelector("[data-catalog-api]");
  if (catalogSection) {
    const catalogForm = document.querySelector("#catalog-filter-form");
    const searchForm = document.querySelector(".header-search");
    const searchInput = searchForm?.querySelector('[name="q"]');
    const results = catalogSection.querySelector("[data-catalog-results]");
    const status = catalogSection.querySelector("[data-catalog-status]");
    const pagination = catalogSection.querySelector("[data-catalog-pagination]");
    const apiUrl = catalogSection.dataset.catalogApi;
    const catalogPath = catalogSection.dataset.catalogPath;
    let activeRequest;
    let searchTimer;

    const makePageUrl = (params) => `${catalogPath}${params.toString() ? `?${params}` : ""}`;
    const buildParamsFromForm = () => {
      const params = new URLSearchParams(new FormData(catalogForm));
      params.set("q", searchInput?.value.trim() || "");
      params.delete("page");
      return params;
    };

    const createProductCard = (product) => {
      const card = document.createElement("article");
      card.className = "product-card card";
      if (product.image_url) {
        const imageLink = document.createElement("a");
        imageLink.className = "product-card-image";
        imageLink.href = product.detail_url;
        imageLink.setAttribute("aria-label", `Открыть ${product.name}`);
        const image = document.createElement("img");
        image.src = product.image_url;
        image.alt = product.name;
        image.loading = "lazy";
        imageLink.append(image);
        card.append(imageLink);
      }

      const title = document.createElement("a");
      title.className = "product-name";
      title.href = product.detail_url;
      title.textContent = product.name;
      const meta = document.createElement("div");
      meta.className = "meta";
      const duration = product.duration_min ? `${product.duration_min} мин` : "длительность не указана";
      const rating = product.rating === null ? "—" : Number(product.rating).toLocaleString("ru-RU", { maximumFractionDigits: 1 });
      meta.textContent = `${product.category} · ${product.min_age}+ · ${product.min_players}–${product.max_players} игроков · ${duration} · ★ ${rating}`;
      const price = document.createElement("div");
      price.className = "price";
      price.textContent = `${Number(product.price).toLocaleString("ru-RU")} ₽`;
      const stock = document.createElement("div");
      stock.className = "stock";
      stock.textContent = product.stock_quantity > 0
        ? `В наличии · ${product.stock_quantity} шт.`
        : "Нет в наличии";
      card.append(title, meta, price, stock);
      return card;
    };

    const renderPagination = (data, params) => {
      if (!pagination) return;
      pagination.replaceChildren();
      if (data.num_pages <= 1) return;

      const addPageLink = (label, pageNumber) => {
        const pageParams = new URLSearchParams(params);
        pageParams.set("page", String(pageNumber));
        const link = document.createElement("a");
        link.href = makePageUrl(pageParams);
        link.dataset.catalogPage = String(pageNumber);
        link.textContent = label;
        pagination.append(link);
      };

      if (data.has_previous) addPageLink("← Назад", data.page - 1);
      const pageLabel = document.createElement("span");
      pageLabel.textContent = `Страница ${data.page} из ${data.num_pages}`;
      pagination.append(pageLabel);
      if (data.has_next) addPageLink("Далее →", data.page + 1);
    };

    const loadCatalog = async (params, historyMode = "push") => {
      activeRequest?.abort();
      const controller = new AbortController();
      activeRequest = controller;
      catalogSection.setAttribute("aria-busy", "true");
      if (status) status.textContent = "Обновляю каталог…";
      try {
        const response = await fetch(`${apiUrl}?${params.toString()}`, {
          headers: { Accept: "application/json" },
          signal: controller.signal,
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Не удалось обновить каталог.");

        results.replaceChildren();
        if (data.results.length) {
          data.results.forEach((product) => results.append(createProductCard(product)));
        } else {
          const empty = document.createElement("p");
          empty.className = "empty-state";
          empty.textContent = "Ничего не найдено. Измените условия поиска.";
          results.append(empty);
        }
        if (status) status.textContent = `Найдено товаров: ${data.total}`;
        renderPagination(data, params);
        if (data.page > 1) params.set("page", String(data.page));
        else params.delete("page");
        const pageUrl = makePageUrl(params);
        if (historyMode === "push") history.pushState(null, "", pageUrl);
        else if (historyMode === "replace") history.replaceState(null, "", pageUrl);
      } catch (error) {
        if (error.name !== "AbortError" && status) status.textContent = error.message;
      } finally {
        if (!controller.signal.aborted) catalogSection.setAttribute("aria-busy", "false");
      }
    };

    const submitCatalogFilters = (event) => {
      event.preventDefault();
      loadCatalog(buildParamsFromForm());
    };
    catalogForm?.addEventListener("submit", submitCatalogFilters);
    searchForm?.addEventListener("submit", (event) => {
      event.preventDefault();
      loadCatalog(buildParamsFromForm());
    });
    searchInput?.addEventListener("input", () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => loadCatalog(buildParamsFromForm(), "replace"), 450);
    });
    pagination?.addEventListener("click", (event) => {
      const link = event.target.closest("a[data-catalog-page]");
      if (!link) return;
      event.preventDefault();
      const params = buildParamsFromForm();
      params.set("page", link.dataset.catalogPage);
      loadCatalog(params);
    });

    window.addEventListener("popstate", () => {
      const params = new URLSearchParams(window.location.search);
      for (const control of catalogForm?.elements || []) {
        if (!control.name) continue;
        if (control.type === "checkbox") control.checked = params.getAll(control.name).includes(control.value);
        else if (params.has(control.name)) control.value = params.get(control.name);
        else if (control.name !== "q") control.value = "";
      }
      if (searchInput) searchInput.value = params.get("q") || "";
      loadCatalog(params, "replace");
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

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatNumber(value, { maximumFractionDigits = 2 } = {}) {
  if (!Number.isFinite(Number(value))) {
    return "-";
  }
  return Number(value).toLocaleString("it-IT", {
    maximumFractionDigits,
  });
}

function formatCurrency(value) {
  if (!Number.isFinite(Number(value))) {
    return "-";
  }
  return Number(value).toLocaleString("it-IT", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  });
}

function formatPercent(value) {
  if (!Number.isFinite(Number(value))) {
    return "-";
  }
  return `${formatNumber(value)}%`;
}

function formatDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "-";
  }
  return date.toLocaleString("it-IT", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatCategory(category) {
  if (!category || typeof category !== "object") {
    return "-";
  }
  return category.label || category.key || "-";
}

function summarizeMunicipalities(values) {
  if (!Array.isArray(values) || values.length === 0) {
    return "Nessun comune";
  }
  const visible = values.slice(0, 3).join(", ");
  return values.length > 3 ? `${visible} +${values.length - 3}` : visible;
}

function metric(value, unit) {
  return `${formatNumber(value)} ${unit}`;
}

export function renderAnalysisHistoryList({
  items,
  selectedIds,
  renamingId = null,
  pendingDeleteId = null,
}) {
  if (!items.length) {
    return `
      <div class="analysis-history-empty">
        <h3>Nessuna analisi salvata</h3>
        <p>Esegui un'analisi per aggiungerla allo storico.</p>
      </div>
    `;
  }

  return `
    <div class="analysis-history-list">
      ${items
        .map((item) => {
          const checked = selectedIds.has(item.id) ? "checked" : "";
          const summary = item.summary || {};
          const isRenaming = item.id === renamingId;
          const isPendingDelete = item.id === pendingDeleteId;
          return `
            <article class="analysis-history-item">
              <div class="analysis-history-item-main">
                <label class="analysis-history-check">
                  <input type="checkbox" data-history-select="${escapeHtml(item.id)}" ${checked}>
                  <span>${escapeHtml(item.label || item.id)}</span>
                </label>
                <div class="analysis-history-date">${escapeHtml(formatDate(item.createdAt))}</div>
              </div>
              <div class="analysis-history-meta">
                <span>${escapeHtml(item.selectionKind || "unknown")}</span>
                <span>${escapeHtml(summarizeMunicipalities(item.municipalities))}</span>
              </div>
              <div class="analysis-history-metrics">
                <span><strong>${escapeHtml(metric(summary.totalCo2, "t"))}</strong><small>CO2</small></span>
                <span><strong>${escapeHtml(metric(summary.totalHectares, "ha"))}</strong><small>Superficie</small></span>
                <span><strong>${escapeHtml(formatCategory(summary.topCategory))}</strong><small>Prevalente</small></span>
              </div>
              <div class="analysis-history-actions">
                ${isRenaming ? renderRenameControls(item) : `<button type="button" data-history-rename="${escapeHtml(item.id)}">Rinomina</button>`}
                ${isPendingDelete ? renderDeleteControls(item) : `<button type="button" data-history-delete="${escapeHtml(item.id)}">Elimina</button>`}
              </div>
            </article>
          `;
        })
        .join("")}
    </div>
  `;
}

function renderRenameControls(item) {
  return `
    <div class="analysis-history-inline-form">
      <label>
        <span>Etichetta</span>
        <input type="text" value="${escapeHtml(item.label || item.id)}" data-history-rename-input="${escapeHtml(item.id)}">
      </label>
      <div class="analysis-history-inline-actions">
        <button type="button" data-history-rename-save="${escapeHtml(item.id)}">Salva</button>
        <button type="button" data-history-rename-cancel="${escapeHtml(item.id)}">Annulla</button>
      </div>
    </div>
  `;
}

function renderDeleteControls(item) {
  return `
    <div class="analysis-history-confirm">
      <span>Eliminare "${escapeHtml(item.label || item.id)}"?</span>
      <div class="analysis-history-inline-actions">
        <button type="button" data-history-delete-confirm="${escapeHtml(item.id)}">Conferma</button>
        <button type="button" data-history-delete-cancel="${escapeHtml(item.id)}">Annulla</button>
      </div>
    </div>
  `;
}

export function renderAnalysisComparison(comparison) {
  if (!comparison) {
    return "";
  }

  return `
    <div class="analysis-comparison">
      <section class="analysis-comparison-section">
        <h3>Confronto analisi</h3>
        ${renderAnalysesTable(comparison.analyses || [])}
      </section>
      ${comparison.pairwise ? renderPairwise(comparison.pairwise) : ""}
      ${renderCategories(comparison.categoriesComparison)}
      ${renderEconomic(comparison.economicComparison || [], comparison.analyses || [])}
    </div>
  `;
}

function renderAnalysesTable(analyses) {
  return `
    <div class="analysis-history-table-wrap">
      <table class="analysis-history-table">
        <thead>
          <tr>
            <th>Analisi</th>
            <th>Tipo</th>
            <th>Comuni</th>
            <th>CO2</th>
            <th>Superficie</th>
            <th>CO2/ha</th>
            <th>Categoria</th>
          </tr>
        </thead>
        <tbody>
          ${analyses
            .map(
              (item) => `
                <tr>
                  <td>${escapeHtml(item.label)}</td>
                  <td>${escapeHtml(item.selectionKind)}</td>
                  <td>${escapeHtml(summarizeMunicipalities(item.municipalities))}</td>
                  <td>${escapeHtml(metric(item.totalCo2, "t"))}</td>
                  <td>${escapeHtml(metric(item.totalHectares, "ha"))}</td>
                  <td>${escapeHtml(item.co2PerHectare === null ? "-" : metric(item.co2PerHectare, "t/ha"))}</td>
                  <td>${escapeHtml(formatCategory(item.topCategory))}</td>
                </tr>
              `
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderPairwise(pairwise) {
  return `
    <section class="analysis-comparison-section">
      <h3>Differenze</h3>
      <div class="analysis-difference-grid">
        ${differenceCard("CO2", pairwise.totalCo2, "t")}
        ${differenceCard("Superficie", pairwise.totalHectares, "ha")}
        ${differenceCard("CO2/ha", pairwise.co2PerHectare, "t/ha")}
      </div>
      <div class="analysis-comparison-note">
        <strong>CO2 maggiore:</strong> ${escapeHtml(pairwise.higherTotalCo2?.label || "-")}
      </div>
      <div class="analysis-comparison-note">
        <strong>CO2/ha maggiore:</strong> ${escapeHtml(pairwise.higherCo2PerHectare?.label || "-")}
      </div>
    </section>
  `;
}

function differenceCard(label, value, unit) {
  return `
    <article class="analysis-difference-card">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(metric(value?.absolute, unit))}</strong>
      <small>${escapeHtml(formatPercent(value?.percent))}</small>
    </article>
  `;
}

function renderCategories(categoriesComparison) {
  if (!categoriesComparison) {
    return "";
  }
  const common = categoriesComparison.commonCategories || [];
  const partial = categoriesComparison.partialCategories || [];
  const top = categoriesComparison.topCategoriesByAnalysis || [];
  const labelsByKey = new Map(
    (categoriesComparison.categoryBreakdown || []).map((item) => [item.key, item.label || item.key])
  );
  const labelList = (keys) => keys.map((key) => labelsByKey.get(key) || key).join(", ");
  return `
    <section class="analysis-comparison-section">
      <h3>Categorie</h3>
      <div class="analysis-comparison-note">
        <strong>Comuni a tutte:</strong> ${escapeHtml(common.length ? labelList(common) : "nessuna")}
      </div>
      <div class="analysis-comparison-note">
        <strong>Solo in alcune:</strong> ${escapeHtml(partial.length ? labelList(partial) : "nessuna")}
      </div>
      <ul class="analysis-comparison-list">
        ${top
          .map(
            (item) => `
              <li><strong>${escapeHtml(item.label)}:</strong> ${escapeHtml(formatCategory(item.topCategory))}</li>
            `
          )
          .join("")}
      </ul>
    </section>
  `;
}

function renderEconomic(scenarios, analyses) {
  if (!scenarios.length || !analyses.length) {
    return "";
  }
  return `
    <section class="analysis-comparison-section">
      <h3>Scenari economici</h3>
      <div class="analysis-history-table-wrap">
        <table class="analysis-history-table">
          <thead>
            <tr>
              <th>Scenario</th>
              <th>Prezzo</th>
              ${analyses.map((item) => `<th>${escapeHtml(item.label)}</th>`).join("")}
              <th>Ranking</th>
            </tr>
          </thead>
          <tbody>
            ${scenarios
              .map((scenario) => {
                const valuesById = new Map((scenario.values || []).map((item) => [item.id, item]));
                return `
                  <tr>
                    <td>${escapeHtml(scenario.label)}</td>
                    <td>${escapeHtml(metric(scenario.priceEurPerTon, "EUR/t"))}</td>
                    ${analyses
                      .map((item) => `<td>${escapeHtml(formatCurrency(valuesById.get(item.id)?.value))}</td>`)
                      .join("")}
                    <td>${escapeHtml((scenario.ranking || []).map((item) => `${item.rank}. ${item.label}`).join(" | "))}</td>
                  </tr>
                `;
              })
              .join("")}
          </tbody>
        </table>
      </div>
    </section>
  `;
}

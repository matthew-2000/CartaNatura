function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatNumber(value, { maximumFractionDigits = 2 } = {}) {
  if (value === null || value === undefined || value === "" || !Number.isFinite(Number(value))) {
    return "-";
  }
  return Number(value).toLocaleString("it-IT", { maximumFractionDigits });
}

function formatCurrency(value) {
  if (value === null || value === undefined || value === "" || !Number.isFinite(Number(value))) {
    return "-";
  }
  return Number(value).toLocaleString("it-IT", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  });
}

function formatPercent(value) {
  return value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value))
    ? `${formatNumber(value)}%`
    : "-";
}

function formatDate(value, { compact = false } = {}) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Data non disponibile";
  }
  return date.toLocaleString("it-IT", {
    day: "2-digit",
    month: compact ? "short" : "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatReadableId(value) {
  const clean = String(value || "").replace(/^analysis[_-]?/i, "").replaceAll(/[^a-z0-9]/gi, "");
  return clean ? `AN-${clean.slice(0, 6).toUpperCase()}` : "AN—";
}

function formatCategory(category) {
  if (!category || typeof category !== "object") {
    return "-";
  }
  return category.label || category.key || "-";
}

function formatSelectionKind(value) {
  const labels = {
    municipalities: "Comuni",
    drawn: "Area disegnata",
    mixed: "Comuni + area disegnata",
    unknown: "Area non specificata",
  };
  return labels[String(value || "unknown")] || labels.unknown;
}

function summarizeMunicipalities(values, limit = 3) {
  if (!Array.isArray(values) || values.length === 0) {
    return "Territorio senza comuni nominati";
  }
  const visible = values.slice(0, limit).join(", ");
  return values.length > limit ? `${visible} +${values.length - limit}` : visible;
}

function metric(value, unit) {
  return value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value))
    ? `${formatNumber(value)} ${unit}`
    : "-";
}

function difference(left, right) {
  const leftValue = Number(left);
  const rightValue = Number(right);
  if (!Number.isFinite(leftValue) || !Number.isFinite(rightValue)) {
    return { absolute: null, percent: null };
  }
  return {
    absolute: Math.abs(rightValue - leftValue),
    percent: leftValue === 0 ? null : (Math.abs(rightValue - leftValue) / Math.abs(leftValue)) * 100,
  };
}

function winnerId(analyses, field) {
  const candidates = analyses.filter((item) => Number.isFinite(Number(item?.[field])));
  if (!candidates.length) {
    return null;
  }
  return candidates.reduce((winner, item) =>
    Number(item[field]) > Number(winner[field]) ? item : winner
  ).id;
}

function comparisonMark(isWinner) {
  return isWinner ? '<span class="comparison-winner-mark">↑ Maggiore</span>' : "";
}

export function renderAnalysisHistoryList({
  items,
  selectedIds,
  renamingId = null,
  pendingDeleteId = null,
  busy = false,
}) {
  if (busy && !items.length) {
    return `
      <div class="analysis-history-loading" role="status" aria-label="Caricamento dello storico">
        <span></span><span></span><span></span>
      </div>
    `;
  }

  if (!items.length) {
    return `
      <div class="analysis-history-empty">
        <span class="analysis-empty-symbol" aria-hidden="true">＋</span>
        <h3>Nessuna analisi salvata</h3>
        <p>Le analisi completate appariranno qui, pronte per essere riaperte e confrontate.</p>
      </div>
    `;
  }

  return `
    <div class="analysis-history-list"${busy ? ' aria-busy="true"' : ""}>
      ${items
        .map((item) => {
          const checked = selectedIds.has(item.id) ? "checked" : "";
          const summary = item.summary || {};
          const isRenaming = item.id === renamingId;
          const isPendingDelete = item.id === pendingDeleteId;
          return `
            <article class="analysis-history-item${checked ? " is-selected" : ""}">
              <label class="analysis-history-check">
                <input type="checkbox" data-history-select="${escapeHtml(item.id)}" ${checked}>
                <span class="analysis-history-selector" aria-hidden="true"></span>
                <span class="analysis-history-item-main">
                  <strong>${escapeHtml(item.label || item.id)}</strong>
                  <small title="${escapeHtml(item.id)}">${escapeHtml(formatReadableId(item.id))} · ${escapeHtml(formatDate(item.createdAt, { compact: true }))}</small>
                </span>
              </label>
              <div class="analysis-history-context">
                <span>${escapeHtml(formatSelectionKind(item.selectionKind))}</span>
                <strong>${escapeHtml(summarizeMunicipalities(item.municipalities))}</strong>
              </div>
              <div class="analysis-history-metrics">
                <span><small>CO₂ annua</small><strong>${escapeHtml(metric(summary.totalCo2, "t/anno"))}</strong></span>
                <span><small>Superficie</small><strong>${escapeHtml(metric(summary.totalHectares, "ha"))}</strong></span>
                <span><small>Prevalente</small><strong>${escapeHtml(formatCategory(summary.topCategory))}</strong></span>
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
        <span>Nome dell'analisi</span>
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
      <span>Eliminare “${escapeHtml(item.label || item.id)}”?</span>
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

  const analyses = comparison.analyses || [];
  return `
    <div class="analysis-comparison">
      <header class="analysis-comparison-header">
        <div>
          <span class="analysis-panel-kicker">Sintesi comparativa</span>
          <h3>${analyses.length === 2 ? "Due territori, una lettura immediata" : `${analyses.length} analisi a confronto`}</h3>
          <p>Valori totali, intensità per ettaro e scostamenti calcolati sugli stessi dati salvati.</p>
        </div>
        <button type="button" data-comparison-close>Storico</button>
      </header>
      ${renderAnalysisIdentities(analyses)}
      ${comparison.pairwise ? renderPairwise(comparison.pairwise, analyses) : renderMultiAnalysis(analyses)}
      ${renderCategories(comparison.categoriesComparison, analyses)}
      ${renderEconomic(comparison.economicComparison || [], analyses)}
    </div>
  `;
}

function renderAnalysisIdentities(analyses) {
  return `
    <section class="comparison-identities" aria-label="Analisi confrontate">
      ${analyses
        .map(
          (item, index) => `
            <article class="comparison-identity">
              <span class="comparison-index">${String.fromCharCode(65 + index)}</span>
              <div>
                <h4>${escapeHtml(item.label)}</h4>
                <p>${escapeHtml(summarizeMunicipalities(item.municipalities, 2))}</p>
                <small>${escapeHtml(formatSelectionKind(item.selectionKind))} · ${escapeHtml(formatReadableId(item.id))} · ${escapeHtml(formatDate(item.createdAt, { compact: true }))}</small>
              </div>
            </article>
          `
        )
        .join("")}
    </section>
  `;
}

function renderPairwise(pairwise, analyses) {
  const [left, right] = analyses;
  if (!left || !right) {
    return "";
  }
  const co2Winner = pairwise.higherTotalCo2?.id || winnerId(analyses, "totalCo2");
  const perHectareWinner = pairwise.higherCo2PerHectare?.id || winnerId(analyses, "co2PerHectare");
  const areaWinner = winnerId(analyses, "totalHectares");
  const co2WinnerItem = analyses.find((item) => item.id === co2Winner);
  const co2Difference = pairwise.totalCo2 || difference(left.totalCo2, right.totalCo2);

  return `
    <section class="comparison-summary-section">
      <div class="comparison-insight">
        <span>Risultato in breve</span>
        <strong>${escapeHtml(co2WinnerItem?.label || "Le analisi")} ${co2WinnerItem ? "registra il valore totale di CO₂ maggiore" : "non hanno un valore confrontabile"}${Number.isFinite(Number(co2Difference?.percent)) ? `, con uno scarto del ${escapeHtml(formatPercent(co2Difference.percent))}` : ""}.</strong>
      </div>
      <div class="comparison-metric-ledger">
        ${comparisonMetricRow({
          label: "CO₂ sequestrata",
          note: "Totale annuo",
          left,
          right,
          field: "totalCo2",
          unit: "t/anno",
          differenceValue: pairwise.totalCo2,
          winner: co2Winner,
        })}
        ${comparisonMetricRow({
          label: "Superficie",
          note: "Area forestale analizzata",
          left,
          right,
          field: "totalHectares",
          unit: "ha",
          differenceValue: pairwise.totalHectares,
          winner: areaWinner,
        })}
        ${comparisonMetricRow({
          label: "CO₂ per ettaro",
          note: "Confronto normalizzato",
          left,
          right,
          field: "co2PerHectare",
          unit: "t/ha",
          differenceValue: pairwise.co2PerHectare,
          winner: perHectareWinner,
        })}
      </div>
    </section>
  `;
}

function comparisonMetricRow({ label, note, left, right, field, unit, differenceValue, winner }) {
  const delta = differenceValue || difference(left[field], right[field]);
  return `
    <article class="comparison-metric-row">
      <div class="comparison-value${winner === left.id ? " is-higher" : ""}">
        <strong>${escapeHtml(metric(left[field], unit))}</strong>
        ${comparisonMark(winner === left.id)}
      </div>
      <div class="comparison-delta">
        <strong>${escapeHtml(label)}</strong>
        <small>${escapeHtml(note)}</small>
        <span>Δ ${escapeHtml(metric(delta?.absolute, unit))} · ${escapeHtml(formatPercent(delta?.percent))}</span>
      </div>
      <div class="comparison-value${winner === right.id ? " is-higher" : ""}">
        <strong>${escapeHtml(metric(right[field], unit))}</strong>
        ${comparisonMark(winner === right.id)}
      </div>
    </article>
  `;
}

function renderMultiAnalysis(analyses) {
  const fields = [
    ["CO₂ annua", "totalCo2", "t/anno"],
    ["Superficie", "totalHectares", "ha"],
    ["CO₂ per ettaro", "co2PerHectare", "t/ha"],
  ];
  return `
    <section class="comparison-multi-ledger">
      ${fields
        .map(([label, field, unit]) => {
          const winner = winnerId(analyses, field);
          return `
            <div class="comparison-multi-group">
              <h4>${escapeHtml(label)}</h4>
              ${analyses
                .map((item) => `<p><span>${escapeHtml(item.label)}</span><strong>${escapeHtml(metric(item[field], unit))}</strong>${comparisonMark(item.id === winner)}</p>`)
                .join("")}
            </div>
          `;
        })
        .join("")}
    </section>
  `;
}

function renderCategories(categoriesComparison, analyses) {
  if (!categoriesComparison) {
    return "";
  }
  const common = categoriesComparison.commonCategories || [];
  const partial = categoriesComparison.partialCategories || [];
  const breakdown = categoriesComparison.categoryBreakdown || [];

  return `
    <details class="comparison-disclosure">
      <summary>
        <span><strong>Categorie forestali</strong><small>${common.length} in comune · ${partial.length} distintive</small></span>
        <span class="disclosure-action">Dettagli</span>
      </summary>
      <div class="category-comparison-list">
        ${breakdown.map((item) => renderCategoryRow(item, analyses)).join("") || '<p class="comparison-empty-detail">Nessuna categoria confrontabile.</p>'}
      </div>
    </details>
  `;
}

function renderCategoryRow(item, analyses) {
  if (analyses.length !== 2) {
    const rowsById = new Map((item.analyses || []).map((entry) => [entry.id, entry]));
    return `
      <article class="category-comparison-row comparison-multi-detail">
        <header><strong>${escapeHtml(item.label || item.key)}</strong><span>${(item.analyses || []).filter((entry) => entry.present).length}/${analyses.length} analisi</span></header>
        <div>
          ${analyses
            .map((analysis) => {
              const row = rowsById.get(analysis.id);
              return `<span><small>${escapeHtml(analysis.label)}</small><strong>${escapeHtml(metric(row?.hectares, "ha"))}</strong><em>${escapeHtml(metric(row?.totalCo2, "t CO₂"))}</em></span>`;
            })
            .join("")}
        </div>
      </article>
    `;
  }
  const [leftAnalysis, rightAnalysis] = analyses;
  const rowsById = new Map((item.analyses || []).map((entry) => [entry.id, entry]));
  const left = rowsById.get(leftAnalysis?.id);
  const right = rowsById.get(rightAnalysis?.id);
  const hectaresDelta = difference(left?.hectares, right?.hectares);
  const winner = Number(left?.hectares || 0) >= Number(right?.hectares || 0) ? leftAnalysis?.id : rightAnalysis?.id;
  const presence = left?.present && right?.present
    ? "Presente in entrambe"
    : `Solo in ${escapeHtml(left?.present ? leftAnalysis?.label : rightAnalysis?.label || "un'analisi")}`;

  return `
    <article class="category-comparison-row">
      <header><strong>${escapeHtml(item.label || item.key)}</strong><span>${presence}</span></header>
      <div class="category-comparison-values">
        <span><small>${escapeHtml(leftAnalysis?.label || "A")}</small><strong>${escapeHtml(metric(left?.hectares, "ha"))}</strong><em>${escapeHtml(metric(left?.totalCo2, "t CO₂"))}</em>${comparisonMark(winner === leftAnalysis?.id)}</span>
        <span class="category-comparison-delta"><small>Differenza</small><strong>${escapeHtml(metric(hectaresDelta.absolute, "ha"))}</strong><em>${escapeHtml(formatPercent(hectaresDelta.percent))}</em></span>
        <span><small>${escapeHtml(rightAnalysis?.label || "B")}</small><strong>${escapeHtml(metric(right?.hectares, "ha"))}</strong><em>${escapeHtml(metric(right?.totalCo2, "t CO₂"))}</em>${comparisonMark(winner === rightAnalysis?.id)}</span>
      </div>
    </article>
  `;
}

function renderEconomic(scenarios, analyses) {
  if (!scenarios.length || !analyses.length) {
    return "";
  }
  return `
    <details class="comparison-disclosure">
      <summary>
        <span><strong>Scenari economici</strong><small>${scenarios.length} prezzi applicati agli stessi totali</small></span>
        <span class="disclosure-action">Dettagli</span>
      </summary>
      <div class="economic-comparison-list">
        ${scenarios.map((scenario) => renderEconomicRow(scenario, analyses)).join("")}
      </div>
    </details>
  `;
}

function renderEconomicRow(scenario, analyses) {
  if (analyses.length !== 2) {
    const valuesById = new Map((scenario.values || []).map((item) => [item.id, item]));
    const winner = scenario.ranking?.[0]?.id;
    return `
      <article class="economic-comparison-row comparison-multi-detail">
        <header><strong>${escapeHtml(scenario.label)}</strong><span>${escapeHtml(metric(scenario.priceEurPerTon, "€/tCO₂"))}</span></header>
        <div>
          ${analyses
            .map((analysis) => `<span class="${winner === analysis.id ? "is-higher" : ""}"><small>${escapeHtml(analysis.label)}</small><strong>${escapeHtml(formatCurrency(valuesById.get(analysis.id)?.value))}</strong>${comparisonMark(winner === analysis.id)}</span>`)
            .join("")}
        </div>
      </article>
    `;
  }
  const [left, right] = analyses;
  const valuesById = new Map((scenario.values || []).map((item) => [item.id, item]));
  const leftValue = valuesById.get(left?.id)?.value;
  const rightValue = valuesById.get(right?.id)?.value;
  const delta = difference(leftValue, rightValue);
  const ranking = scenario.ranking || [];
  const winner = ranking[0]?.id;

  return `
    <article class="economic-comparison-row">
      <header><strong>${escapeHtml(scenario.label)}</strong><span>${escapeHtml(metric(scenario.priceEurPerTon, "€/tCO₂"))}</span></header>
      <div>
        <span class="${winner === left?.id ? "is-higher" : ""}"><small>${escapeHtml(left?.label || "A")}</small><strong>${escapeHtml(formatCurrency(leftValue))}</strong>${comparisonMark(winner === left?.id)}</span>
        <span class="economic-comparison-delta"><small>Differenza</small><strong>${escapeHtml(formatCurrency(delta.absolute))}</strong><em>${escapeHtml(formatPercent(delta.percent))}</em></span>
        <span class="${winner === right?.id ? "is-higher" : ""}"><small>${escapeHtml(right?.label || "B")}</small><strong>${escapeHtml(formatCurrency(rightValue))}</strong>${comparisonMark(winner === right?.id)}</span>
      </div>
    </article>
  `;
}

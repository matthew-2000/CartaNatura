export function summarizeClippedFeatures(clipped, categories, categoryByCode) {
  const totalsByKey = new Map(categories.map((category) => [category.key, 0]));
  let totalCo2 = 0;
  let totalHectares = 0;

  for (const feature of clipped.features) {
    const code = feature.properties?.CODICE;
    const hectares = Number(feature.properties?.ettari || 0);
    const category = categoryByCode.get(code);

    if (!category) {
      continue;
    }

    totalsByKey.set(category.key, totalsByKey.get(category.key) + hectares);
    totalCo2 += category.co2PerHectare * hectares;
    totalHectares += hectares;
  }

  const items = categories
    .map((category) => ({
      ...category,
      hectares: totalsByKey.get(category.key),
    }))
    .filter((category) => category.hectares > 0);

  return {
    items,
    totalCo2,
    totalHectares,
    hasSupportedVegetation: items.length > 0,
  };
}

export function deriveSummaryMetrics(summary) {
  const items = summary?.items || [];
  const totalHectares = items.reduce((sum, item) => sum + (Number(item.hectares) || 0), 0);
  const topCategory = items.reduce(
    (current, item) => ((Number(item.hectares) || 0) > (Number(current?.hectares) || 0) ? item : current),
    null
  );

  return {
    totalHectares,
    topCategory,
  };
}

export function formatRoundedNumber(value) {
  return Number(value || 0).toLocaleString("it-IT", {
    maximumFractionDigits: 2,
  });
}

export function formatCurrency(value) {
  return Number(value || 0).toLocaleString("it-IT", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 2,
  });
}

export function buildEconomicScenarioRows(summary, priceOptions, selectedPrice) {
  const totalCo2 = Number(summary?.totalCo2 || 0);
  const selectedValue = Number(selectedPrice || priceOptions?.[0]?.value || 0);

  return (priceOptions || []).map((option) => {
    const price = Number(option.value || 0);
    return {
      label: option.label || "",
      description: option.description || option.note || "",
      price,
      totalCo2,
      value: totalCo2 * price,
      selected: price === selectedValue,
    };
  });
}

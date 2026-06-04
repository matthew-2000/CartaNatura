export function summarizeClippedFeatures(clipped, categories, categoryByCode) {
  const totalsByKey = new Map(categories.map((category) => [category.key, 0]));
  let totalCo2 = 0;

  for (const feature of clipped.features) {
    const code = feature.properties?.CODICE;
    const hectares = Number(feature.properties?.ettari || 0);
    const category = categoryByCode.get(code);

    if (!category) {
      continue;
    }

    totalsByKey.set(category.key, totalsByKey.get(category.key) + hectares);
    totalCo2 += category.co2PerHectare * hectares;
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
    hasSupportedVegetation: items.length > 0,
  };
}

export function formatRoundedNumber(value) {
  return Math.floor(value).toLocaleString("it-IT");
}

export function formatCurrency(value) {
  return Math.floor(value).toLocaleString("it-IT", {
    style: "currency",
    currency: "EUR",
  });
}

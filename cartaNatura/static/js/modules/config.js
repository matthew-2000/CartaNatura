const rawConfig = document.getElementById("app-config")?.textContent;

if (!rawConfig) {
  throw new Error("Configurazione applicazione mancante.");
}

export const appConfig = JSON.parse(rawConfig);
export const categories = appConfig.categories;
export const priceOptions = appConfig.priceOptions;
export const assistantConfig = appConfig.assistant || {};

export const categoryByCode = new Map();
for (const category of categories) {
  for (const code of category.codes) {
    categoryByCode.set(code, category);
  }
}

export function resolveFeatureCategory(feature) {
  return categoryByCode.get(String(feature?.properties?.CODICE ?? "")) || null;
}

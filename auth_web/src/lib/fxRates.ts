/** Merge saved FX overrides with built-in defaults for the settings editor. */

export function mergedFxRates(
  defaults?: Record<string, number>,
  saved?: Record<string, number>,
): Record<string, number> {
  return { ...(defaults ?? {}), ...(saved ?? {}) };
}

export function formatFxRatesJson(
  defaults?: Record<string, number>,
  saved?: Record<string, number>,
): string {
  const merged = mergedFxRates(defaults, saved);
  const sorted = Object.fromEntries(
    Object.keys(merged)
      .sort()
      .map((iso) => [iso, merged[iso]]),
  );
  return JSON.stringify(sorted, null, 2);
}

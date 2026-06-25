const API_BASE = import.meta.env.VITE_API_URL || "";

export async function fetchTranslations(
  texts: string[],
  target: "ar" | "en",
  source: "ar" | "en" = "en",
): Promise<string[]> {
  if (!texts.length || source === target) {
    return [...texts];
  }
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/translate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ texts, source, target }),
    });
  } catch {
    throw new Error("Cannot reach the translation service.");
  }
  if (!res.ok) {
    let detail = "Translation failed";
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  const data = (await res.json()) as { translations: string[] };
  return data.translations ?? texts;
}

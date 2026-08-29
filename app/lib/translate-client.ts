import type { MLCEngine } from "@mlc-ai/web-llm";

/**
 * Client-side, keyless input translation for BROWSER runs.
 *
 * The server-side translator can only use server providers — but browser setups often
 * have none running. So when Auto-translate is on and the run uses the in-browser model,
 * translation happens right here with the very same WebLLM engine.
 */

const TRANSLATE_SYSTEM_PROMPT =
  "You are a translation engine. Translate the user's text into natural English. Preserve meaning, tone, technical terms, URLs, file paths and code identifiers. Output ONLY the translation - no preamble, no quotes, no notes. If the text is already English, output it unchanged.";

const SCRIPT_TESTS: Array<[string, RegExp]> = [
  ["Cyrillic", /[\u0400-\u04FF]/],
  ["Greek", /[\u0370-\u03FF]/],
  ["Arabic", /[\u0600-\u06FF]/],
  ["Hebrew", /[\u0590-\u05FF]/],
  ["Chinese", /[\u4E00-\u9FFF]/],
  ["Japanese", /[\u3040-\u30FF]/],
  ["Korean", /[\uAC00-\uD7AF]/],
  ["Thai", /[\u0E00-\u0E7F]/],
];

// Short shared function words are deliberately excluded (" es " is the German word
// for "it", "una"/"para"/"con"/"que" appear in several Romance languages). They
// cause false positives like a German "geht es dir" being read as Spanish.
const LATIN_HINTS: Array<[string, RegExp]> = [
  ["German", / ä| ö| ü|ß| der | die | das | und | nicht | ist | ich | bitte | danke |schreibe|mache|funktioniert|warum |wie |geht |dir |du |guten |tschüss|hallo /],
  // Note: bare é is NOT a French marker — it appears in Spanish "qué"/"está" and
  // other languages; the remaining French markers are distinctive enough.
  ["French", / è|ç|à| le | la | les | une | des |est |pour |avec |je |nous |pourquoi |comment /],
  ["Spanish", / ñ|¿|¡| el | los | las |por favor|gracias|por qué|cómo |qué |está | hola |buenos días/],
  ["Italian", / il | lo | gli | per | con | che | non | sono |perché|grazie|come /],
  ["Portuguese", / ã|ç| os | as | não |está|obrigado|por favor|por que|como /],
  ["Dutch", / het | een | niet | zijn | met | voor | waarom |hoe kan |dank /],
  ["Polish", / nie | jest | się| dla | jak |dlaczego|proszę|dzięk/],
  ["Turkish", / bir | için | değil| nasıl| neden |lütfen/],
];

const ENGLISH_MARKERS = /\b(the|and|is|are|you|please|thanks|how|what|why|can|could|would|should|need|want|help|make|write|find|explain|build)\b/i;
const DIACRITIC = /[äöüßéèçñã¿à]/;

export function detectNonEnglish(text: string): { nonEnglish: boolean; language: string } {
  const sample = ` ${text.trim().toLowerCase()} `;
  for (const [name, pattern] of SCRIPT_TESTS) {
    if (pattern.test(text)) return { nonEnglish: true, language: name };
  }
  for (const [name, pattern] of LATIN_HINTS) {
    if (pattern.test(sample) && (!ENGLISH_MARKERS.test(text) || DIACRITIC.test(text))) {
      return { nonEnglish: true, language: name };
    }
  }
  return { nonEnglish: false, language: "English" };
}

export function languageNoteSuffix(language: string): string {
  return `\n\n[Context note: the user wrote the original message in ${language}. Reply in ${language}. The text above is its English translation for your processing.]`;
}

function isPlausibleTranslation(original: string, translated: string): boolean {
  const t = translated.trim();
  if (!t) return false;
  if (t.length > Math.max(original.length * 6, 4000)) return false;
  const words = t.split(/\s+/);
  for (let i = 0; i <= words.length - 4; i += 1) {
    // Same token four times in a row ("yes yes yes yes") — degenerate output.
    if (words[i] === words[i + 1] && words[i + 1] === words[i + 2] && words[i + 2] === words[i + 3]) return false;
  }
  const seen = new Set<string>();
  for (let i = 0; i <= words.length - 3; i += 1) {
    // Any 3-word sequence repeated — the model is stuck in a loop.
    const gram = words.slice(i, i + 3).join(" ");
    if (seen.has(gram)) return false;
    seen.add(gram);
  }
  // The model echoed the input (or wrapped it) instead of translating it.
  const originalLower = original.trim().toLowerCase();
  const lower = t.toLowerCase();
  if (lower === originalLower || lower.includes(originalLower)) return false;
  return true;
}

export async function translateWithEngine(engine: MLCEngine, text: string): Promise<string | null> {
  try {
    const completion = await engine.chat.completions.create({
      messages: [
        { role: "system", content: TRANSLATE_SYSTEM_PROMPT },
        { role: "user", content: text.slice(0, 4000) },
      ],
      stream: false,
      temperature: 0,
      max_tokens: 500,
    });
    const translated = (completion.choices[0]?.message?.content ?? "").trim();
    if (!isPlausibleTranslation(text, translated)) return null;
    return translated;
  } catch {
    return null;
  }
}

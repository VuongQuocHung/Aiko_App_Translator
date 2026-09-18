import rules from "../../../defaults/glossary_rules.txt?raw";
import type { GlossaryEntry } from "../types";
import { stringify } from "yaml";

export const GLOSSARY_RULES = rules;
export const GLOSSARY_TYPES = "Skill Ability Trait Rank Title Concept System Artifact Organization Faction Place World Species Name Common Alias Unknown".split(" ");

export function parseGlossary(text: string): GlossaryEntry[] {
  const entries = new Map<string, GlossaryEntry>();
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const [mapping, ...metadata] = line.split("|");
    const equals = mapping.indexOf("=");
    const source = mapping.slice(0, equals).trim(), target = mapping.slice(equals + 1).trim();
    if (equals < 1 || !source || !target) { console.warn("Glossary: skipping invalid entry", line); continue; }
    const entry: GlossaryEntry = { source, target };
    if (metadata.length) {
      const fields: Record<string, string> = Object.create(null);
      for (const item of metadata) {
        const split = item.indexOf("=");
        if (split < 1) { console.warn("Glossary: invalid metadata", item); continue; }
        fields[item.slice(0, split).trim().toLowerCase()] = item.slice(split + 1).trim();
      }
      const boolean = (name: string) => {
        const value = (fields[name] || "no").toLowerCase();
        if (!["yes", "no", "true", "false"].includes(value)) console.warn("Glossary: invalid boolean", name, value);
        return ["yes", "true"].includes(value);
      };
      entry.type = GLOSSARY_TYPES.find((type) => type.toLowerCase() === fields.type?.toLowerCase()) || fields.type || "Unknown";
      entry.first_vi = boolean("first_vi"); entry.first_en = boolean("first_en"); entry.brackets = boolean("brackets"); entry.extended = true;
      if (entry.first_vi && entry.first_en) { console.warn("Glossary: first_vi and first_en cannot both be yes; keeping first_vi", source); entry.first_en = false; }
      delete fields.type; delete fields.first_vi; delete fields.first_en; delete fields.brackets;
      entry.extra_metadata = fields;
    }
    if (entries.has(source)) console.warn("Glossary: duplicate; last valid entry wins", source);
    entries.set(source, entry);
  }
  return [...entries.values()];
}

export function serializeGlossaryEntry(entry: GlossaryEntry) {
  const base = `${entry.source} = ${entry.target}`;
  if (!entry.extended && !entry.first_vi && !entry.first_en && !entry.brackets && (!entry.type || entry.type === "Unknown") && !Object.keys(entry.extra_metadata || {}).length) return base;
  return base + ` | type=${entry.type || "Unknown"} | first_vi=${entry.first_vi ? "yes" : "no"} | first_en=${entry.first_en ? "yes" : "no"} | brackets=${entry.brackets ? "yes" : "no"}` + Object.entries(entry.extra_metadata || {}).map(([key, value]) => ` | ${key}=${value}`).join("");
}

const escape = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const term = (text: string) => `(?<![\\p{L}\\p{N}_])${escape(text)}(?![\\p{L}\\p{N}_])`;
const isTargetOnly = (entry: GlossaryEntry) => entry.type?.toLowerCase() === "common"
  || ["yes", "true"].includes((entry.extra_metadata?.target_only || "no").trim().toLowerCase());
const bodies = (text: string) => {
  const parts = text.split(/^[ \t]*(?:#{1,6}[ \t]*)?(?:chapter|chương|section)[ \t]*\d+[^\n]*\n?/gimu);
  if (!parts[0].trim() && parts.length > 1) parts.shift();
  return parts;
};

export function validateGlossary(text: string, entries: GlossaryEntry[], source = "", introduced: string[] = []): string[] {
  if (!entries.length) return [];
  const pattern = new RegExp([...entries].sort((a, b) => b.source.length - a.source.length).map((e) => term(e.source)).join("|"), "giu");
  const byName = new Map(entries.map((e) => [e.source.toLowerCase(), e]));
  const errors: string[] = [];
  const sourceBodies = bodies(source);
  bodies(text).forEach((body, chapter) => {
    const seen = new Set(chapter === 0 ? introduced : []);
    const protectedSpans: Array<[number, number]> = [];
    const present = new Set<string>();
    const firstEnPresent = new Set<string>();
    const report = (entry: GlossaryEntry, code: string, position: number) => errors.push(`Chapter ${chapter + 1}: ${entry.source}: ${code} at ${position}: ${body.slice(Math.max(0, position - 20), position + entry.source.length + 50)}`);
    for (const entry of [...entries].sort((a, b) => b.target.length - a.target.length)) {
      if (!entry.extended || !entry.first_en || isTargetOnly(entry)) continue;
      for (const match of body.matchAll(new RegExp(term(entry.target), "giu"))) {
        const start = match.index!, end = start + match[0].length;
        if (protectedSpans.some(([a, b]) => a < end && start < b)) continue;
        const bracketed = body[start - 1] === "[" && body[end] === "]";
        const suffix = end + (bracketed ? 1 : 0);
        const annotation = /^[ \t]*\(([^)\n]*)\)/u.exec(body.slice(suffix));
        protectedSpans.push([start, end]);
        if (annotation) protectedSpans.push([suffix, suffix + annotation[0].length]);
        firstEnPresent.add(entry.source);
        if (match[0] !== entry.target) report(entry, "target_spelling", start);
        if (Boolean(entry.brackets) !== bracketed) report(entry, entry.brackets ? "missing_brackets" : "unexpected_brackets", start);
        if (bracketed && (body[start - 2] === "[" || body[suffix] === "]")) report(entry, "nested_brackets", start);
        const expected = !seen.has(entry.source) && entry.source.toLowerCase() !== entry.target.toLowerCase();
        if (expected && annotation?.[1] !== entry.source) report(entry, "missing_first_english_annotation", start);
        if (!expected && annotation?.[1] === entry.source) report(entry, "repeated_english_annotation", start);
        if (expected && annotation && annotation[1] !== entry.source) report(entry, "incorrect_english_annotation", start);
        seen.add(entry.source);
      }
    }
    for (const match of body.matchAll(pattern)) {
      const start = match.index!, end = start + match[0].length;
      if (protectedSpans.some(([a, b]) => a <= start && start < b)) continue;
      const entry = byName.get(match[0].toLowerCase())!;
      present.add(entry.source);
      const bracketed = body[start - 1] === "[" && body[end] === "]";
      const suffix = end + (bracketed ? 1 : 0);
      const annotation = /^[ \t]*\(([^)\n]*)\)/u.exec(body.slice(suffix));
      if (annotation) protectedSpans.push([suffix, suffix + annotation[0].length]);
      protectedSpans.push([start, end]);
      if (!entry.extended) {
        if (annotation?.[1] === entry.target && entry.source === entry.target) report(entry, "redundant_annotation", start);
        continue;
      }
      if (isTargetOnly(entry)) {
        const prefix = entry.type?.toLowerCase() === "common" ? "common" : "target_only";
        if (entry.source.toLowerCase() !== entry.target.toLowerCase()) report(entry, `${prefix}_requires_vietnamese`, start);
        else if (bracketed || annotation) report(entry, `${prefix}_plain_vietnamese`, start);
        continue;
      }
      if (entry.first_en) { report(entry, "english_without_vietnamese", start); continue; }
      if (match[0] !== entry.source) report(entry, "canonical_spelling", start);
      if (Boolean(entry.brackets) !== bracketed) report(entry, entry.brackets ? "missing_brackets" : "unexpected_brackets", start);
      if (bracketed && (body[start - 2] === "[" || body[suffix] === "]")) report(entry, "nested_brackets", start);
      const expected = entry.first_vi && !seen.has(entry.source) && entry.source !== entry.target;
      if (expected && annotation?.[1] !== entry.target) report(entry, "missing_first_annotation", start);
      if (!expected && annotation?.[1] === entry.target) report(entry, entry.first_vi && entry.source !== entry.target ? "repeated_annotation" : "forbidden_annotation", start);
      seen.add(entry.source);
    }
    const raw = sourceBodies[Math.min(chapter, sourceBodies.length - 1)] || "";
    const sourceTerms = new Set([...raw.matchAll(pattern)].map((match) => byName.get(match[0].toLowerCase())!.source));
    for (const entry of [...entries].sort((a, b) => b.target.length - a.target.length)) {
      if (!entry.extended) continue;
      if (!isTargetOnly(entry) && sourceTerms.has(entry.source)) {
        if (entry.first_en && !firstEnPresent.has(entry.source)) report(entry, "missing_vietnamese", 0);
        else if (!entry.first_en && !present.has(entry.source)) report(entry, "missing_canonical", 0);
      }
      if (entry.source.toLowerCase() === entry.target.toLowerCase()) continue;
      if (entry.first_en) continue;
      for (const match of body.matchAll(new RegExp(term(entry.target), "giu"))) {
        const start = match.index!, end = start + match[0].length;
        if (protectedSpans.some(([a, b]) => a < end && start < b)) continue;
        if (!isTargetOnly(entry)) report(entry, "vietnamese_without_canonical", start);
        else if (body[start - 1] === "[" && body[end] === "]") {
          const prefix = entry.type?.toLowerCase() === "common" ? "common" : "target_only";
          report(entry, `${prefix}_plain_vietnamese`, start);
        }
        protectedSpans.push([start, end]);
      }
    }
  });
  return errors;
}

export function glossaryCorrectionPrompt(source: string, draft: string, entries: GlossaryEntry[], errors: string[]) {
  const contextText = stringify({ glossary: entries.map(serializeGlossaryEntry).join("\n") }, { lineWidth: 0 });
  return { stage: "polish" as const, sourceText: source, relevanceText: source + "\n" + draft, contextText, systemInstruction: GLOSSARY_RULES, prompt: `Fix ONLY the listed glossary/term formatting errors. Do not rewrite correct prose, narration, dialogue or meaning. Do not retranslate the chapter. Return only the complete corrected translation.\nERRORS:\n${errors.join("\n")}\nFULL GLOSSARY:\n${contextText}\nENGLISH ORIGINAL:\n${source}\nTEXT:\n${draft}` };
}

export function introducedTerms(text: string, entries: GlossaryEntry[]) {
  if (!entries.length) return [];
  const byName = new Map(entries.map((entry) => [entry.source.toLowerCase(), entry]));
  const pattern = new RegExp([...entries].sort((a, b) => b.source.length - a.source.length).map((entry) => term(entry.source)).join("|"), "giu");
  const body = bodies(text).at(-1)!;
  const introduced = [...body.matchAll(pattern)].map((match) => byName.get(match[0].toLowerCase())!).filter((entry) => entry.extended && !entry.first_en).map((entry) => entry.source);
  for (const entry of entries) if (entry.extended && entry.first_en && new RegExp(term(entry.target), "iu").test(body)) introduced.push(entry.source);
  return [...new Set(introduced)];
}

export function glossaryProseSignature(text: string, entries: GlossaryEntry[]) {
  const sorted = [...entries].sort((a, b) => Math.max(b.source.length, b.target.length) - Math.max(a.source.length, a.target.length));
  if (!sorted.length) return text;
  const pattern = new RegExp(sorted.map((entry, index) => {
    const viAnnotation = `(?:[ \\t]*\\(${escape(entry.target)}\\))?`;
    const enAnnotation = `(?:[ \\t]*\\(${escape(entry.source)}\\))?`;
    return `(?<t${index}>\\[*${term(entry.source)}${viAnnotation}\\]*${viAnnotation}|\\[*${term(entry.target)}\\]*${enAnnotation})`;
  }).join("|"), "giu");
  return text.replace(pattern, (...args) => {
    const groups = args.at(-1) as Record<string, string | undefined>;
    const key = Object.keys(groups).find((name) => groups[name] !== undefined)!;
    return `§${sorted[Number(key.slice(1))].source}§`;
  }).replace(/\s+/g, " ").trim();
}

export async function correctGlossary(source: string, draft: string, entries: GlossaryEntry[],
  generate?: (request: ReturnType<typeof glossaryCorrectionPrompt>) => Promise<string>, introduced: string[] = [], signal?: AbortSignal) {
  const errors = validateGlossary(draft, entries, source, introduced);
  if (!errors.length || !generate) return { text: draft, errors, corrected: false };
  const request = glossaryCorrectionPrompt(source, draft, entries, errors);
  if (introduced.length) request.systemInstruction += `\nTERMS ALREADY INTRODUCED IN THIS CHAPTER:\n${introduced.join("\n")}`;
  try {
    const candidate = await generate(request);
    const remaining = validateGlossary(candidate, entries, source, introduced);
    if (candidate.trim() && !remaining.length && glossaryProseSignature(draft, entries) === glossaryProseSignature(candidate, entries)) return { text: candidate, errors: [], corrected: true };
  } catch (reason) {
    if (signal?.aborted) throw reason;
    console.warn("Glossary correction failed; preserving proofread translation", reason);
  }
  return { text: draft, errors, corrected: false };
}

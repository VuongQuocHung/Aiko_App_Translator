import { parse, stringify } from "yaml";
import { parseGlossary, serializeGlossaryEntry } from "./glossary";

export class ContextBudgetError extends Error {}
export const estimateTokens = (text: string) => Math.ceil(new TextEncoder().encode(text).length / 2);

export interface BudgetRequest {
  systemInstruction: string;
  prompt: string;
  contextText?: string;
  sourceText?: string;
  relevanceText?: string;
  stage?: "translate" | "polish";
  contextTokens?: number;
  maxOutputTokens?: number | null;
  document?: { content: string };
}

export function fitNovelRequest<T extends BudgetRequest>(request: T): T {
  if (!request.stage) return request;
  const output = request.maxOutputTokens || 30000, window = request.contextTokens || 128000;
  if (request.stage === "translate" && estimateTokens(request.sourceText || "") * 2 > output) throw new ContextBudgetError("Nguồn có thể vượt giới hạn đầu ra; cần chia chương.");
  const fits = (prompt: string) => estimateTokens(request.systemInstruction + prompt + (request.document?.content || "")) + output + 512 <= window;
  if (fits(request.prompt)) return request;
  if (request.contextText) {
    const context = parse(request.contextText);
    if (context && typeof context === "object" && context.glossary) {
      const entries = parseGlossary(String(context.glossary));
      const words = new Set((request.relevanceText || request.sourceText || "").toLowerCase().match(/[\p{L}\p{N}]+/gu) || []);
      const relevant = new Set(entries.filter((entry) => `${entry.source} ${entry.target}`.toLowerCase().match(/[\p{L}\p{N}]+/gu)?.some((word) => words.has(word))).map((entry) => entry.source));
      let previous = -1;
      while (previous !== relevant.size) {
        previous = relevant.size;
        const targets = new Set(entries.filter((entry) => relevant.has(entry.source)).map((entry) => entry.target));
        const linked = new Set(entries.filter((entry) => relevant.has(entry.source)).map((entry) => entry.extra_metadata?.canonical));
        for (const entry of entries) if (targets.has(entry.target) || linked.has(entry.source) || relevant.has(entry.extra_metadata?.canonical || "")) relevant.add(entry.source);
      }
      const next = stringify({ ...context, glossary: entries.filter((entry) => relevant.has(entry.source)).map(serializeGlossaryEntry).join("\n") }, { lineWidth: 0 });
      const prompt = request.prompt.replace(request.contextText, next);
      if (fits(prompt)) { console.warn("Context estimate exceeds budget; using relevant glossary and aliases"); return { ...request, prompt, contextText: next }; }
    }
  }
  throw new ContextBudgetError("Nội dung và prompt vượt ngân sách context; không cắt nguồn.");
}

export function splitSource(text: string): [string, string] {
  for (const pattern of [/\n\s*\n/g, /[.!?。！？]\s+/g, /\s+/g]) {
    const cuts = [...text.matchAll(pattern)].map((match) => match.index! + match[0].length).filter((cut) => text.length / 5 < cut && cut < text.length * 4 / 5);
    if (cuts.length) {
      const cut = cuts.sort((a, b) => Math.abs(a - text.length / 2) - Math.abs(b - text.length / 2))[0];
      return [text.slice(0, cut), text.slice(cut)];
    }
  }
  throw new ContextBudgetError("Không tìm thấy ranh giới an toàn để chia chương quá dài.");
}

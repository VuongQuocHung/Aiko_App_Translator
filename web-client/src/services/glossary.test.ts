import { describe, expect, it } from "vitest";
import { parseGlossary, serializeGlossaryEntry, validateGlossary, correctGlossary, glossaryProseSignature } from "./glossary";
import { fitNovelRequest, ContextBudgetError, splitSource } from "./requestBudget";
import { vi } from "vitest";
import { translationContextYaml } from "../App";
import { projectContextYaml } from "./localProjectArchive";
import { polishPrompt, translationPrompt } from "./gemini";
import type { Project } from "../types";

const glossary = `Chain of Heart = Xiềng Xích Trái Tim | type=Skill | first_vi=yes | brackets=yes
Awakened = Thức Tỉnh | type=Rank | first_vi=yes | brackets=yes
Fate Essence = Tinh Hoa Vận Mệnh | type=Concept | first_vi=yes | brackets=no
Lucid = Lucid | type=Name | first_vi=no | brackets=no
Shield = Khiên | type=Artifact | first_vi=no | brackets=yes`;
const valid = "Lucid dùng [Chain of Heart] (Xiềng Xích Trái Tim). [Awakened] (Thức Tỉnh) đến. Fate Essence (Tinh Hoa Vận Mệnh) trào ra. [Chain of Heart], [Awakened], Fate Essence và [Shield].";

describe("glossary metadata", () => {
  it("preserves legacy and extended Unicode entries across serialization", () => {
    const text = "Ōhiroma = Heaven’s Judgment\nA = B=C | type=Alias | first_vi=TRUE | brackets=False | canonical=X=Y";
    const entries = parseGlossary(text);
    expect(entries[0]).toEqual({ source: "Ōhiroma", target: "Heaven’s Judgment" });
    expect(entries[1]).toMatchObject({ first_vi: true, brackets: false, target: "B=C", extra_metadata: { canonical: "X=Y" } });
    expect(parseGlossary(entries.map(serializeGlossaryEntry).join("\n"))).toEqual(entries);
  });
  it("skips invalid entries and uses the last valid duplicate", () => {
    expect(parseGlossary("# Note\nA =\n= B\nA = B | first_vi=yess\nA = C\nA =")).toEqual([{ source: "A", target: "C" }]);
  });
  it("validates all four display cases", () => {
    expect(validateGlossary(valid, parseGlossary(glossary))).toEqual([]);
  });
  it("keeps target-only types while accepting only the plain Vietnamese target", () => {
    const entries = parseGlossary("blood blade = huyết kiếm | type=Skill | first_vi=yes | brackets=yes | target_only=yes");
    expect(validateGlossary("thanh huyết kiếm lóe lên", entries, "A blood blade flashed.")).toEqual([]);
    expect(validateGlossary("blood blade", entries).join("\n")).toContain("target_only_requires_vietnamese");
    expect(validateGlossary("[huyết kiếm]", entries).join("\n")).toContain("target_only_plain_vietnamese");
    expect(entries[0]).toMatchObject({ type: "Skill", extra_metadata: { target_only: "yes" } });
    expect(parseGlossary(serializeGlossaryEntry(entries[0]))).toEqual(entries);
  });
  it("makes Common obey display flags instead of overriding them", () => {
    const entries = parseGlossary("Empire = Đế Quốc | type=Common | first_vi=yes | brackets=yes");
    expect(validateGlossary("[Empire] (Đế Quốc) và [Empire]", entries, "Empire and Empire")).toEqual([]);
    expect(validateGlossary("[Empire]", entries).join("\n")).toContain("missing_first_annotation");
    expect(validateGlossary("Đế Quốc", entries).join("\n")).toContain("vietnamese_without_canonical");
  });
  it("supports first_en as the mutually exclusive reverse of first_vi", () => {
    const entries = parseGlossary("Fate Essence = Tinh Hoa Vận Mệnh | type=Concept | first_en=yes | brackets=yes");
    const valid = "[Tinh Hoa Vận Mệnh] (Fate Essence) trào lên. [Tinh Hoa Vận Mệnh] dần lắng xuống.";
    expect(validateGlossary(valid, entries, "Fate Essence surged. Fate Essence settled.")).toEqual([]);
    expect(validateGlossary("[Tinh Hoa Vận Mệnh]", entries).join("\n")).toContain("missing_first_english_annotation");
    expect(validateGlossary("Fate Essence", entries).join("\n")).toContain("english_without_vietnamese");
    expect(parseGlossary(serializeGlossaryEntry(entries[0]))).toEqual(entries);
    expect(parseGlossary("A = B | type=Concept | first_vi=yes | first_en=yes")[0]).toMatchObject({ first_vi: true, first_en: false });
  });
  it.each([
    ["Lucid (Lucid)", "forbidden_annotation"],
    ["Awakened (Thức Tỉnh)", "missing_brackets"],
    ["[[Awakened]] (Thức Tỉnh)", "nested_brackets"],
    ["[Awakened]", "missing_first_annotation"],
    ["[Awakened] (Thức Tỉnh) [Awakened] (Thức Tỉnh)", "repeated_annotation"],
    ["người Thức Tỉnh", "vietnamese_without_canonical"],
  ])("detects %s", (text, error) => {
    expect(validateGlossary(text, parseGlossary(glossary)).join("\n")).toContain(error);
  });
  it("resets chapters and carries chunk state without matching substrings", () => {
    const entries = parseGlossary(glossary);
    expect(validateGlossary(`Chapter 1: Awakened\n${valid}\nChương 2: Awakened\n${valid}`, entries)).toEqual([]);
    expect(validateGlossary("[Awakened]", entries, "Awakened", ["Awakened"])).toEqual([]);
    expect(validateGlossary("UnAwakened SuperLucid", entries)).toEqual([]);
    expect(validateGlossary("", entries, "Awakened").join("\n")).toContain("missing_canonical");
  });
  it("preserves full glossary and independent style/role/task prompts", () => {
    const project: Project = { id: "p", name: "P", sourceLanguage: "English", targetLanguage: "Vietnamese", characters: "", contextV1: "", styleNotes: "STYLE\n\nMore style", glossary: parseGlossary(glossary).map((entry, index) => ({ ...entry, id: String(index) })), createdAt: "", updatedAt: "" };
    const context = translationContextYaml(project, "Lucid");
    expect(context).toContain("Chain of Heart");
    expect(context).toContain("first_vi=yes");
    expect(projectContextYaml(project)).toContain("type=Skill");
    const translation = translationPrompt({ title: "T", source: "SOURCE", role: "ROLE", task: "TASK", context, pronouns: "", previousChapters: "", from: "English", to: "Vietnamese" });
    expect(translation.systemInstruction).toContain("ROLE");
    expect(translation.systemInstruction).toContain("More style");
    expect(translation.prompt).toContain("TASK");
    const polish = polishPrompt("SOURCE", "DRAFT", context, "PROOF ROLE", "PROOF TASK");
    expect(polish.systemInstruction).toContain("PROOF ROLE");
    expect(polish.prompt).toContain("SOURCE");
    expect(polish.prompt).toContain("DRAFT");
  });
  it("only filters after overflow and preserves source and aliases", () => {
    const context = "glossary: |\n  A = B | type=Skill\n  AliasA = AliasB | canonical=A\n" + Array.from({ length: 100 }, (_, i) => `  Unrelated${i} = Distant${i}\n`).join("");
    const request = { stage: "translate" as const, sourceText: "A", contextText: context, prompt: `${context}\nSOURCE A`, systemInstruction: "RULES", contextTokens: 10000, maxOutputTokens: 100 };
    expect(fitNovelRequest(request)).toBe(request);
    const fitted = fitNovelRequest({ ...request, contextTokens: 800 });
    expect(fitted.prompt).toContain("AliasA");
    expect(fitted.prompt).toContain("SOURCE A");
    expect(fitted.prompt).not.toContain("Unrelated99");
    expect(() => fitNovelRequest({ ...request, contextTokens: 200 })).toThrow(ContextBudgetError);
    const source = "One paragraph.\n\nAnother paragraph.\n\nThe last paragraph.";
    expect(splitSource(source).join("")).toBe(source);
  });
  it("corrects once, revalidates and refuses changes to unrelated prose", async () => {
    const entries = parseGlossary(glossary);
    const draft = "[Awakened] bước tới. Cậu đóng cửa.";
    const corrected = "[Awakened] (Thức Tỉnh) bước tới. Cậu đóng cửa.";
    const generate = vi.fn().mockResolvedValue(corrected);
    expect(await correctGlossary("Awakened", draft, entries, generate)).toMatchObject({ text: corrected, errors: [], corrected: true });
    expect(generate).toHaveBeenCalledTimes(1);
    expect(glossaryProseSignature(draft, entries)).toBe(glossaryProseSignature(corrected, entries));
    generate.mockResolvedValue("[Awakened] (Thức Tỉnh)");
    expect((await correctGlossary("Awakened", draft, entries, generate)).text).toBe(draft);
    generate.mockResolvedValue("");
    expect((await correctGlossary("Awakened", draft, entries, generate)).text).toBe(draft);
  });
});

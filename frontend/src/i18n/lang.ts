export type Lang = "zh" | "en";

export function asLang(value: unknown): Lang {
  return value === "en" ? "en" : "zh";
}

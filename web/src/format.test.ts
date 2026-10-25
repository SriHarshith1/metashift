import { comparePatchesDesc, formatChange, formatRate } from "./format";

test("formatChange shows old and new", () => {
  expect(formatChange("40", "45")).toBe("40 → 45");
});

test("formatChange shows a dash for null values", () => {
  expect(formatChange(null, "45")).toBe("— → 45");
  expect(formatChange("40", null)).toBe("40 → —");
});

test("formatRate formats a percentage", () => expect(formatRate(49.1)).toBe("49.1%"));

test("formatRate shows no stats for null", () => expect(formatRate(null)).toBe("no stats"));

test("comparePatchesDesc sorts newest first by number, not by text", () => {
  expect(["26.9", "26.21", "25.24", "26.10"].sort(comparePatchesDesc)).toEqual(["26.21", "26.10", "26.9", "25.24"]);
});

import { describe, it, expect } from "vitest";
import { cn } from "@/lib/utils";

describe("cn (Duuutah AI class-name helper)", () => {
  it("joins multiple class names with spaces", () => {
    expect(cn("foo", "bar")).toBe("foo bar");
  });

  it("skips falsy values", () => {
    expect(cn("foo", null, undefined, false, "bar")).toBe("foo bar");
  });

  it("returns empty string when given no args", () => {
    expect(cn()).toBe("");
  });

  it("supports conditional class objects from clsx", () => {
    expect(cn({ "is-active": true, "is-disabled": false })).toBe("is-active");
  });

  it("supports nested arrays from clsx", () => {
    expect(cn(["a", ["b", { c: true }]])).toBe("a b c");
  });

  it("merges conflicting tailwind utilities via twMerge (later wins)", () => {
    expect(cn("p-2", "p-4")).toBe("p-4");
  });

  it("merges conflicting tailwind directional utilities correctly", () => {
    expect(cn("text-red-500", "text-blue-500")).toBe("text-blue-500");
  });

  it("preserves non-conflicting utilities", () => {
    expect(cn("rounded-md", "bg-white", "shadow")).toBe("rounded-md bg-white shadow");
  });

  it("handles a mix of strings, objects, and arrays", () => {
    const result = cn("base", ["a", "b"], { c: true, d: false }, "e");
    expect(result).toBe("base a b c e");
  });

  it("is stable when called with the same arguments", () => {
    const a = cn("p-2", "text-sm");
    const b = cn("p-2", "text-sm");
    expect(a).toBe(b);
  });
});

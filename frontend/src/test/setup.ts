import "@testing-library/jest-dom";
import { afterAll, afterEach, beforeAll, vi } from "vitest";
import { cleanup } from "@testing-library/react";
import "./utils/mock-clerk";
import { server } from "./utils/msw-server";

beforeAll(() => {
  server.listen({ onUnhandledRequest: "warn" });
});

afterEach(() => {
  cleanup();
  server.resetHandlers();
  localStorage.clear();
});

afterAll(() => {
  server.close();
});

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: typeof ResizeObserver }).ResizeObserver =
  ResizeObserverMock as unknown as typeof ResizeObserver;

if (!("IntersectionObserver" in globalThis)) {
  class IntersectionObserverMock {
    observe() {}
    unobserve() {}
    disconnect() {}
    takeRecords() {
      return [];
    }
    root = null;
    rootMargin = "";
    thresholds = [];
  }
  (globalThis as unknown as { IntersectionObserver: typeof IntersectionObserver }).IntersectionObserver =
    IntersectionObserverMock as unknown as typeof IntersectionObserver;
}

Object.defineProperty(window, "matchMedia", {
  writable: true,
  configurable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

if (!(globalThis as unknown as { URL: typeof URL }).URL.createObjectURL) {
  (globalThis as unknown as { URL: typeof URL & { createObjectURL?: () => string } }).URL.createObjectURL =
    vi.fn(() => "blob:mock");
}
if (!(globalThis as unknown as { URL: typeof URL & { revokeObjectURL?: () => void } }).URL.revokeObjectURL) {
  (globalThis as unknown as { URL: typeof URL & { revokeObjectURL?: () => void } }).URL.revokeObjectURL =
    vi.fn();
}

// scrollIntoView shim — Radix UI components call this in jsdom
if (typeof HTMLElement !== "undefined" && !HTMLElement.prototype.scrollIntoView) {
  HTMLElement.prototype.scrollIntoView = vi.fn();
}

// hasPointerCapture / setPointerCapture / releasePointerCapture shims —
// Radix UI's Select (and other primitives) call these on pointer events in
// jsdom, where they aren't implemented.
if (typeof HTMLElement !== "undefined") {
  if (!("hasPointerCapture" in HTMLElement.prototype)) {
    (HTMLElement.prototype as unknown as Record<string, unknown>).hasPointerCapture = vi.fn(
      () => false
    );
  }
  if (!("setPointerCapture" in HTMLElement.prototype)) {
    (HTMLElement.prototype as unknown as Record<string, unknown>).setPointerCapture = vi.fn();
  }
  if (!("releasePointerCapture" in HTMLElement.prototype)) {
    (HTMLElement.prototype as unknown as Record<string, unknown>).releasePointerCapture = vi.fn();
  }
}

// Filter noisy jsdom-not-implemented warnings while preserving real errors
const originalError = console.error;
console.error = (...args: unknown[]) => {
  const msg = String(args[0] ?? "");
  if (msg.includes("Not implemented: HTMLFormElement.prototype.submit")) return;
  if (msg.includes("Not implemented: navigation")) return;
  originalError(...args);
};

// React Router v6 prints v7 migration hints as console.warn — informational
// and not actionable inside the test suite. Suppress to keep test output clean.
const originalWarn = console.warn;
console.warn = (...args: unknown[]) => {
  const msg = String(args[0] ?? "");
  if (msg.includes("React Router Future Flag Warning")) return;
  originalWarn(...args);
};

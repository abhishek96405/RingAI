import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useIsMobile } from "@/hooks/use-mobile";

const MOBILE_WIDTH = 500;
const DESKTOP_WIDTH = 1280;

function installMatchMedia(opts: { onChange: (cb: () => void) => void }) {
  const listeners = new Set<(ev: MediaQueryListEvent) => void>();
  const mql = {
    matches: false,
    media: "",
    onchange: null,
    addEventListener: (_: string, cb: (ev: MediaQueryListEvent) => void) => {
      listeners.add(cb);
      opts.onChange(() => cb({} as MediaQueryListEvent));
    },
    removeEventListener: (_: string, cb: (ev: MediaQueryListEvent) => void) => {
      listeners.delete(cb);
    },
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  };
  window.matchMedia = vi.fn().mockReturnValue(mql);
  return { mql, listeners };
}

describe("useIsMobile (Duuutah AI responsive hook)", () => {
  const originalInner = window.innerWidth;

  beforeEach(() => {
    Object.defineProperty(window, "innerWidth", {
      writable: true,
      configurable: true,
      value: DESKTOP_WIDTH,
    });
  });

  afterEach(() => {
    Object.defineProperty(window, "innerWidth", {
      writable: true,
      configurable: true,
      value: originalInner,
    });
  });

  it("returns false on a desktop-width viewport (>=768)", () => {
    Object.defineProperty(window, "innerWidth", { value: DESKTOP_WIDTH, configurable: true });
    installMatchMedia({ onChange: () => {} });
    const { result } = renderHook(() => useIsMobile());
    expect(result.current).toBe(false);
  });

  it("returns true on a mobile-width viewport (<768)", () => {
    Object.defineProperty(window, "innerWidth", { value: MOBILE_WIDTH, configurable: true });
    installMatchMedia({ onChange: () => {} });
    const { result } = renderHook(() => useIsMobile());
    expect(result.current).toBe(true);
  });

  it("returns true exactly at the 767 boundary and false at 768", () => {
    Object.defineProperty(window, "innerWidth", { value: 767, configurable: true });
    installMatchMedia({ onChange: () => {} });
    const { result: r767 } = renderHook(() => useIsMobile());
    expect(r767.current).toBe(true);

    Object.defineProperty(window, "innerWidth", { value: 768, configurable: true });
    installMatchMedia({ onChange: () => {} });
    const { result: r768 } = renderHook(() => useIsMobile());
    expect(r768.current).toBe(false);
  });

  it("updates the result when matchMedia fires a change event", () => {
    Object.defineProperty(window, "innerWidth", { value: DESKTOP_WIDTH, configurable: true });
    let fireChange: (() => void) | null = null;
    installMatchMedia({
      onChange: (cb) => {
        fireChange = cb;
      },
    });

    const { result } = renderHook(() => useIsMobile());
    expect(result.current).toBe(false);

    act(() => {
      Object.defineProperty(window, "innerWidth", { value: MOBILE_WIDTH, configurable: true });
      fireChange?.();
    });

    expect(result.current).toBe(true);
  });

  it("removes its event listener on unmount", () => {
    const removeSpy = vi.fn();
    const mql = {
      matches: false,
      media: "",
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: removeSpy,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    };
    window.matchMedia = vi.fn().mockReturnValue(mql);

    const { unmount } = renderHook(() => useIsMobile());
    unmount();

    expect(removeSpy).toHaveBeenCalled();
  });
});

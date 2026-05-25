import { describe, it, expect } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { toast, useToast, reducer } from "@/hooks/use-toast";

describe("use-toast reducer (Duuutah AI toast system)", () => {
  it("ADD_TOAST inserts a toast at the head of the list", () => {
    const state = reducer(
      { toasts: [] },
      { type: "ADD_TOAST", toast: { id: "t1", title: "Hello" } as never }
    );
    expect(state.toasts).toHaveLength(1);
    expect(state.toasts[0].id).toBe("t1");
  });

  it("ADD_TOAST enforces the TOAST_LIMIT of 1", () => {
    let state = reducer(
      { toasts: [] },
      { type: "ADD_TOAST", toast: { id: "first", title: "A" } as never }
    );
    state = reducer(state, {
      type: "ADD_TOAST",
      toast: { id: "second", title: "B" } as never,
    });
    expect(state.toasts).toHaveLength(1);
    expect(state.toasts[0].id).toBe("second");
  });

  it("UPDATE_TOAST patches a matching toast in place", () => {
    let state = reducer(
      { toasts: [] },
      { type: "ADD_TOAST", toast: { id: "t1", title: "Hello" } as never }
    );
    state = reducer(state, {
      type: "UPDATE_TOAST",
      toast: { id: "t1", title: "Hi" } as never,
    });
    expect(state.toasts[0].title).toBe("Hi");
  });

  it("DISMISS_TOAST marks a single toast as not open", () => {
    let state = reducer(
      { toasts: [] },
      { type: "ADD_TOAST", toast: { id: "t1", title: "Hello", open: true } as never }
    );
    state = reducer(state, { type: "DISMISS_TOAST", toastId: "t1" });
    expect(state.toasts[0].open).toBe(false);
  });

  it("DISMISS_TOAST with no id marks all toasts as closed", () => {
    let state = reducer(
      { toasts: [] },
      { type: "ADD_TOAST", toast: { id: "t1", title: "x", open: true } as never }
    );
    state = reducer(state, { type: "DISMISS_TOAST" });
    expect(state.toasts.every((t) => !t.open)).toBe(true);
  });

  it("REMOVE_TOAST drops the matching toast", () => {
    let state = reducer(
      { toasts: [] },
      { type: "ADD_TOAST", toast: { id: "t1", title: "x" } as never }
    );
    state = reducer(state, { type: "REMOVE_TOAST", toastId: "t1" });
    expect(state.toasts).toHaveLength(0);
  });

  it("REMOVE_TOAST with no id wipes the list", () => {
    let state = reducer(
      { toasts: [] },
      { type: "ADD_TOAST", toast: { id: "t1", title: "x" } as never }
    );
    state = reducer(state, { type: "REMOVE_TOAST" });
    expect(state.toasts).toHaveLength(0);
  });
});

describe("toast() and useToast()", () => {
  it("toast() returns an id, dismiss and update functions", () => {
    const { id, dismiss, update } = toast({ title: "Saved" });
    expect(typeof id).toBe("string");
    expect(typeof dismiss).toBe("function");
    expect(typeof update).toBe("function");
    dismiss();
  });

  it("useToast() exposes the current toasts and a toast() function", () => {
    const { result } = renderHook(() => useToast());
    expect(typeof result.current.toast).toBe("function");

    act(() => {
      result.current.toast({ title: "Hello" });
    });

    expect(result.current.toasts.length).toBeGreaterThanOrEqual(1);

    act(() => result.current.dismiss());
  });
});

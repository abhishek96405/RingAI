import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import type { Mock } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useWebSocketNotifications } from "@/hooks/useWebSocketNotifications";
import { getAuthToken } from "@/lib/api";

// A6-2: the hook now fetches a fresh Clerk token for every connection attempt
// and refuses to open an unauthenticated socket. Mock the token source.
vi.mock("@/lib/api", () => ({
  getAuthToken: vi.fn(async () => "test-token"),
}));

const mockGetAuthToken = getAuthToken as Mock;

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  static OPEN = 1;
  static CLOSED = 3;

  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onclose: ((ev: CloseEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  send = vi.fn();
  close = vi.fn(function (this: MockWebSocket, code?: number, reason?: string) {
    this.readyState = MockWebSocket.CLOSED;
    if (this.onclose) {
      this.onclose({ code: code ?? 1000, reason: reason ?? "" } as CloseEvent);
    }
  });

  constructor(public url: string) {
    MockWebSocket.instances.push(this);
  }

  acceptOpen() {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.();
  }

  emit(payload: unknown) {
    const data = typeof payload === "string" ? payload : JSON.stringify(payload);
    this.onmessage?.({ data } as MessageEvent);
  }

  triggerClose(code = 1006, reason = "abnormal") {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.({ code, reason } as CloseEvent);
  }
}

const installMockWebSocket = () => {
  MockWebSocket.instances = [];
  vi.stubGlobal("WebSocket", MockWebSocket as unknown as typeof WebSocket);
};

// connect() is async (it awaits getAuthToken). Flush the pending microtasks so
// the socket is created before assertions run.
const flush = async () => {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
};

// Render the hook with a default restaurantId (required now that the socket is
// gated on tenant + token) and wait for the async connect to open the socket.
const mountHook = async (
  options: Parameters<typeof useWebSocketNotifications>[0] = {}
) => {
  const rendered = renderHook(() =>
    useWebSocketNotifications({ restaurantId: "rest_default", ...options })
  );
  await flush();
  return rendered;
};

describe("useWebSocketNotifications (Duuutah AI live monitor)", () => {
  beforeEach(() => {
    installMockWebSocket();
    mockGetAuthToken.mockResolvedValue("test-token");
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
    vi.unstubAllGlobals();
    mockGetAuthToken.mockReset();
  });

  it("opens a WebSocket and transitions to connected on open", async () => {
    const { result } = await mountHook({ autoReconnect: false });
    expect(result.current.connected).toBe(false);
    expect(MockWebSocket.instances).toHaveLength(1);

    act(() => MockWebSocket.instances[0].acceptOpen());
    expect(result.current.connected).toBe(true);
  });

  it("appends restaurant_id query param when provided", async () => {
    await mountHook({ restaurantId: "rest_abc", autoReconnect: false });
    expect(MockWebSocket.instances[0].url).toContain("restaurant_id=rest_abc");
  });

  it("URL-encodes the restaurant id", async () => {
    await mountHook({ restaurantId: "rest with spaces", autoReconnect: false });
    expect(MockWebSocket.instances[0].url).toContain("restaurant_id=rest%20with%20spaces");
  });

  it("includes the auth token query param (A6-2)", async () => {
    await mountHook({ restaurantId: "rest_abc", autoReconnect: false });
    expect(MockWebSocket.instances[0].url).toContain("token=test-token");
  });

  it("does NOT open a socket without a token and retries", async () => {
    mockGetAuthToken.mockResolvedValue(null);
    await mountHook({ restaurantId: "rest_abc", autoReconnect: true, reconnectDelay: 1000 });

    // No token => no socket opened.
    expect(MockWebSocket.instances).toHaveLength(0);

    // Once a token becomes available, the scheduled retry opens the socket.
    mockGetAuthToken.mockResolvedValue("test-token");
    await act(async () => {
      vi.advanceTimersByTime(1000);
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(MockWebSocket.instances).toHaveLength(1);
  });

  it("does NOT open a socket without a restaurant id and retries", async () => {
    renderHook(() =>
      useWebSocketNotifications({ restaurantId: null, autoReconnect: true, reconnectDelay: 1000 })
    );
    await flush();
    expect(MockWebSocket.instances).toHaveLength(0);
  });

  it("ignores ping/pong messages without surfacing as a notification", async () => {
    const onNotification = vi.fn();
    const { result } = await mountHook({ onNotification, autoReconnect: false });
    act(() => MockWebSocket.instances[0].acceptOpen());

    act(() => MockWebSocket.instances[0].emit("ping"));
    act(() => MockWebSocket.instances[0].emit("pong"));

    expect(onNotification).not.toHaveBeenCalled();
    expect(result.current.notifications).toHaveLength(0);
  });

  it("responds to ping with pong", async () => {
    await mountHook({ autoReconnect: false });
    act(() => MockWebSocket.instances[0].acceptOpen());

    act(() => MockWebSocket.instances[0].emit("ping"));
    expect(MockWebSocket.instances[0].send).toHaveBeenCalledWith("pong");
  });

  it("ignores 'connected' control messages", async () => {
    const onNotification = vi.fn();
    await mountHook({ onNotification, autoReconnect: false });
    act(() => MockWebSocket.instances[0].acceptOpen());

    act(() =>
      MockWebSocket.instances[0].emit({ type: "connected", message: "hello" })
    );
    expect(onNotification).not.toHaveBeenCalled();
  });

  it("captures and surfaces notification events", async () => {
    const onNotification = vi.fn();
    const { result } = await mountHook({ onNotification, autoReconnect: false });
    act(() => MockWebSocket.instances[0].acceptOpen());

    act(() =>
      MockWebSocket.instances[0].emit({
        type: "notification",
        event: "call",
        title: "Incoming call",
        message: "+1 555 0100",
        data: { call_id: "c1" },
        priority: "high",
        timestamp: "2026-05-24T12:00:00Z",
      })
    );

    expect(onNotification).toHaveBeenCalledWith(
      expect.objectContaining({
        event: "call",
        title: "Incoming call",
        priority: "high",
        data: { call_id: "c1" },
      })
    );
    expect(result.current.notifications).toHaveLength(1);
    expect(result.current.notifications[0].title).toBe("Incoming call");
  });

  it("caps stored notifications at 50", async () => {
    const { result } = await mountHook({ autoReconnect: false });
    act(() => MockWebSocket.instances[0].acceptOpen());

    act(() => {
      for (let i = 0; i < 60; i++) {
        MockWebSocket.instances[0].emit({
          type: "notification",
          event: "order",
          title: `Order ${i}`,
          message: "",
          data: {},
          priority: "normal",
          timestamp: "2026-05-24T12:00:00Z",
        });
      }
    });

    expect(result.current.notifications).toHaveLength(50);
    expect(result.current.notifications[0].title).toBe("Order 59");
  });

  it("clearNotifications empties the buffer", async () => {
    const { result } = await mountHook({ autoReconnect: false });
    act(() => MockWebSocket.instances[0].acceptOpen());
    act(() =>
      MockWebSocket.instances[0].emit({
        type: "notification",
        event: "info",
        title: "t",
        message: "m",
        data: {},
        priority: "normal",
        timestamp: "",
      })
    );
    expect(result.current.notifications).toHaveLength(1);

    act(() => result.current.clearNotifications());
    expect(result.current.notifications).toHaveLength(0);
  });

  it("ignores malformed JSON messages without crashing", async () => {
    const onNotification = vi.fn();
    await mountHook({ onNotification, autoReconnect: false });
    act(() => MockWebSocket.instances[0].acceptOpen());

    act(() => MockWebSocket.instances[0].emit("not-valid-json{{{"));
    expect(onNotification).not.toHaveBeenCalled();
  });

  it("sendMessage only writes when the socket is OPEN", async () => {
    const { result } = await mountHook({ autoReconnect: false });
    // Before open
    act(() => result.current.sendMessage("hello"));
    expect(MockWebSocket.instances[0].send).not.toHaveBeenCalled();

    // After open
    act(() => MockWebSocket.instances[0].acceptOpen());
    act(() => result.current.sendMessage("hello"));
    expect(MockWebSocket.instances[0].send).toHaveBeenCalledWith("hello");
  });

  it("auto-reconnects after close when autoReconnect=true", async () => {
    await mountHook({ autoReconnect: true, reconnectDelay: 1000 });
    act(() => MockWebSocket.instances[0].acceptOpen());
    expect(MockWebSocket.instances).toHaveLength(1);

    act(() => MockWebSocket.instances[0].triggerClose(1006));
    expect(MockWebSocket.instances).toHaveLength(1);

    await act(async () => {
      vi.advanceTimersByTime(1000);
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(MockWebSocket.instances).toHaveLength(2);
  });

  it("does not reconnect when autoReconnect=false", async () => {
    await mountHook({ autoReconnect: false, reconnectDelay: 1000 });
    act(() => MockWebSocket.instances[0].acceptOpen());
    act(() => MockWebSocket.instances[0].triggerClose(1006));

    await act(async () => {
      vi.advanceTimersByTime(5000);
      await Promise.resolve();
    });
    expect(MockWebSocket.instances).toHaveLength(1);
  });

  it("sends periodic ping when connected", async () => {
    await mountHook({ autoReconnect: false });
    act(() => MockWebSocket.instances[0].acceptOpen());
    MockWebSocket.instances[0].send.mockClear();

    act(() => vi.advanceTimersByTime(25_000));
    expect(MockWebSocket.instances[0].send).toHaveBeenCalledWith("ping");
  });

  it("closes the socket and skips reconnect on unmount", async () => {
    const { unmount } = await mountHook({ autoReconnect: true, reconnectDelay: 500 });
    act(() => MockWebSocket.instances[0].acceptOpen());
    const ws = MockWebSocket.instances[0];

    unmount();
    expect(ws.close).toHaveBeenCalled();

    await act(async () => {
      vi.advanceTimersByTime(2000);
      await Promise.resolve();
    });
    expect(MockWebSocket.instances).toHaveLength(1);
  });

  it("flips connected back to false when the socket closes", async () => {
    const { result } = await mountHook({ autoReconnect: false });
    act(() => MockWebSocket.instances[0].acceptOpen());
    expect(result.current.connected).toBe(true);

    act(() => MockWebSocket.instances[0].triggerClose(1006));
    expect(result.current.connected).toBe(false);
  });
});

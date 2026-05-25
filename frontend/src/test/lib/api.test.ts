import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "@/test/utils/msw-server";
import {
  api,
  bootstrapSession,
  clearRestaurantId,
  createMenuItem,
  createRestaurant,
  getAnalyticsSummary,
  getCall,
  getCalls,
  getConfig,
  getMenuItems,
  getRestaurant,
  getRestaurantId,
  selectRestaurant,
  setAuthTokenGetter,
  setRestaurantId,
  updateRestaurant,
} from "@/lib/api";

const ACTIVE_RESTAURANT_KEY = "ringai.activeRestaurantId";

describe("api client storage helpers", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("setRestaurantId persists a sanitized value", () => {
    setRestaurantId("rest_123");
    expect(localStorage.getItem(ACTIVE_RESTAURANT_KEY)).toBe("rest_123");
  });

  it("setRestaurantId trims whitespace", () => {
    setRestaurantId("  rest_456  ");
    expect(localStorage.getItem(ACTIVE_RESTAURANT_KEY)).toBe("rest_456");
  });

  it("setRestaurantId removes the key when given the string 'null'", () => {
    localStorage.setItem(ACTIVE_RESTAURANT_KEY, "rest_old");
    setRestaurantId("null");
    expect(localStorage.getItem(ACTIVE_RESTAURANT_KEY)).toBeNull();
  });

  it("setRestaurantId removes the key when given the string 'undefined'", () => {
    localStorage.setItem(ACTIVE_RESTAURANT_KEY, "rest_old");
    setRestaurantId("undefined");
    expect(localStorage.getItem(ACTIVE_RESTAURANT_KEY)).toBeNull();
  });

  it("setRestaurantId removes the key when given an empty string", () => {
    localStorage.setItem(ACTIVE_RESTAURANT_KEY, "rest_old");
    setRestaurantId("");
    expect(localStorage.getItem(ACTIVE_RESTAURANT_KEY)).toBeNull();
  });

  it("setRestaurantId removes the key when given null", () => {
    localStorage.setItem(ACTIVE_RESTAURANT_KEY, "rest_old");
    setRestaurantId(null);
    expect(localStorage.getItem(ACTIVE_RESTAURANT_KEY)).toBeNull();
  });

  it("getRestaurantId returns the stored value", () => {
    localStorage.setItem(ACTIVE_RESTAURANT_KEY, "rest_xyz");
    expect(getRestaurantId()).toBe("rest_xyz");
  });

  it("getRestaurantId returns null when not set", () => {
    expect(getRestaurantId()).toBeNull();
  });

  it("getRestaurantId returns null for sentinel string 'null'", () => {
    localStorage.setItem(ACTIVE_RESTAURANT_KEY, "null");
    expect(getRestaurantId()).toBeNull();
  });

  it("clearRestaurantId removes the key", () => {
    localStorage.setItem(ACTIVE_RESTAURANT_KEY, "rest_abc");
    clearRestaurantId();
    expect(localStorage.getItem(ACTIVE_RESTAURANT_KEY)).toBeNull();
  });
});

describe("api auth interceptor", () => {
  afterEach(() => {
    setAuthTokenGetter(null);
  });

  it("does not attach an Authorization header when no getter is configured", async () => {
    let observedAuth: string | undefined;
    server.use(
      http.get("*/api/status", ({ request }) => {
        observedAuth = request.headers.get("authorization") ?? undefined;
        return HttpResponse.json({ ok: true });
      })
    );

    await api.get("/status");
    expect(observedAuth).toBeUndefined();
  });

  it("attaches a Bearer token when the getter returns a value", async () => {
    setAuthTokenGetter(async () => "test-jwt-token");
    let observedAuth: string | undefined;
    server.use(
      http.get("*/api/status", ({ request }) => {
        observedAuth = request.headers.get("authorization") ?? undefined;
        return HttpResponse.json({ ok: true });
      })
    );

    await api.get("/status");
    expect(observedAuth).toBe("Bearer test-jwt-token");
  });

  it("does not attach Authorization when the getter returns null", async () => {
    setAuthTokenGetter(async () => null);
    let observedAuth: string | undefined;
    server.use(
      http.get("*/api/status", ({ request }) => {
        observedAuth = request.headers.get("authorization") ?? undefined;
        return HttpResponse.json({ ok: true });
      })
    );

    await api.get("/status");
    expect(observedAuth).toBeUndefined();
  });

  it("calls the getter for every request", async () => {
    const getter = vi.fn().mockResolvedValue("tok");
    setAuthTokenGetter(getter);
    server.use(http.get("*/api/status", () => HttpResponse.json({ ok: true })));

    await api.get("/status");
    await api.get("/status");

    expect(getter).toHaveBeenCalledTimes(2);
  });
});

describe("requireRestaurantId enforcement", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("getRestaurant throws when no restaurant id is provided or stored", () => {
    expect(() => getRestaurant()).toThrow(/no active restaurant/i);
  });

  it("getConfig throws when no restaurant id is available", () => {
    expect(() => getConfig()).toThrow(/no active restaurant/i);
  });

  it("getMenuItems throws when no restaurant id is available", () => {
    expect(() => getMenuItems()).toThrow(/no active restaurant/i);
  });

  it("getCalls throws when no restaurant id is available", () => {
    expect(() => getCalls()).toThrow(/no active restaurant/i);
  });

  it("getAnalyticsSummary throws when no restaurant id is available", () => {
    expect(() => getAnalyticsSummary()).toThrow(/no active restaurant/i);
  });

  it("createMenuItem throws when no restaurant id is available", () => {
    expect(() => createMenuItem(null, {})).toThrow(/no active restaurant/i);
  });

  it("updateRestaurant throws when no restaurant id is available", () => {
    expect(() => updateRestaurant(null, {})).toThrow(/no active restaurant/i);
  });

  it("falls back to the stored restaurant id when none is passed explicitly", async () => {
    localStorage.setItem(ACTIVE_RESTAURANT_KEY, "rest_stored");
    let observedPath: string | undefined;
    server.use(
      http.get("*/api/restaurants/:id", ({ params }) => {
        observedPath = params.id as string;
        return HttpResponse.json({ id: params.id });
      })
    );

    await getRestaurant();
    expect(observedPath).toBe("rest_stored");
  });

  it("prefers an explicit restaurant id over the stored one", async () => {
    localStorage.setItem(ACTIVE_RESTAURANT_KEY, "rest_stored");
    let observedPath: string | undefined;
    server.use(
      http.get("*/api/restaurants/:id", ({ params }) => {
        observedPath = params.id as string;
        return HttpResponse.json({ id: params.id });
      })
    );

    await getRestaurant("rest_explicit");
    expect(observedPath).toBe("rest_explicit");
  });
});

describe("bootstrapSession", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("calls /api/me/bootstrap without restaurant_id when none is known", async () => {
    let observedParams: URLSearchParams | undefined;
    server.use(
      http.get("*/api/me/bootstrap", ({ request }) => {
        observedParams = new URL(request.url).searchParams;
        return HttpResponse.json({ active_restaurant: null, restaurants: [] });
      })
    );

    await bootstrapSession();
    expect(observedParams?.get("restaurant_id")).toBeNull();
  });

  it("passes restaurant_id when one is provided", async () => {
    let observedParams: URLSearchParams | undefined;
    server.use(
      http.get("*/api/me/bootstrap", ({ request }) => {
        observedParams = new URL(request.url).searchParams;
        return HttpResponse.json({ active_restaurant: null, restaurants: [] });
      })
    );

    await bootstrapSession("rest_explicit");
    expect(observedParams?.get("restaurant_id")).toBe("rest_explicit");
  });

  it("syncs active_restaurant.id to localStorage", async () => {
    server.use(
      http.get("*/api/me/bootstrap", () =>
        HttpResponse.json({
          active_restaurant: { id: "rest_active" },
          restaurants: [{ id: "rest_active" }],
        })
      )
    );

    await bootstrapSession();
    expect(getRestaurantId()).toBe("rest_active");
  });

  it("clears localStorage when bootstrap returns no restaurants and no active_restaurant", async () => {
    localStorage.setItem(ACTIVE_RESTAURANT_KEY, "stale");
    server.use(
      http.get("*/api/me/bootstrap", () =>
        HttpResponse.json({ active_restaurant: null, restaurants: [] })
      )
    );

    await bootstrapSession();
    expect(getRestaurantId()).toBeNull();
  });

  it("preserves existing restaurant id when bootstrap returns restaurants but no active_restaurant", async () => {
    localStorage.setItem(ACTIVE_RESTAURANT_KEY, "rest_existing");
    server.use(
      http.get("*/api/me/bootstrap", () =>
        HttpResponse.json({
          active_restaurant: null,
          restaurants: [{ id: "rest_existing" }],
        })
      )
    );

    await bootstrapSession();
    expect(getRestaurantId()).toBe("rest_existing");
  });
});

describe("specific API call helpers", () => {
  beforeEach(() => {
    localStorage.setItem(ACTIVE_RESTAURANT_KEY, "rest_test");
  });

  it("selectRestaurant posts to /me/select-restaurant and stores the id", async () => {
    let body: unknown;
    server.use(
      http.post("*/api/me/select-restaurant", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ ok: true });
      })
    );

    await selectRestaurant("rest_new");
    expect(body).toEqual({ restaurant_id: "rest_new" });
    expect(getRestaurantId()).toBe("rest_new");
  });

  it("createRestaurant stores the returned id", async () => {
    server.use(
      http.post("*/api/restaurants", () =>
        HttpResponse.json({ id: "rest_just_created" })
      )
    );

    await createRestaurant({ name: "New Place" });
    expect(getRestaurantId()).toBe("rest_just_created");
  });

  it("getCalls passes search params through", async () => {
    let observedQuery: string | undefined;
    server.use(
      http.get("*/api/restaurants/:id/calls", ({ request }) => {
        observedQuery = new URL(request.url).search;
        return HttpResponse.json({ calls: [], total: 0, pages: 1 });
      })
    );

    await getCalls(null, { page: 2, limit: 25, status: "COMPLETED" });
    expect(observedQuery).toContain("page=2");
    expect(observedQuery).toContain("limit=25");
    expect(observedQuery).toContain("status=COMPLETED");
  });

  it("getCall by id hits /calls/:id (not nested under restaurants)", async () => {
    let observedPath: string | undefined;
    server.use(
      http.get("*/api/calls/:cid", ({ params, request }) => {
        observedPath = new URL(request.url).pathname;
        return HttpResponse.json({ id: params.cid });
      })
    );

    await getCall("call_abc");
    expect(observedPath).toBe("/api/calls/call_abc");
  });

  it("rejects when the backend returns 401", async () => {
    server.use(
      http.get("*/api/restaurants/:id", () => new HttpResponse(null, { status: 401 }))
    );

    await expect(getRestaurant()).rejects.toMatchObject({
      response: { status: 401 },
    });
  });

  it("rejects when the backend returns 500", async () => {
    server.use(
      http.get("*/api/restaurants/:id/analytics/summary", () =>
        new HttpResponse(null, { status: 500 })
      )
    );

    await expect(getAnalyticsSummary()).rejects.toMatchObject({
      response: { status: 500 },
    });
  });
});

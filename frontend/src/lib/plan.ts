/**
 * Plan-tier helpers. The canonical stored plan casing is UPPERCASE
 * ("STARTER" / "PRO"), matching PLAN_CONFIG on the backend. These helpers are
 * case-insensitive so a stray "pro"/"Pro" can never silently demote a paying
 * customer to Starter features.
 */
export function isProPlan(plan?: string | null): boolean {
  return (plan ?? "").toUpperCase() === "PRO";
}

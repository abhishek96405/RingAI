import axios from "axios";

/**
 * Extracts a human-readable message from an unknown thrown value.
 * Preference order:
 *   1. Axios error with our FastAPI `detail` string
 *   2. Axios error's own message
 *   3. A native Error's message
 *   4. A plain thrown string
 *   5. The provided fallback
 */
export function getApiErrorMessage(err: unknown, fallback: string): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail;
    if (typeof detail === "string" && detail.trim()) {
      return detail;
    }
    if (err.message) {
      return err.message;
    }
  }
  if (err instanceof Error && err.message) {
    return err.message;
  }
  if (typeof err === "string" && err.trim()) {
    return err;
  }
  return fallback;
}

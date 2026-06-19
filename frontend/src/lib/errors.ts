import axios from "axios";

/**
 * Extracts a human-readable message from an unknown thrown value.
 *
 * For Axios errors we use our FastAPI `detail` string when present, otherwise the
 * caller's fallback — we deliberately do NOT surface raw transport messages like
 * "Request failed with status code 500" to end users. Non-axios throws use a
 * native Error message or a thrown string before falling back.
 */
export function getApiErrorMessage(err: unknown, fallback: string): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail;
    return typeof detail === "string" && detail.trim() ? detail : fallback;
  }
  if (err instanceof Error && err.message) {
    return err.message;
  }
  if (typeof err === "string" && err.trim()) {
    return err;
  }
  return fallback;
}

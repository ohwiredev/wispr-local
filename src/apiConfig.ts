const raw = import.meta.env.VITE_WISPR_API_URL;

/** Base URL for the Wispr Python API (no trailing slash). */
export const WISPR_API_URL =
  typeof raw === "string" && raw.length > 0
    ? raw.replace(/\/$/, "")
    : "http://127.0.0.1:8001";

/** Port string for UI copy, e.g. dashboard offline banner. */
export function wisprApiPortLabel(): string {
  try {
    const port = new URL(WISPR_API_URL).port;
    return port || "8001";
  } catch {
    return "8001";
  }
}

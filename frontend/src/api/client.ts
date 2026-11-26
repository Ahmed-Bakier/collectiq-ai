// Minimal typed API client. All requests go to the CollectIQ backend (/api),
// never directly to PayPal or the AI provider.

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly paypalDebugId: string | null;

  constructor(status: number, code: string, message: string, paypalDebugId: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.paypalDebugId = paypalDebugId;
  }
}

interface ErrorBody {
  error?: { code?: string; message?: string; paypal_debug_id?: string | null };
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new ApiError(0, "network_error", "Cannot reach the CollectIQ server. Is the backend running?");
  }

  if (!response.ok) {
    let body: ErrorBody = {};
    try {
      body = (await response.json()) as ErrorBody;
    } catch {
      // Non-JSON error body: fall back to a generic message.
    }
    throw new ApiError(
      response.status,
      body.error?.code ?? "http_error",
      body.error?.message ?? `Request failed (HTTP ${response.status}).`,
      body.error?.paypal_debug_id ?? null,
    );
  }

  return (await response.json()) as T;
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Unexpected error.";
}

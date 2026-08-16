export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;
  readonly details: Record<string, unknown>;

  constructor(options: {
    status: number;
    code: string;
    message: string;
    requestId?: string | null;
    details?: Record<string, unknown>;
  }) {
    super(options.message);
    this.name = "ApiError";
    this.status = options.status;
    this.code = options.code;
    this.requestId = options.requestId ?? null;
    this.details = options.details ?? {};
  }
}

export async function apiRequest<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
    });
  } catch (error) {
    throw new ApiError({
      status: 0,
      code: "network_error",
      message: "无法连接后端服务，请确认服务正在运行后重试。",
      details: error instanceof Error ? { cause: error.name } : {},
    });
  }

  if (!response.ok) {
    const detail = await response.text();
    throw parseApiError(detail, response.status);
  }

  return (await response.json()) as T;
}

function parseApiError(detail: string, status: number): ApiError {
  if (!detail) {
    return new ApiError({
      status,
      code: "request_failed",
      message: `接口请求失败：${status}`,
    });
  }
  try {
    const parsed = JSON.parse(detail) as unknown;
    if (isObject(parsed)) {
      const error = parsed.error;
      if (isObject(error) && typeof error.message === "string") {
        return structuredApiError(error, status);
      }
      if (typeof parsed.detail === "string") {
        return new ApiError({
          status,
          code: "request_failed",
          message: parsed.detail,
        });
      }
      if (isObject(parsed.detail)) {
        const nestedError = parsed.detail.error;
        if (isObject(nestedError) && typeof nestedError.message === "string") {
          return structuredApiError(nestedError, status);
        }
        if (typeof parsed.detail.message === "string") {
          return structuredApiError(parsed.detail, status);
        }
      }
    }
  } catch {
    return new ApiError({
      status,
      code: "request_failed",
      message: detail,
    });
  }
  return new ApiError({
    status,
    code: "request_failed",
    message: detail,
  });
}

function structuredApiError(
  detail: Record<string, unknown>,
  status: number,
): ApiError {
  const code =
    typeof detail.code === "string"
      ? detail.code
      : typeof detail.error === "string"
        ? detail.error
        : "request_failed";
  const requestId =
    typeof detail.request_id === "string" ? detail.request_id : null;
  const explicitDetails = isObject(detail.details) ? detail.details : {};
  const supplemental = Object.fromEntries(
    Object.entries(detail).filter(
      ([key]) =>
        !["code", "error", "message", "request_id", "details"].includes(key),
    ),
  );
  return new ApiError({
    status,
    code,
    message:
      typeof detail.message === "string"
        ? detail.message
        : `接口请求失败：${status}`,
    requestId,
    details: { ...supplemental, ...explicitDetails },
  });
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

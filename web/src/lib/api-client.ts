const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export async function apiRequest<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(errorMessage(detail, response.status));
  }

  return (await response.json()) as T;
}

function errorMessage(detail: string, status: number): string {
  if (!detail) {
    return `接口请求失败：${status}`;
  }
  try {
    const parsed = JSON.parse(detail) as unknown;
    if (isObject(parsed)) {
      const error = parsed.error;
      if (isObject(error) && typeof error.message === "string") {
        return error.message;
      }
      if (typeof parsed.detail === "string") {
        return parsed.detail;
      }
      if (isObject(parsed.detail)) {
        const nestedError = parsed.detail.error;
        if (
          isObject(nestedError) &&
          typeof nestedError.message === "string"
        ) {
          return nestedError.message;
        }
      }
    }
  } catch {
    return detail;
  }
  return detail;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

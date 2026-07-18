export function resolveAppShellEscapeDestination(
  pathname: string,
  escapeToHome?: boolean,
): string | null {
  if (escapeToHome === false) return null;
  if (pathname.startsWith("/task-monitor/")) return "/task-monitor";
  if (escapeToHome === true) return "/home";
  return pathname === "/home" ? null : "/home";
}

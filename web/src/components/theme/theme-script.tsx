import {
  DEFAULT_THEME_STYLE,
  THEME_STORAGE_KEY,
  themeStyles,
} from "./theme-registry";

export function ThemeScript() {
  const allowedThemes = JSON.stringify(themeStyles.map(theme => theme.id));

  const script = `
(() => {
  try {
    const allowedThemes = ${allowedThemes};
    const storedTheme = window.localStorage.getItem("${THEME_STORAGE_KEY}");
    const themeStyle = allowedThemes.includes(storedTheme)
      ? storedTheme
      : "${DEFAULT_THEME_STYLE}";
    document.documentElement.dataset.themeStyle = themeStyle;
  } catch (_) {
    document.documentElement.dataset.themeStyle = "${DEFAULT_THEME_STYLE}";
  }
})();
`;

  return (
    <script
      suppressHydrationWarning
      dangerouslySetInnerHTML={{ __html: script }}
    />
  );
}

export const THEME_STORAGE_KEY = "taichu-theme-style";

export const DEFAULT_THEME_STYLE = "langbase-midnight-console";

export const themeStyles = [
  {
    id: "langbase-midnight-console",
    label: "午夜极光控制台风格",
    shortLabel: "极光",
    description: "炭灰控制台、白色胶囊按钮、极光装饰条",
  },
  {
    id: "graphite-chalk-swiss",
    label: "石墨网格风格",
    shortLabel: "石墨",
    description: "黑白灰、发丝线、紧凑瑞士网格",
  },
] as const;

export type ThemeStyle = (typeof themeStyles)[number]["id"];

export function isThemeStyle(value: string | null): value is ThemeStyle {
  return themeStyles.some(theme => theme.id === value);
}

export function getThemeStyle(value: ThemeStyle) {
  return themeStyles.find(theme => theme.id === value) ?? themeStyles[0];
}

export function getNextThemeStyle(value: ThemeStyle): ThemeStyle {
  const currentIndex = themeStyles.findIndex(theme => theme.id === value);
  const nextIndex = currentIndex < 0 ? 0 : (currentIndex + 1) % themeStyles.length;
  return themeStyles[nextIndex].id;
}

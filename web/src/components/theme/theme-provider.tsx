"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  DEFAULT_THEME_STYLE,
  THEME_STORAGE_KEY,
  getNextThemeStyle,
  getThemeStyle,
  isThemeStyle,
  type ThemeStyle,
} from "./theme-registry";

type ThemeContextValue = {
  themeStyle: ThemeStyle;
  currentTheme: ReturnType<typeof getThemeStyle>;
  nextTheme: ReturnType<typeof getThemeStyle>;
  setThemeStyle: (themeStyle: ThemeStyle) => void;
  toggleThemeStyle: () => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

function getInitialThemeStyle(): ThemeStyle {
  if (typeof document !== "undefined") {
    const datasetTheme = document.documentElement.dataset.themeStyle ?? null;
    if (isThemeStyle(datasetTheme)) {
      return datasetTheme;
    }
  }

  if (typeof window !== "undefined") {
    const storedTheme = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (isThemeStyle(storedTheme)) {
      return storedTheme;
    }
  }

  return DEFAULT_THEME_STYLE;
}

function applyThemeStyle(themeStyle: ThemeStyle) {
  document.documentElement.dataset.themeStyle = themeStyle;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [themeStyle, setThemeStyleState] =
    useState<ThemeStyle>(getInitialThemeStyle);

  useEffect(() => {
    applyThemeStyle(themeStyle);
    window.localStorage.setItem(THEME_STORAGE_KEY, themeStyle);
  }, [themeStyle]);

  const setThemeStyle = useCallback((nextThemeStyle: ThemeStyle) => {
    setThemeStyleState(nextThemeStyle);
  }, []);

  const toggleThemeStyle = useCallback(() => {
    setThemeStyle(getNextThemeStyle(themeStyle));
  }, [setThemeStyle, themeStyle]);

  const value = useMemo<ThemeContextValue>(() => {
    const nextThemeStyle = getNextThemeStyle(themeStyle);

    return {
      themeStyle,
      currentTheme: getThemeStyle(themeStyle),
      nextTheme: getThemeStyle(nextThemeStyle),
      setThemeStyle,
      toggleThemeStyle,
    };
  }, [setThemeStyle, themeStyle, toggleThemeStyle]);

  return (
    <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
  );
}

export function useThemeStyle() {
  const value = useContext(ThemeContext);

  if (!value) {
    throw new Error("useThemeStyle must be used inside ThemeProvider");
  }

  return value;
}

"use client";

import { useEffect, useState } from "react";
import { Loader2, Save, Settings } from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { patchPreferences, readPreferences } from "@/lib/api/mvp";
import type { EditorPreferences } from "@/lib/types/mvp";

const defaultPreferences: EditorPreferences = {
  font_size: 18,
  font_style: "serif",
  editor_background: "soft",
  updated_at: "",
};

export default function SettingsPage() {
  const [preferences, setPreferences] =
    useState<EditorPreferences>(defaultPreferences);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    readPreferences()
      .then(response => {
        if (!cancelled) {
          setPreferences(response.preferences);
        }
      })
      .catch(caught => {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "设置加载失败");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function savePreferences() {
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const response = await patchPreferences(preferences);
      setPreferences(response.preferences);
      setMessage("偏好已保存");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "设置保存失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <AppShell activePath="/settings">
      <section className="mx-auto max-w-4xl px-5 py-8">
        <div className="mb-6">
          <p className="mb-2 flex items-center gap-2 text-sm text-[var(--tc-deep-forest-teal)]">
            <Settings className="size-4" />
            设置
          </p>
          <h1 className="font-serif text-4xl text-[var(--tc-midnight-ink)]">
            基础偏好
          </h1>
        </div>

        <div className="rounded-[var(--tc-radius-card)] border border-[var(--tc-stone-mist)] bg-[var(--tc-white)] p-6">
          {loading ? (
            <div className="flex h-40 items-center justify-center text-sm text-[var(--tc-smoke)]">
              <Loader2 className="mr-2 size-4 animate-spin" />
              加载中
            </div>
          ) : (
            <div className="grid gap-5 md:grid-cols-2">
              <label className="block text-sm font-medium">
                字体大小
                <input
                  type="range"
                  min={14}
                  max={24}
                  value={preferences.font_size}
                  onChange={event =>
                    setPreferences(current => ({
                      ...current,
                      font_size: Number(event.target.value),
                    }))
                  }
                  className="mt-3 w-full accent-[var(--tc-deep-forest-teal)]"
                />
                <span className="mt-2 block text-sm text-[var(--tc-smoke)]">
                  {preferences.font_size} 像素
                </span>
              </label>

              <label className="block text-sm font-medium">
                字体样式
                <select
                  value={preferences.font_style}
                  onChange={event =>
                    setPreferences(current => ({
                      ...current,
                      font_style: event.target.value as EditorPreferences["font_style"],
                    }))
                  }
                  className="mt-3 h-10 w-full rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] px-3"
                >
                  <option value="serif">衬线</option>
                  <option value="sans">无衬线</option>
                </select>
              </label>

              <label className="block text-sm font-medium">
                编辑背景
                <select
                  value={preferences.editor_background}
                  onChange={event =>
                    setPreferences(current => ({
                      ...current,
                      editor_background:
                        event.target.value as EditorPreferences["editor_background"],
                    }))
                  }
                  className="mt-3 h-10 w-full rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] px-3"
                >
                  <option value="soft">柔和纸面</option>
                  <option value="dark">墨色边框</option>
                </select>
              </label>

              <div className="rounded-[var(--tc-radius-control)] border border-[var(--tc-stone-mist)] bg-[var(--tc-cream-paper)] p-4 text-sm leading-6 text-[var(--tc-smoke)]">
                基础显示偏好会影响写作区的正文输入体验。
              </div>
            </div>
          )}

          {error ? (
            <p className="tc-warning mt-4 rounded-[var(--tc-radius-control)] border px-3 py-2 text-sm">
              {error}
            </p>
          ) : null}
          {message ? (
            <p className="tc-success mt-4 rounded-[var(--tc-radius-control)] border px-3 py-2 text-sm">
              {message}
            </p>
          ) : null}

          <Button
            type="button"
            onClick={savePreferences}
            disabled={loading || saving}
            className="mt-6"
          >
            {saving ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
            保存
          </Button>
        </div>
      </section>
    </AppShell>
  );
}

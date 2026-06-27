"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { TaichuPointCloudScene } from "./point-cloud-scene";
import type { EntryState } from "./types";
import { useReducedMotion } from "./use-reduced-motion";

const stateText: Record<EntryState, string> = {
  idle: "观测中",
  entering: "穿行中",
  "dense-transition": "穿越位面夹层",
  focus: "锁定世界种子",
  completed: "进入太初",
};

export default function TaichuEntry() {
  const router = useRouter();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const sceneRef = useRef<TaichuPointCloudScene | null>(null);
  const reducedMotion = useReducedMotion();
  const [entryState, setEntryState] = useState<EntryState>("idle");
  const [renderError, setRenderError] = useState<string | null>(null);

  const enterHome = useCallback(() => {
    router.push("/home");
  }, [router]);

  const startEntry = useCallback(() => {
    if (entryState !== "idle") {
      return;
    }
    if (!sceneRef.current) {
      enterHome();
      return;
    }
    sceneRef.current.enter();
  }, [enterHome, entryState]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }

    try {
      const scene = new TaichuPointCloudScene({
        container,
        reducedMotion,
        onEnter: enterHome,
        onStateChange: setEntryState,
      });
      sceneRef.current = scene;
      return () => {
        scene.dispose();
        sceneRef.current = null;
      };
    } catch (caught) {
      const message =
        caught instanceof Error
          ? caught.message
          : "图形渲染不可用，仍可进入太初";
      const timer = window.setTimeout(() => setRenderError(message), 0);
      sceneRef.current = null;
      return () => window.clearTimeout(timer);
    }
  }, [enterHome, reducedMotion]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "Enter" && event.key !== " ") {
        return;
      }
      const target = event.target as HTMLElement | null;
      if (target?.tagName === "BUTTON") {
        return;
      }
      event.preventDefault();
      startEntry();
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [startEntry]);

  return (
    <main className="relative min-h-screen overflow-hidden bg-[#100b12] text-[#f4efe5]">
      <div
        ref={containerRef}
        className="absolute inset-0"
        aria-hidden="true"
      />

      <div className="pointer-events-none absolute inset-0 z-10 bg-[radial-gradient(circle_at_50%_52%,rgba(0,0,0,0)_0%,rgba(0,0,0,0)_58%,rgba(0,0,0,0.22)_100%)] shadow-[inset_0_0_96px_rgba(0,0,0,0.46)]" />

      <button
        type="button"
        onClick={startEntry}
        disabled={entryState !== "idle"}
        aria-label="进入太初"
        aria-busy={entryState !== "idle"}
        className="absolute left-1/2 top-8 z-20 flex h-14 w-[218px] -translate-x-1/2 flex-col items-center justify-center border border-[#f4efe5]/72 bg-[#100b12]/18 text-[#f7f3ea] outline-none backdrop-blur-[1px] transition-[border-color,background-color,opacity,transform] duration-200 hover:border-white hover:bg-white/[0.032] focus-visible:ring-2 focus-visible:ring-[#f4efe5]/70 disabled:cursor-default disabled:opacity-70"
      >
        <span className="font-mono text-[17px] tracking-[0.34em]">TAICHU</span>
        <span className="mt-1 text-[11px] tracking-[0.18em] text-[#c4beb2]">
          {entryState === "idle" ? "进入太初" : stateText[entryState]}
        </span>
      </button>

      <div className="pointer-events-none absolute left-6 top-6 z-20 hidden max-w-[220px] space-y-2 text-[11px] text-[#a6a196] md:block">
        <Readout label="坐标" value="太初虚空" />
        <Readout label="阶段" value={stateText[entryState]} />
      </div>

      <div className="pointer-events-none absolute bottom-6 right-6 z-20 hidden max-w-[260px] space-y-2 text-[11px] text-[#a6a196] md:block">
        <Readout label="世界种子" value="已点亮" active />
        <Readout label="观测场" value="点云稳定" />
      </div>

      {renderError ? (
        <div className="absolute bottom-6 left-6 z-30 max-w-sm border border-[#f4efe5]/30 bg-black/70 px-3 py-2 text-xs text-[#f4efe5]">
          {renderError}
        </div>
      ) : null}
    </main>
  );
}

function Readout({
  label,
  value,
  active = false,
}: {
  label: string;
  value: string;
  active?: boolean;
}) {
  return (
    <div className="flex items-center gap-2 font-mono">
      <span
        className={
          active
            ? "size-1.5 rounded-full bg-[#ebfb10] shadow-[0_0_12px_rgba(235,251,16,0.38)]"
            : "h-px w-4 bg-[#6f6f6f]"
        }
      />
      <span>{label}：</span>
      <span className="text-[#f4efe5]/80">{value}</span>
    </div>
  );
}

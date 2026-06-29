"use client";

import {
  forwardRef,
  useCallback,
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { useRouter } from "next/navigation";

import { TaichuPointCloudScene } from "./point-cloud-scene";
import { taichuEntrySceneConfig } from "./point-cloud-scene-config";
import type { EntryState, PointCloudAssetStatus } from "./types";
import { useReducedMotion } from "./use-reduced-motion";

const stateText: Record<EntryState, string> = {
  idle: "观测中",
  entering: "穿行中",
  "dense-transition": "穿越位面夹层",
  focus: "锁定太初之种",
  completed: "进入太初",
};

export default function TaichuEntry() {
  const router = useRouter();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const sceneRef = useRef<TaichuPointCloudScene | null>(null);
  const cursorRef = useRef<HTMLDivElement | null>(null);
  const reducedMotion = useReducedMotion();
  const [entryState, setEntryState] = useState<EntryState>("idle");
  const [assetStatus, setAssetStatus] =
    useState<PointCloudAssetStatus>("loading");
  const [renderError, setRenderError] = useState<string | null>(null);
  const [cursorVisible, setCursorVisible] = useState(false);
  const [cursorActive, setCursorActive] = useState(false);

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
        config: taichuEntrySceneConfig,
        onEnter: enterHome,
        onStateChange: setEntryState,
        onAssetStatusChange: status => {
          setAssetStatus(status);
          if (status === "loaded") {
            setRenderError(null);
          }
        },
        onRenderError: setRenderError,
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

  const moveCursor = useCallback((event: ReactPointerEvent<HTMLElement>) => {
    const cursorElement = cursorRef.current;
    if (!cursorElement) {
      return;
    }

    cursorElement.style.transform = `translate3d(${event.clientX}px, ${event.clientY}px, 0) translate(-50%, -50%)`;
  }, []);

  const onPointerMove = useCallback(
    (event: ReactPointerEvent<HTMLElement>) => {
      moveCursor(event);
      setCursorVisible(true);
    },
    [moveCursor],
  );

  const onPointerDown = useCallback(
    (event: ReactPointerEvent<HTMLElement>) => {
      moveCursor(event);
      setCursorVisible(true);
      setCursorActive(true);
    },
    [moveCursor],
  );

  const onPointerUp = useCallback(
    (event: ReactPointerEvent<HTMLElement>) => {
      moveCursor(event);
      setCursorActive(false);
    },
    [moveCursor],
  );

  const hideCursor = useCallback(() => {
    setCursorVisible(false);
    setCursorActive(false);
  }, []);

  return (
    <main
      className="relative min-h-screen cursor-none overflow-hidden bg-black text-[#f4efe5]"
      onPointerMove={onPointerMove}
      onPointerDown={onPointerDown}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onPointerLeave={hideCursor}
    >
      <div
        ref={containerRef}
        className="absolute inset-0 cursor-none"
        aria-hidden="true"
      />

      <div className="pointer-events-none absolute inset-0 z-10 bg-[radial-gradient(circle_at_50%_52%,rgba(0,0,0,0)_0%,rgba(0,0,0,0)_58%,rgba(0,0,0,0.22)_100%)] shadow-[inset_0_0_96px_rgba(0,0,0,0.46)]" />

      <button
        type="button"
        onClick={startEntry}
        disabled={entryState !== "idle"}
        aria-label="进入太初"
        aria-busy={entryState !== "idle"}
        className="absolute left-1/2 top-8 z-20 flex h-14 w-[218px] -translate-x-1/2 cursor-none flex-col items-center justify-center border border-[#f4efe5]/72 bg-black/18 text-[#f7f3ea] outline-none backdrop-blur-[1px] transition-[border-color,background-color,opacity,transform] duration-200 hover:border-white hover:bg-white/[0.032] focus-visible:ring-2 focus-visible:ring-[#f4efe5]/70 disabled:cursor-none disabled:opacity-70"
      >
        <span className="font-mono text-[17px] tracking-[0.34em]">TAICHU</span>
        <span className="mt-1 text-[11px] tracking-[0.18em] text-[#c4beb2]">
          {entryState === "idle" ? "进入太初" : stateText[entryState]}
        </span>
      </button>

      <div className="pointer-events-none absolute left-6 top-6 z-20 hidden max-w-[260px] space-y-2 text-[11px] text-[#a6a196] md:block">
        <Readout label="观测" value="太极虚空" />
        <Readout label="阶段" value={stateText[entryState]} />
      </div>

      <div className="pointer-events-none absolute bottom-6 right-6 z-20 hidden max-w-[260px] space-y-2 text-[11px] text-[#a6a196] md:block">
        <Readout label="太初之种" value="已追踪" active />
        <Readout
          label="虚空经纬"
          value="观测中"
          active={assetStatus === "loaded"}
        />
      </div>

      <ObservationCursor
        ref={cursorRef}
        active={cursorActive}
        visible={cursorVisible}
      />

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
            ? "size-1.5 rounded-full bg-[#dce8f6] shadow-[0_0_12px_rgba(190,212,251,0.34)]"
            : "h-px w-4 bg-[#6f6f6f]"
        }
      />
      <span>{label}：</span>
      <span className="text-[#f4efe5]/80">{value}</span>
    </div>
  );
}

const ObservationCursor = forwardRef<
  HTMLDivElement,
  { active: boolean; visible: boolean }
>(function ObservationCursor({ active, visible }, ref) {
  const size = active ? 34 : 24;

  return (
    <div
      ref={ref}
      data-testid="taichu-observation-cursor"
      className="pointer-events-none fixed left-0 top-0 z-50 hidden -translate-x-1/2 -translate-y-1/2 md:block"
      style={{
        width: size,
        height: size,
        opacity: visible ? 1 : 0,
        transform: "translate3d(0, 0, 0) translate(-50%, -50%)",
        transition:
          "width 140ms ease, height 140ms ease, opacity 120ms ease, border-color 140ms ease",
      }}
      aria-hidden="true"
    >
      <span
        className={
          active
            ? "absolute inset-0 rounded-full border border-[#dce8f6]/58 shadow-[0_0_18px_rgba(190,212,251,0.24)]"
            : "absolute inset-[5px] rounded-full border border-[#f4efe5]/48"
        }
      />
      <span
        className={
          active
            ? "absolute inset-[7px] rounded-full border border-[#f4efe5]/24"
            : "absolute left-1/2 top-1/2 size-1 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[#f4efe5]/72"
        }
      />
      <span className="absolute left-1/2 top-0 h-[7px] w-px -translate-x-1/2 bg-[#f4efe5]/52" />
      <span className="absolute bottom-0 left-1/2 h-[7px] w-px -translate-x-1/2 bg-[#f4efe5]/52" />
      <span className="absolute left-0 top-1/2 h-px w-[7px] -translate-y-1/2 bg-[#f4efe5]/52" />
      <span className="absolute right-0 top-1/2 h-px w-[7px] -translate-y-1/2 bg-[#f4efe5]/52" />
      <span
        className={
          active
            ? "absolute left-1/2 top-1/2 size-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[#dce8f6] shadow-[0_0_12px_rgba(190,212,251,0.42)]"
            : "hidden"
        }
      />
    </div>
  );
});

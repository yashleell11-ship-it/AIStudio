"use client";

import { useEffect, useRef } from "react";
import { Minus, Plus } from "lucide-react";
import {
  NOVEL_PALETTES,
  SITE_PALETTE,
  type NovelPaletteChoice,
  type NovelSurface,
  type PaletteScheme,
} from "../palettes";
import {
  MAX_FONT_SIZE,
  MAX_LINE_HEIGHT,
  MAX_MEASURE,
  MIN_FONT_SIZE,
  MIN_LINE_HEIGHT,
  MIN_MEASURE,
  novelFontStack,
  type NovelFontFamily,
} from "../typography";
import type { NovelPreferences } from "../preferences";

interface NovelTypePanelProps {
  surface: NovelSurface;
  preferences: NovelPreferences;
  onChange: (patch: Partial<NovelPreferences>) => void;
  choice: NovelPaletteChoice;
  onChoosePalette: (choice: NovelPaletteChoice) => void;
  siteScheme: PaletteScheme;
  onClose: () => void;
}

/**
 * Type and page settings, painted in the reader's own palette.
 *
 * Not a glass panel and not the app's chrome: a settings sheet in Eclipse Warm
 * dropped onto a Paper page is a hole punched in the book. It borrows the
 * surface it sits on and separates itself with a hairline and a shadow, which
 * is all the separation a single panel needs.
 */
export function NovelTypePanel({
  surface,
  preferences,
  onChange,
  choice,
  onChoosePalette,
  siteScheme,
  onClose,
}: NovelTypePanelProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  // Escape and an outside click both close it. Escape is captured here rather
  // than left to the reader's own binding so it dismisses the panel before it
  // would leave the chapter.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.stopPropagation();
      onClose();
    };
    const onPointerDown = (event: PointerEvent) => {
      if (!panelRef.current || panelRef.current.contains(event.target as Node)) return;
      onClose();
    };
    document.addEventListener("keydown", onKeyDown, true);
    document.addEventListener("pointerdown", onPointerDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown, true);
      document.removeEventListener("pointerdown", onPointerDown);
    };
  }, [onClose]);

  const lightPalettes = NOVEL_PALETTES.filter((palette) => palette.scheme === "light");
  const darkPalettes = NOVEL_PALETTES.filter((palette) => palette.scheme === "dark");

  return (
    <div
      ref={panelRef}
      role="dialog"
      aria-label="Type and page settings"
      className="absolute right-0 top-full z-50 mt-2 w-[min(22rem,calc(100vw-2rem))] rounded-xl p-4 shadow-[0_18px_50px_rgba(0,0,0,0.28)]"
      style={{
        backgroundColor: surface.bg,
        color: surface.ink,
        border: `1px solid ${surface.rule}`,
      }}
    >
      <Stepper
        label="Text size"
        value={`${preferences.fontSize} px`}
        surface={surface}
        onDecrease={() => onChange({ fontSize: preferences.fontSize - 1 })}
        onIncrease={() => onChange({ fontSize: preferences.fontSize + 1 })}
        atMin={preferences.fontSize <= MIN_FONT_SIZE}
        atMax={preferences.fontSize >= MAX_FONT_SIZE}
      />
      <Stepper
        label="Line spacing"
        value={preferences.lineHeight.toFixed(2)}
        surface={surface}
        onDecrease={() => onChange({ lineHeight: preferences.lineHeight - 0.05 })}
        onIncrease={() => onChange({ lineHeight: preferences.lineHeight + 0.05 })}
        atMin={preferences.lineHeight <= MIN_LINE_HEIGHT}
        atMax={preferences.lineHeight >= MAX_LINE_HEIGHT}
      />
      <Stepper
        label="Line width"
        value={`${preferences.measure} ch`}
        surface={surface}
        onDecrease={() => onChange({ measure: preferences.measure - 2 })}
        onIncrease={() => onChange({ measure: preferences.measure + 2 })}
        atMin={preferences.measure <= MIN_MEASURE}
        atMax={preferences.measure >= MAX_MEASURE}
      />

      <Divider surface={surface} />

      <Legend surface={surface}>Typeface</Legend>
      <div className="mt-2 grid grid-cols-2 gap-2">
        {(["serif", "sans"] as const).map((family) => (
          <FaceButton
            key={family}
            family={family}
            active={preferences.fontFamily === family}
            surface={surface}
            onSelect={() => onChange({ fontFamily: family })}
          />
        ))}
      </div>

      <Divider surface={surface} />

      <Legend surface={surface}>Page</Legend>
      <div className="mt-2 space-y-2">
        <button
          type="button"
          aria-pressed={choice === SITE_PALETTE}
          onClick={() => onChoosePalette(SITE_PALETTE)}
          className="flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm transition-opacity hover:opacity-80"
          style={{
            border: `1px solid ${choice === SITE_PALETTE ? surface.ink : surface.rule}`,
            color: surface.ink,
          }}
        >
          <span>Follow site theme</span>
          <span className="text-xs" style={{ color: surface.muted }}>
            {siteScheme === "light" ? "light" : "dark"}
          </span>
        </button>

        <PaletteRow
          label="Light"
          palettes={lightPalettes}
          choice={choice}
          surface={surface}
          onChoose={onChoosePalette}
        />
        <PaletteRow
          label="Dark"
          palettes={darkPalettes}
          choice={choice}
          surface={surface}
          onChoose={onChoosePalette}
        />
      </div>
    </div>
  );
}

function Divider({ surface }: { surface: NovelSurface }) {
  return <div className="my-4 h-px" style={{ backgroundColor: surface.rule }} />;
}

function Legend({
  surface,
  children,
}: {
  surface: NovelSurface;
  children: React.ReactNode;
}) {
  return (
    <p
      className="text-[0.6875rem] font-semibold uppercase tracking-[0.18em]"
      style={{ color: surface.muted }}
    >
      {children}
    </p>
  );
}

function Stepper({
  label,
  value,
  surface,
  onDecrease,
  onIncrease,
  atMin,
  atMax,
}: {
  label: string;
  value: string;
  surface: NovelSurface;
  onDecrease: () => void;
  onIncrease: () => void;
  atMin: boolean;
  atMax: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-3 py-1.5">
      <span className="text-sm" style={{ color: surface.ink }}>
        {label}
      </span>
      <div className="flex items-center gap-2">
        <StepButton
          surface={surface}
          disabled={atMin}
          onClick={onDecrease}
          label={`Decrease ${label.toLowerCase()}`}
        >
          <Minus className="size-4" aria-hidden />
        </StepButton>
        <span
          className="min-w-[4.25rem] text-center text-xs tabular-nums"
          style={{ color: surface.muted }}
        >
          {value}
        </span>
        <StepButton
          surface={surface}
          disabled={atMax}
          onClick={onIncrease}
          label={`Increase ${label.toLowerCase()}`}
        >
          <Plus className="size-4" aria-hidden />
        </StepButton>
      </div>
    </div>
  );
}

function StepButton({
  surface,
  disabled,
  onClick,
  label,
  children,
}: {
  surface: NovelSurface;
  disabled: boolean;
  onClick: () => void;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className="flex size-8 items-center justify-center rounded-lg transition-opacity hover:opacity-70 disabled:opacity-30"
      style={{ border: `1px solid ${surface.rule}`, color: surface.ink }}
    >
      {children}
    </button>
  );
}

function FaceButton({
  family,
  active,
  surface,
  onSelect,
}: {
  family: NovelFontFamily;
  active: boolean;
  surface: NovelSurface;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onSelect}
      className="rounded-lg px-3 py-2 text-base transition-opacity hover:opacity-80"
      style={{
        fontFamily: novelFontStack(family),
        border: `1px solid ${active ? surface.ink : surface.rule}`,
        color: surface.ink,
      }}
    >
      {family === "serif" ? "Serif" : "Sans"}
    </button>
  );
}

function PaletteRow({
  label,
  palettes,
  choice,
  surface,
  onChoose,
}: {
  label: string;
  palettes: readonly (typeof NOVEL_PALETTES)[number][];
  choice: NovelPaletteChoice;
  surface: NovelSurface;
  onChoose: (choice: NovelPaletteChoice) => void;
}) {
  return (
    <div>
      <p className="mb-1.5 text-[0.6875rem]" style={{ color: surface.muted }}>
        {label}
      </p>
      <div className="flex flex-wrap gap-2">
        {palettes.map((palette) => {
          const active = choice === palette.id;
          return (
            <button
              key={palette.id}
              type="button"
              title={palette.label}
              aria-label={palette.label}
              aria-pressed={active}
              onClick={() => onChoose(palette.id)}
              className="flex size-9 items-center justify-center rounded-lg text-sm transition-transform hover:scale-105"
              style={{
                backgroundColor: palette.bg,
                color: palette.ink,
                // The tick is the ring, drawn in the reader's own ink so it
                // reads on any of the twelve surfaces.
                boxShadow: active
                  ? `0 0 0 2px ${surface.bg}, 0 0 0 3.5px ${surface.ink}`
                  : `inset 0 0 0 1px ${palette.muted}`,
              }}
            >
              Aa
            </button>
          );
        })}
      </div>
    </div>
  );
}

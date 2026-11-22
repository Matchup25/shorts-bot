import React from "react";
import { Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { BODY, HEAD } from "../fonts";
import { clamp, YELLOW } from "../theme";

const format = (value: string, p: number) => {
  const raw = value.replace(/,/g, "").trim();
  const num = Number(raw);
  if (!Number.isFinite(num)) return value;
  const cur = num * p;
  // big numbers are shown compact so they fit the ring: 500,000 -> 500K, 1,200,000 -> 1.2M
  if (Math.abs(num) >= 1e9) return `${(cur / 1e9).toFixed(cur / 1e9 >= 10 || p < 1 ? 0 : 1)}B`;
  if (Math.abs(num) >= 1e6) return `${(cur / 1e6).toFixed(cur / 1e6 >= 10 || p < 1 ? 0 : 1)}M`;
  if (Math.abs(num) >= 1e4) return `${Math.round(cur / 1e3)}K`;
  const decimals = raw.includes(".") ? raw.split(".")[1].length : 0;
  return cur.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
};

/** Giant counting number with a glowing ring. */
export const Stat: React.FC<{ value: string; unit: string; top?: number }> = ({ value, unit, top = 470 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = interpolate(frame, [4, 1.1 * fps], [0, 1], { ...clamp, easing: Easing.out(Easing.cubic) });
  const appear = spring({ frame: frame - 2, fps, config: { damping: 14, stiffness: 140 } });
  const text = format(value, p);
  const size = text.length >= 6 ? 170 : text.length === 5 ? 200 : text.length === 4 ? 240 : 280;
  const R = 285;
  const C = 2 * Math.PI * R;

  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        top,
        height: 660,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        scale: interpolate(appear, [0, 1], [0.6, 1]),
        opacity: interpolate(appear, [0, 1], [0, 1]),
      }}
    >
      <svg width={660} height={660} style={{ position: "absolute", rotate: `${-90 + frame * 0.4}deg` }}>
        <circle cx={330} cy={330} r={R} stroke="rgba(255,255,255,0.14)" strokeWidth={6} fill="none" />
        <circle
          cx={330}
          cy={330}
          r={R}
          stroke={YELLOW}
          strokeWidth={10}
          strokeLinecap="round"
          fill="none"
          strokeDasharray={C}
          strokeDashoffset={C * (1 - p * 0.82)}
          style={{ filter: "drop-shadow(0 0 18px rgba(255,210,63,0.8))" }}
        />
      </svg>
      <div
        style={{
          fontFamily: HEAD,
          fontSize: size,
          lineHeight: 1,
          color: YELLOW,
          textShadow: "0 0 50px rgba(255,210,63,0.55), 0 12px 40px rgba(0,0,0,0.6)",
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {text}
      </div>
      <div
        style={{
          marginTop: 18,
          maxWidth: 470,
          textAlign: "center",
          fontFamily: BODY,
          fontWeight: 800,
          fontSize: 40,
          letterSpacing: 4,
          textTransform: "uppercase",
          color: "white",
          textShadow: "0 4px 20px rgba(0,0,0,0.8)",
          opacity: interpolate(frame, [10, 22], [0, 1], clamp),
          translate: `0px ${interpolate(frame, [10, 22], [20, 0], { ...clamp, easing: Easing.out(Easing.cubic) })}px`,
        }}
      >
        {unit}
      </div>
    </div>
  );
};

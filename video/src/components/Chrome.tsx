import React from "react";
import {
  AbsoluteFill,
  Easing,
  interpolate,
  random,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { BODY } from "../fonts";
import { CATEGORY_COLORS, clamp, RED, YELLOW } from "../theme";

/** Darkening gradients + vignette so text is always readable. */
export const Shade: React.FC = () => (
  <AbsoluteFill style={{ pointerEvents: "none" }}>
    <AbsoluteFill
      style={{ background: "linear-gradient(180deg, rgba(0,0,0,0.78) 0%, rgba(0,0,0,0.35) 22%, rgba(0,0,0,0) 38%)" }}
    />
    <AbsoluteFill
      style={{
        background:
          "linear-gradient(0deg, rgba(0,0,0,0.88) 0%, rgba(0,0,0,0.6) 25%, rgba(0,0,0,0.15) 48%, rgba(0,0,0,0) 60%)",
      }}
    />
    <AbsoluteFill
      style={{ background: "radial-gradient(ellipse 80% 65% at 50% 50%, rgba(0,0,0,0) 55%, rgba(0,0,0,0.55) 100%)" }}
    />
  </AbsoluteFill>
);

/** Moving film grain. */
export const Grain: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill
      style={{
        backgroundImage: `url(${staticFile("grain.png")})`,
        backgroundSize: "384px 384px",
        backgroundPosition: `${Math.floor(random(`gx${frame}`) * 384)}px ${Math.floor(random(`gy${frame}`) * 384)}px`,
        opacity: 0.075,
        mixBlendMode: "overlay",
      }}
    />
  );
};

/** Channel badge, category and image credit at the top. */
export const Brand: React.FC<{ channel: string; category: string }> = ({ channel, category }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const inP = interpolate(frame, [0, 14], [0, 1], { ...clamp, easing: Easing.out(Easing.cubic) });
  const color = CATEGORY_COLORS[category] ?? YELLOW;
  const pulse = 0.55 + 0.45 * Math.abs(Math.sin((frame / fps) * Math.PI));
  return (
    <div
      style={{
        position: "absolute",
        left: 80,
        top: 150,
        opacity: inP,
        translate: `${interpolate(inP, [0, 1], [-40, 0])}px 0px`,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 14,
            padding: "12px 24px 12px 20px",
            borderRadius: 999,
            backgroundColor: "rgba(10,10,14,0.55)",
            border: "1.5px solid rgba(255,255,255,0.18)",
          }}
        >
          <div
            style={{
              width: 16,
              height: 16,
              borderRadius: 8,
              backgroundColor: RED,
              opacity: pulse,
              boxShadow: `0 0 16px ${RED}`,
            }}
          />
          <span style={{ fontFamily: BODY, fontWeight: 800, fontSize: 28, letterSpacing: 3, color: "white" }}>
            {channel.toUpperCase()}
          </span>
        </div>
        <div
          style={{
            padding: "12px 20px",
            borderRadius: 999,
            backgroundColor: color,
            fontFamily: BODY,
            fontWeight: 800,
            fontSize: 24,
            letterSpacing: 3,
            color: "#0B0B10",
          }}
        >
          {category.toUpperCase()}
        </div>
      </div>
    </div>
  );
};

/** Small picture credit under the badge (fades with each scene). */
export const Credit: React.FC<{ text?: string }> = ({ text }) => {
  const frame = useCurrentFrame();
  if (!text) return null;
  return (
    <div
      style={{
        position: "absolute",
        left: 86,
        top: 232,
        fontFamily: BODY,
        fontWeight: 600,
        fontSize: 22,
        color: "rgba(255,255,255,0.72)",
        letterSpacing: 0.5,
        opacity: interpolate(frame, [4, 14], [0, 1], clamp),
        textShadow: "0 2px 8px rgba(0,0,0,0.8)",
      }}
    >
      {text}
    </div>
  );
};

/** Thin progress line at the very top. */
export const Progress: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        top: 0,
        height: 9,
        width: `${(frame / durationInFrames) * 100}%`,
        backgroundColor: YELLOW,
        boxShadow: "0 0 18px rgba(255,210,63,0.8)",
      }}
    />
  );
};

/** White flash right on a cut. */
export const Flash: React.FC<{ strength: number }> = ({ strength }) => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill
      style={{
        backgroundColor: "white",
        opacity: interpolate(frame, [0, 1, 7], [strength, strength, 0], clamp),
        mixBlendMode: "screen",
      }}
    />
  );
};

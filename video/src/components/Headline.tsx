import React from "react";
import { Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { HEAD } from "../fonts";
import { clamp, YELLOW } from "../theme";

/** Scene title: words rise out of a mask one after another, with a growing accent bar. */
export const Headline: React.FC<{ text: string; big: boolean; exitAt: number }> = ({ text, big, exitAt }) => {
  // the very first title is already on screen at frame 0 (it is often the thumbnail)
  const frame = useCurrentFrame() + (big ? 30 : 0);
  const { fps } = useVideoConfig();
  const words = text.toUpperCase().split(/\s+/).filter(Boolean);
  const size = big ? 128 : 100;
  const exit = interpolate(frame - (big ? 30 : 0), [exitAt - 6, exitAt], [1, 0], clamp);

  return (
    <div
      style={{
        position: "absolute",
        left: 80,
        right: 80,
        top: big ? 300 : 280,
        opacity: exit,
      }}
    >
      <div
        style={{
          height: 12,
          borderRadius: 6,
          backgroundColor: YELLOW,
          marginBottom: 22,
          width: interpolate(frame, [2, 16], [0, 120], { ...clamp, easing: Easing.out(Easing.cubic) }),
          boxShadow: "0 0 30px rgba(255,210,63,0.6)",
        }}
      />
      <div style={{ display: "flex", flexWrap: "wrap", columnGap: size * 0.26, rowGap: 0 }}>
        {words.map((w, i) => {
          const s = spring({ frame: frame - 3 - i * 3, fps, config: { damping: 16, stiffness: 170, mass: 0.7 } });
          return (
            <span key={i} style={{ overflow: "hidden", display: "inline-block", paddingBottom: 6 }}>
              <span
                style={{
                  display: "inline-block",
                  fontFamily: HEAD,
                  fontSize: size,
                  lineHeight: 1.04,
                  color: "white",
                  letterSpacing: 1,
                  textShadow: "0 6px 28px rgba(0,0,0,0.55)",
                  translate: `0px ${interpolate(s, [0, 1], [size * 1.1, 0])}px`,
                  rotate: `${interpolate(s, [0, 1], [6, 0])}deg`,
                }}
              >
                {w}
              </span>
            </span>
          );
        })}
      </div>
    </div>
  );
};

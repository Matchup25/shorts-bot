import React from "react";
import {
  AbsoluteFill,
  Easing,
  Img,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { BODY, HEAD } from "../fonts";
import { CATEGORY_COLORS, clamp, YELLOW } from "../theme";
import { Globe } from "./Globe";
import type { Place } from "./types";

const ease = Easing.bezier(0.16, 1, 0.3, 1);

const Backdrop: React.FC = () => (
  <AbsoluteFill
    style={{
      background: "radial-gradient(ellipse 70% 80% at 62% 50%, #1E2540 0%, #0C0F1C 60%, #05060B 100%)",
    }}
  />
);

/** Story opener: countdown number, place, headline and a globe that turns to the place. */
export const StoryCard: React.FC<{
  rank: number;
  headline: string;
  category: string;
  place: Place;
  from?: Place;
}> = ({ rank, headline, category, place, from }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const turn = interpolate(frame, [0, 1.3 * fps], [0, 1], { ...clamp, easing: ease });
  const start: [number, number] = from ? [-from.lon, -from.lat] : [-place.lon + 70, -place.lat * 0.3];
  let dLon = -place.lon - start[0];
  if (dLon > 180) dLon -= 360;
  if (dLon < -180) dLon += 360;
  const rotate: [number, number] = [start[0] + dLon * turn, start[1] + (-place.lat - start[1]) * turn];
  const zoom = interpolate(frame, [0, 1.3 * fps, durationInFrames], [0.92, 1.35, 1.45], clamp);
  const hl = interpolate(frame, [1.0 * fps, 1.5 * fps], [0, 1], clamp);
  const pulse = ((frame / fps) % 1.2) / 1.2;
  const num = spring({ frame: frame - 2, fps, config: { damping: 14, stiffness: 120 } });
  const words = headline.toUpperCase().split(/\s+/);
  const catColor = CATEGORY_COLORS[category] ?? YELLOW;
  const isGlobal = !place.country || place.country.toLowerCase() === "global";

  return (
    <AbsoluteFill>
      <Backdrop />
      <div style={{ position: "absolute", right: 60, top: 40, opacity: interpolate(frame, [0, 10], [0, 1], clamp) }}>
        <Globe
          size={1000}
          rotate={rotate}
          zoom={zoom}
          country={isGlobal ? undefined : place.country}
          pin={isGlobal ? undefined : { lat: place.lat, lon: place.lon }}
          pulse={pulse}
          highlight={hl}
        />
      </div>
      <div style={{ position: "absolute", left: 110, top: 170, width: 860 }}>
        <div
          style={{
            fontFamily: HEAD,
            fontSize: 300,
            lineHeight: 0.9,
            color: YELLOW,
            textShadow: "0 0 60px rgba(255,210,63,0.35)",
            scale: interpolate(num, [0, 1], [0.6, 1]),
            opacity: num,
            transformOrigin: "left center",
          }}
        >
          #{rank}
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 16,
            marginTop: 22,
            opacity: interpolate(frame, [8, 18], [0, 1], clamp),
            translate: `${interpolate(frame, [8, 18], [-30, 0], { ...clamp, easing: ease })}px 0px`,
          }}
        >
          <div
            style={{
              padding: "8px 18px",
              borderRadius: 999,
              backgroundColor: catColor,
              fontFamily: BODY,
              fontWeight: 800,
              fontSize: 26,
              letterSpacing: 3,
              color: "#0B0B10",
            }}
          >
            {category.toUpperCase()}
          </div>
          <div style={{ fontFamily: BODY, fontWeight: 800, fontSize: 34, letterSpacing: 3, color: "white" }}>
            {(isGlobal ? "WORLD" : place.label).toUpperCase()}
          </div>
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", columnGap: 26, marginTop: 26 }}>
          {words.map((w, i) => {
            const s = spring({ frame: frame - 12 - i * 3, fps, config: { damping: 16, stiffness: 170, mass: 0.7 } });
            return (
              <span key={i} style={{ overflow: "hidden", display: "inline-block" }}>
                <span
                  style={{
                    display: "inline-block",
                    fontFamily: HEAD,
                    fontSize: 104,
                    lineHeight: 1.04,
                    color: "white",
                    translate: `0px ${interpolate(s, [0, 1], [120, 0])}px`,
                  }}
                >
                  {w}
                </span>
              </span>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};

/** Story label shown over footage: rank, place and headline (top-left). */
export const StoryTag: React.FC<{ rank: number; headline: string; place: Place }> = ({ rank, headline, place }) => {
  const frame = useCurrentFrame();
  const inP = interpolate(frame, [0, 12], [0, 1], { ...clamp, easing: ease });
  const isGlobal = !place.country || place.country.toLowerCase() === "global";
  return (
    <div
      style={{
        position: "absolute",
        left: 80,
        top: 70,
        display: "flex",
        alignItems: "stretch",
        opacity: inP,
        translate: `${interpolate(inP, [0, 1], [-40, 0])}px 0px`,
      }}
    >
      <div
        style={{
          backgroundColor: YELLOW,
          color: "#0B0B10",
          fontFamily: HEAD,
          fontSize: 64,
          padding: "6px 22px",
          display: "flex",
          alignItems: "center",
        }}
      >
        #{rank}
      </div>
      <div style={{ backgroundColor: "rgba(8,9,15,0.78)", padding: "10px 26px", maxWidth: 1100 }}>
        <div style={{ fontFamily: BODY, fontWeight: 800, fontSize: 22, letterSpacing: 3, color: YELLOW }}>
          {(isGlobal ? "WORLD" : place.label).toUpperCase()}
        </div>
        <div style={{ fontFamily: HEAD, fontSize: 50, lineHeight: 1.1, color: "white" }}>{headline.toUpperCase()}</div>
      </div>
    </div>
  );
};

/** Channel badge, top right. */
export const WeeklyBug: React.FC<{ channel: string }> = ({ channel }) => (
  <div
    style={{
      position: "absolute",
      right: 70,
      top: 70,
      display: "flex",
      alignItems: "center",
      gap: 12,
      padding: "10px 22px 10px 16px",
      borderRadius: 999,
      backgroundColor: "rgba(8,9,15,0.6)",
      border: "1.5px solid rgba(255,255,255,0.18)",
    }}
  >
    <Img src={staticFile("brand/logo.png")} style={{ width: 44, height: 44, borderRadius: 22 }} />
    <span style={{ fontFamily: BODY, fontWeight: 800, fontSize: 24, letterSpacing: 3, color: "white" }}>
      {channel.toUpperCase()}
    </span>
    <span style={{ fontFamily: BODY, fontWeight: 800, fontSize: 24, letterSpacing: 3, color: YELLOW }}>WEEKLY</span>
  </div>
);

/** One block per story along the bottom; the current one fills up. */
export const ChapterBar: React.FC<{ segments: { start: number; end: number }[] }> = ({ segments }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  return (
    <div style={{ position: "absolute", left: 80, right: 80, bottom: 34, display: "flex", gap: 8 }}>
      {segments.map((s, i) => {
        const p = Math.max(0, Math.min(1, (t - s.start) / (s.end - s.start)));
        return (
          <div key={i} style={{ flex: 1, height: 8, borderRadius: 4, backgroundColor: "rgba(255,255,255,0.18)" }}>
            <div style={{ width: `${p * 100}%`, height: "100%", borderRadius: 4, backgroundColor: YELLOW }} />
          </div>
        );
      })}
    </div>
  );
};

/** Opening titles. */
export const Intro: React.FC<{ storyCount: number; dateRange: string; channel: string }> = ({
  storyCount,
  dateRange,
  channel,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const a = spring({ frame, fps, config: { damping: 15, stiffness: 110 } });
  const b = spring({ frame: frame - 10, fps, config: { damping: 15, stiffness: 110 } });
  const c = interpolate(frame, [22, 34], [0, 1], clamp);
  return (
    <AbsoluteFill>
      <Backdrop />
      <div style={{ position: "absolute", right: -120, top: 40, opacity: 0.9 }}>
        <Globe size={1000} rotate={[-frame * 0.6, -18]} zoom={1} pulse={0} highlight={0} />
      </div>
      <div style={{ position: "absolute", left: 120, top: 230, width: 1100 }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 20,
            opacity: a,
            translate: `${interpolate(a, [0, 1], [-40, 0])}px 0px`,
          }}
        >
          <Img src={staticFile("brand/logo.png")} style={{ width: 90, height: 90, borderRadius: 45 }} />
          <span style={{ fontFamily: BODY, fontWeight: 800, fontSize: 40, letterSpacing: 6, color: "white" }}>
            {channel.toUpperCase()} <span style={{ color: YELLOW }}>WEEKLY</span>
          </span>
        </div>
        <div
          style={{
            fontFamily: HEAD,
            fontSize: 170,
            lineHeight: 1,
            color: "white",
            marginTop: 30,
            opacity: b,
            translate: `0px ${interpolate(b, [0, 1], [60, 0])}px`,
          }}
        >
          THE WEEK IN <span style={{ color: YELLOW }}>{storyCount}</span> STORIES
        </div>
        <div
          style={{
            marginTop: 30,
            display: "inline-block",
            padding: "12px 28px",
            borderRadius: 999,
            backgroundColor: YELLOW,
            fontFamily: BODY,
            fontWeight: 800,
            fontSize: 36,
            letterSpacing: 4,
            color: "#0B0B10",
            opacity: c,
          }}
        >
          {dateRange}
        </div>
      </div>
    </AbsoluteFill>
  );
};

/** Closing card. */
export const Outro: React.FC<{ channel: string }> = ({ channel }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const a = spring({ frame, fps, config: { damping: 15, stiffness: 110 } });
  return (
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
      <Backdrop />
      <div style={{ position: "absolute", left: 460, top: 40, opacity: 0.35 }}>
        <Globe size={1000} rotate={[-frame * 0.6 + 40, -18]} zoom={1} pulse={0} highlight={0} />
      </div>
      <div style={{ textAlign: "center", opacity: a, scale: interpolate(a, [0, 1], [0.85, 1]) }}>
        <Img src={staticFile("brand/logo.png")} style={{ width: 200, height: 200, borderRadius: 100 }} />
        <div style={{ fontFamily: HEAD, fontSize: 130, color: "white", marginTop: 20 }}>
          THAT WAS <span style={{ color: YELLOW }}>THE WEEK</span>
        </div>
        <div style={{ fontFamily: BODY, fontWeight: 800, fontSize: 40, letterSpacing: 4, color: "white", marginTop: 10 }}>
          SUBSCRIBE TO {channel.toUpperCase()}
        </div>
        <div style={{ fontFamily: BODY, fontWeight: 600, fontSize: 32, color: "rgba(255,255,255,0.75)", marginTop: 12 }}>
          A new Short every day · the weekly show every Sunday
        </div>
      </div>
    </AbsoluteFill>
  );
};

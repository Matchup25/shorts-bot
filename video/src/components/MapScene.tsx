import React from "react";
import { AbsoluteFill, Easing, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { BODY } from "../fonts";
import { clamp } from "../theme";
import { Globe } from "../weekly/Globe";
import { isGlobalPlace } from "../weekly/Cards";
import type { Place } from "../weekly/types";

/** Full-screen scene for geography: a globe turns to the place, zooms in and highlights the country. */
export const MapScene: React.FC<{ place: Place; index: number }> = ({ place, index }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const ease = Easing.bezier(0.33, 1, 0.68, 1);
  const turn = interpolate(frame, [0, 1.6 * fps], [0, 1], { ...clamp, easing: ease });
  const side = index % 2 === 0 ? 1 : -1;
  const start: [number, number] = [-place.lon + 75 * side, -place.lat * 0.3];
  let dLon = -place.lon - start[0];
  if (dLon > 180) dLon -= 360;
  if (dLon < -180) dLon += 360;
  const rotate: [number, number] = [start[0] + dLon * turn, start[1] + (-place.lat - start[1]) * turn];
  const zoom = interpolate(frame, [0, 1.6 * fps, durationInFrames], [0.95, 1.55, 1.75], clamp);
  const hl = interpolate(frame, [1.2 * fps, 1.8 * fps], [0, 1], clamp);
  const pulse = (frame % Math.round(1.2 * fps)) / (1.2 * fps);
  const global = isGlobalPlace(place);
  const size = 980;

  return (
    <AbsoluteFill style={{ background: "radial-gradient(circle at 50% 50%, #131A30 0%, #05070E 75%)" }}>
      <div style={{ position: "absolute", left: (1080 - size) / 2, top: 560 }}>
        <Globe
          size={size}
          rotate={rotate}
          zoom={zoom}
          country={global ? undefined : place.country}
          pin={global ? undefined : { lat: place.lat, lon: place.lon }}
          pulse={pulse}
          highlight={hl}
        />
      </div>
    </AbsoluteFill>
  );
};

/** Place name under the globe; drawn above the dark shade so it stays bright. */
export const PlaceLabel: React.FC<{ place: Place }> = ({ place }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const a = interpolate(frame, [1.2 * fps, 1.8 * fps], [0, 1], clamp);
  const global = isGlobalPlace(place);
  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        top: 1500,
        textAlign: "center",
        fontFamily: BODY,
        fontWeight: 800,
        fontSize: 46,
        letterSpacing: 4,
        color: "white",
        opacity: a,
        translate: `0px ${interpolate(a, [0, 1], [20, 0])}px`,
        textShadow: "0 4px 18px rgba(0,0,0,0.9)",
      }}
    >
      📍 {(global ? "WORLD" : place.label).toUpperCase()}
    </div>
  );
};

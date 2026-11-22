import React from "react";
import { AbsoluteFill, Img, staticFile } from "remotion";
import { BODY, HEAD } from "../fonts";
import "../fonts";
import { YELLOW } from "../theme";
import { Globe } from "./Globe";
import type { ThumbProps } from "./types";

/** 1280x720 thumbnail for the weekly show. */
export const WeeklyThumb: React.FC<ThumbProps> = ({ dateRange, storyCount, topHeadline, image, place }) => (
  <AbsoluteFill style={{ backgroundColor: "#07080D" }}>
    {image ? (
      <Img
        src={staticFile(image)}
        style={{ position: "absolute", right: 0, top: 0, width: 760, height: 720, objectFit: "cover" }}
      />
    ) : null}
    <AbsoluteFill
      style={{
        background:
          "linear-gradient(90deg, #07080D 0%, #07080D 42%, rgba(7,8,13,0.75) 58%, rgba(7,8,13,0.15) 100%)",
      }}
    />
    <div style={{ position: "absolute", right: -60, bottom: -150, opacity: 0.9 }}>
      <Globe
        size={520}
        rotate={place ? [-place.lon, -place.lat] : [-10, -20]}
        zoom={1}
        country={place?.country}
        pin={place ? { lat: place.lat, lon: place.lon } : undefined}
        pulse={0.3}
        highlight={1}
      />
    </div>
    <div style={{ position: "absolute", left: 56, top: 70, width: 700 }}>
      <div style={{ fontFamily: HEAD, fontSize: 210, lineHeight: 0.9, color: YELLOW }}>{storyCount}</div>
      <div style={{ fontFamily: HEAD, fontSize: 96, lineHeight: 1.0, color: "white" }}>
        STORIES THAT SHAPED THE WEEK
      </div>
      <div
        style={{
          marginTop: 22,
          display: "inline-block",
          padding: "8px 20px",
          borderRadius: 999,
          backgroundColor: YELLOW,
          fontFamily: BODY,
          fontWeight: 800,
          fontSize: 28,
          letterSpacing: 3,
          color: "#0B0B10",
        }}
      >
        {dateRange}
      </div>
      <div
        style={{
          marginTop: 18,
          fontFamily: BODY,
          fontWeight: 800,
          fontSize: 30,
          color: "white",
          textTransform: "uppercase",
          width: 640,
        }}
      >
        #1 · {topHeadline}
      </div>
    </div>
  </AbsoluteFill>
);

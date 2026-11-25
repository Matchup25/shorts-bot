import React, { useMemo } from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { BODY } from "../fonts";
import { clamp, useAccent } from "../theme";
import type { Word } from "../types";

type Chunk = { words: Word[]; start: number; end: number };

const buildChunks = (words: Word[], maxWords: number, maxChars: number): Chunk[] => {
  const chunks: Chunk[] = [];
  let cur: Word[] = [];
  words.forEach((w, i) => {
    cur.push(w);
    const punct = /[.,!?;:]$/.test(w.text);
    const gap = i + 1 < words.length ? words[i + 1].start - w.end : 1;
    const chars = cur.reduce((n, x) => n + x.text.length + 1, 0);
    const nextLen = i + 1 < words.length ? words[i + 1].text.length : 0;
    if (cur.length === maxWords || punct || gap > 0.25 || chars + nextLen > maxChars) {
      chunks.push({ words: cur, start: cur[0].start, end: w.end });
      cur = [];
    }
  });
  if (cur.length) chunks.push({ words: cur, start: cur[0].start, end: cur[cur.length - 1].end });
  return chunks.map((c, i) => ({
    ...c,
    end: Math.min(i + 1 < chunks.length ? chunks[i + 1].start : c.end + 0.6, c.end + 0.4),
  }));
};

/** Big social-style captions: 1-3 words, the spoken word turns yellow and pops. */
export const Captions: React.FC<{
  words: Word[];
  top?: number;
  scale?: number;
  maxWords?: number;
  maxChars?: number;
}> = ({ words, top = 1130, scale = 1, maxWords = 3, maxChars = 17 }) => {
  const frame = useCurrentFrame();
  const YELLOW = useAccent();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const chunks = useMemo(() => buildChunks(words, maxWords, maxChars), [words, maxWords, maxChars]);
  const chunk = chunks.find((c) => t >= c.start && t < c.end);
  if (!chunk) return null;

  const local = (t - chunk.start) * fps;
  const pop = spring({ frame: local, fps, config: { damping: 11, stiffness: 260, mass: 0.6 } });
  const total = chunk.words.reduce((n, w) => n + w.text.length, 0) + chunk.words.length;
  const size = (total > 15 ? 76 : total > 11 ? 86 : 96) * scale;

  return (
    <div
      style={{
        position: "absolute",
        left: 60,
        right: 60,
        top,
        height: 260 * scale,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        flexWrap: "wrap",
        columnGap: size * 0.42,
        scale: interpolate(pop, [0, 1], [0.72, 1]),
        translate: `0px ${interpolate(pop, [0, 1], [26, 0])}px`,
        opacity: interpolate(local, [0, 2], [0, 1], clamp),
      }}
    >
      {chunk.words.map((w, i) => {
        const active = t >= w.start && (t < w.end || i === chunk.words.length - 1);
        const wPop = spring({ frame: (t - w.start) * fps, fps, config: { damping: 10, stiffness: 300, mass: 0.5 } });
        return (
          <span
            key={i}
            style={{
              fontFamily: BODY,
              fontWeight: 900,
              fontSize: size,
              lineHeight: 1.12,
              textTransform: "uppercase",
              color: active ? YELLOW : "white",
              WebkitTextStroke: `${Math.round(size / 9)}px black`,
              paintOrder: "stroke fill",
              textShadow: "0 10px 30px rgba(0,0,0,0.7)",
              display: "inline-block",
              margin: active ? `0 ${size * 0.06}px` : 0,
              scale: active ? interpolate(wPop, [0, 1], [1, 1.08]) : 1,
              rotate: active ? `${interpolate(wPop, [0, 1], [0, -2])}deg` : "0deg",
            }}
          >
            {w.text.replace(/["“”]/g, "")}
          </span>
        );
      })}
    </div>
  );
};

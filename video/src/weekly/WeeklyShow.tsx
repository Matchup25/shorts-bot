import { Audio } from "@remotion/media";
import React from "react";
import { AbsoluteFill, Sequence, staticFile, useVideoConfig } from "remotion";
import { Captions } from "../components/Captions";
import { Flash, Grain, Shade } from "../components/Chrome";
import { SceneMedia } from "../components/SceneMedia";
import { Stat } from "../components/Stat";
import "../fonts";
import { ChapterBar, Intro, Outro, StoryCard, StoryTag, WeeklyBug } from "./Cards";
import type { Segment, WeeklyProps, WScene } from "./types";

const OVERLAP = 10;

type Flat = { scene: WScene; seg: Segment; segIndex: number; first: boolean };

export const WeeklyShow: React.FC<WeeklyProps> = ({
  channel,
  dateRange,
  storyCount,
  audio,
  intro,
  outro,
  segments,
  words,
}) => {
  const { fps, durationInFrames } = useVideoConfig();
  const flat: Flat[] = segments.flatMap((seg, segIndex) =>
    seg.scenes.map((scene, i) => ({ scene, seg, segIndex, first: i === 0 })),
  );
  const introEnd = Math.round(intro.end * fps) + 6;
  const outroStart = Math.round(outro.start * fps) - 6;
  const starts = flat.map((f, i) => (i === 0 ? introEnd : Math.round(f.scene.start * fps) - 4));

  return (
    <AbsoluteFill style={{ backgroundColor: "black" }}>
      {flat.map((f, i) => {
        const from = starts[i];
        const next = i + 1 < flat.length ? starts[i + 1] : outroStart;
        const len = Math.max(1, next - from + OVERLAP);
        const prevPlace = f.segIndex > 0 ? segments[f.segIndex - 1].place : undefined;
        return (
          <Sequence key={`s${i}`} from={from} durationInFrames={len} name={`#${f.seg.rank} ${f.scene.kind}`}>
            {f.scene.kind === "map" || !f.scene.media ? (
              <StoryCard
                rank={f.seg.rank}
                headline={f.seg.headline}
                category={f.seg.category}
                place={f.seg.place}
                from={prevPlace}
              />
            ) : (
              <AbsoluteFill>
                <SceneMedia
                  scene={{ media: f.scene.media, transition: f.scene.transition }}
                  index={i}
                  darken={f.scene.kind === "stat" ? 0.5 : 0.85}
                />
                <Shade />
                {f.scene.kind === "stat" && f.scene.stat ? (
                  <Stat value={f.scene.stat.value} unit={f.scene.stat.unit} top={150} />
                ) : null}
                <StoryTag rank={f.seg.rank} headline={f.seg.headline} place={f.seg.place} />
              </AbsoluteFill>
            )}
          </Sequence>
        );
      })}

      <Sequence from={0} durationInFrames={introEnd + OVERLAP} name="Intro">
        <Intro storyCount={storyCount} dateRange={dateRange} channel={channel} />
      </Sequence>
      <Sequence from={outroStart} durationInFrames={Math.max(1, durationInFrames - outroStart)} name="Outro">
        <Outro channel={channel} />
      </Sequence>

      {segments.map((seg, i) => (
        <Sequence key={`f${i}`} from={Math.round(seg.start * fps) - 4} durationInFrames={8} layout="none">
          <Flash strength={0.35} />
        </Sequence>
      ))}

      <Sequence from={introEnd} durationInFrames={Math.max(1, outroStart - introEnd)} layout="none">
        <WeeklyBug channel={channel} />
      </Sequence>
      <Captions words={words} top={845} scale={0.62} maxWords={5} maxChars={30} />
      <ChapterBar segments={segments.map((s) => ({ start: s.start, end: s.end }))} />
      <Grain />
      <Audio src={staticFile(audio)} />
    </AbsoluteFill>
  );
};

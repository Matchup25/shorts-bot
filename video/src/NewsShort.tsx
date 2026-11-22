import { Audio } from "@remotion/media";
import React from "react";
import { AbsoluteFill, Sequence, staticFile, useVideoConfig } from "remotion";
import { Brand, Flash, Grain, Progress, Shade } from "./components/Chrome";
import { Captions } from "./components/Captions";
import { Headline } from "./components/Headline";
import { SceneMedia } from "./components/SceneMedia";
import { Stat } from "./components/Stat";
import "./fonts";
import type { ShortProps } from "./types";

const OVERLAP = 10; // frames the next scene overlaps the previous one (its entrance)

export const NewsShort: React.FC<ShortProps> = ({ channel, category, audio, scenes, words }) => {
  const { fps, durationInFrames } = useVideoConfig();
  const starts = scenes.map((s, i) => (i === 0 ? 0 : Math.round(s.start * fps) - 4));

  return (
    <AbsoluteFill style={{ backgroundColor: "black" }}>
      {scenes.map((scene, i) => {
        const from = starts[i];
        const next = i + 1 < scenes.length ? starts[i + 1] : durationInFrames;
        const len = Math.max(1, next - from + OVERLAP);
        return (
          <Sequence key={`m${i}`} from={from} durationInFrames={len} name={`Scene ${i + 1}`}>
            <SceneMedia scene={scene} index={i} darken={scene.kind === "stat" ? 0.55 : 0.88} />
          </Sequence>
        );
      })}

      <Shade />

      {scenes.map((scene, i) => {
        const from = starts[i];
        const next = i + 1 < scenes.length ? starts[i + 1] : durationInFrames;
        const len = Math.max(1, next - from);
        return (
          <Sequence key={`t${i}`} from={from} durationInFrames={len} name={`Text ${i + 1}`} layout="none">
            {scene.kind === "stat" && scene.stat ? <Stat value={scene.stat.value} unit={scene.stat.unit} /> : null}
            <Headline text={scene.headline} big={i === 0} exitAt={len} />
            <Brand channel={channel} category={category} credit={scene.media.credit} />
          </Sequence>
        );
      })}

      <Captions words={words} />

      {scenes.slice(1).map((scene, i) => (
        <Sequence key={`f${i}`} from={starts[i + 1]} durationInFrames={8} layout="none">
          <Flash strength={scene.transition === "flash" ? 0.55 : 0.18} />
        </Sequence>
      ))}

      <Grain />
      <Progress />
      <Audio src={staticFile(audio)} />
    </AbsoluteFill>
  );
};

import { Audio } from "@remotion/media";
import React from "react";
import { AbsoluteFill, Sequence, staticFile, useVideoConfig } from "remotion";
import { Brand, Credit, Flash, Grain, Progress, Shade } from "./components/Chrome";
import { Captions } from "./components/Captions";
import { Headline } from "./components/Headline";
import { SceneMedia } from "./components/SceneMedia";
import { Stat } from "./components/Stat";
import "./fonts";
import { AccentContext, YELLOW } from "./theme";
import type { ShortProps } from "./types";

const OVERLAP = 10; // frames the next scene overlaps the previous one (its entrance)
const CUT_AFTER = 4.2; // seconds: longer scenes are split into two shots

export const NewsShort: React.FC<ShortProps> = ({ channel, category, audio, scenes, words, accent, look }) => {
  const { fps, durationInFrames } = useVideoConfig();
  const starts = scenes.map((s, i) => (i === 0 ? 0 : Math.round(s.start * fps) - 4));
  const orbit = look === "3d";

  return (
    <AccentContext.Provider value={accent ?? YELLOW}>
    <AbsoluteFill style={{ backgroundColor: "black" }}>
      {scenes.map((scene, i) => {
        const from = starts[i];
        const next = i + 1 < scenes.length ? starts[i + 1] : durationInFrames;
        const len = Math.max(1, next - from + OVERLAP);
        const darken = scene.kind === "stat" ? 0.55 : 0.88;
        // Faster rhythm: scenes longer than ~4 s get a cut halfway, to a second shot
        // (or a punch-in on the same picture when there is no second one).
        const cut = next - from >= Math.round(CUT_AFTER * fps) ? Math.round((next - from) / 2) : 0;
        if (!cut) {
          return (
            <Sequence key={`m${i}`} from={from} durationInFrames={len} name={`Scene ${i + 1}`}>
              <SceneMedia scene={scene} index={i} darken={darken} orbit={orbit} />
            </Sequence>
          );
        }
        const second = scene.media2 ?? scene.media;
        const same = !scene.media2;
        return (
          <React.Fragment key={`m${i}`}>
            <Sequence from={from} durationInFrames={cut + 2} name={`Scene ${i + 1}a`}>
              <SceneMedia scene={scene} index={i} darken={darken} orbit={orbit} />
            </Sequence>
            <Sequence from={from + cut} durationInFrames={Math.max(1, len - cut)} name={`Scene ${i + 1}b`}>
              <SceneMedia
                scene={{ media: second, transition: "cut" }}
                index={i}
                part={1}
                darken={darken}
                orbit={orbit}
                zoom={same ? 1.32 : 1}
                trimBefore={same && second.type === "video" ? cut : undefined}
              />
            </Sequence>
          </React.Fragment>
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
            <Credit text={scene.media.credit} />
          </Sequence>
        );
      })}

      <Brand channel={channel} category={category} />
      <Captions words={words} />

      {scenes.slice(1).map((scene, i) =>
        scene.transition === "flash" ? (
          <Sequence key={`f${i}`} from={starts[i + 1]} durationInFrames={8} layout="none">
            <Flash strength={0.6} />
          </Sequence>
        ) : null,
      )}

      <Grain />
      <Progress />
      <Audio src={staticFile(audio)} />
    </AbsoluteFill>
    </AccentContext.Provider>
  );
};

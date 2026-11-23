import { Video } from "@remotion/media";
import React from "react";
import {
  AbsoluteFill,
  Easing,
  Img,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { clamp } from "../theme";
import type { Media, Scene } from "../types";

const ENTER = 9; // frames of the entrance transition

/**
 * Full-screen footage or photo with a slow cinematic push-in,
 * colour grade and an entrance transition (zoom punch / whip pan / flash cut).
 */
export const SceneMedia: React.FC<{
  scene: { media: Media; transition: Scene["transition"] };
  index: number;
  darken: number;
  part?: number; // 0 = first shot of the scene, 1 = second shot (after the mid-scene cut)
  zoom?: number; // extra zoom: a "punch-in" when the second shot reuses the same picture
  trimBefore?: number; // frames to skip at the start of a video (continue where the first shot was)
}> = ({
  scene,
  index,
  darken,
  part = 0,
  zoom = 1,
  trimBefore,
}) => {
  const frame = useCurrentFrame();
  const { durationInFrames, width, height } = useVideoConfig();
  const media = scene.media;
  const isLandscape = (media.width ?? width) / (media.height ?? height) > (width / height) * 1.3;
  const drift = (index + part) % 2 === 0 ? 1 : -1;
  const isFirst = index === 0 && part === 0;

  const enter = isFirst
    ? 1
    : interpolate(frame, [0, ENTER], [0, 1], { ...clamp, easing: Easing.out(Easing.cubic) });

  let enterScale = 1;
  let enterX = 0;
  let enterBlur = 0;
  let enterSkew = 0;
  if (scene.transition === "cut") {
    // hard cut with a small punch, like an editor's jump cut
    enterScale = interpolate(frame, [0, 6], [1.12, 1], { ...clamp, easing: Easing.out(Easing.cubic) });
  } else if (scene.transition === "zoom") {
    enterScale = interpolate(enter, [0, 1], [1.45, 1]);
    enterBlur = interpolate(enter, [0, 1], [22, 0]);
  } else if (scene.transition === "whip-left" || scene.transition === "whip-right") {
    const dir = scene.transition === "whip-left" ? 1 : -1;
    enterX = interpolate(enter, [0, 1], [dir * width, 0]);
    enterBlur = interpolate(enter, [0, 0.7, 1], [26, 8, 0]);
    enterSkew = interpolate(enter, [0, 1], [dir * -8, 0]);
  }

  return (
    <AbsoluteFill style={{ overflow: "hidden", backgroundColor: isFirst ? "black" : "transparent" }}>
      <AbsoluteFill
        style={{
          translate: `${enterX}px 0px`,
          scale: enterScale,
          transform: `skewX(${enterSkew}deg)`,
          filter: `blur(${enterBlur}px) contrast(1.08) saturate(1.12) brightness(${darken})`,
          opacity: isFirst || scene.transition === "cut" ? 1 : interpolate(frame, [0, 4], [0.6, 1], clamp),
        }}
      >
        <AbsoluteFill
          style={{
            scale: zoom * interpolate(frame, [0, durationInFrames], [1.06, 1.2], clamp),
            translate: `${interpolate(frame, [0, durationInFrames], [0, drift * 24], clamp)}px ${interpolate(
              frame,
              [0, durationInFrames],
              [0, -30],
              clamp,
            )}px`,
          }}
        >
          {media.type === "video" ? (
            <Video
              src={staticFile(media.src)}
              muted
              loop
              trimBefore={trimBefore}
              style={{ width: "100%", height: "100%", objectFit: "cover" }}
            />
          ) : (
            <Img
              src={staticFile(media.src)}
              style={{
                width: "100%",
                height: "100%",
                objectFit: "cover",
                objectPosition: isLandscape
                  ? `${interpolate(frame, [0, durationInFrames], drift > 0 ? [30, 70] : [70, 30], clamp)}% 50%`
                  : "50% 50%",
              }}
            />
          )}
        </AbsoluteFill>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

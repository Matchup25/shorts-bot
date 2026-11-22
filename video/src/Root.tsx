import React from "react";
import { CalculateMetadataFunction, Composition, Still } from "remotion";
import demo from "./demo-props.json";
import weeklyDemo from "./weekly/demo-weekly.json";
import { NewsShort } from "./NewsShort";
import type { ShortProps } from "./types";
import type { ThumbProps, WeeklyProps } from "./weekly/types";
import { WeeklyShow } from "./weekly/WeeklyShow";
import { WeeklyThumb } from "./weekly/WeeklyThumb";

const FPS = 30;

const shortMeta: CalculateMetadataFunction<ShortProps> = ({ props }) => ({
  durationInFrames: Math.max(30, Math.ceil(props.duration * FPS)),
});

const weeklyMeta: CalculateMetadataFunction<WeeklyProps> = ({ props }) => ({
  durationInFrames: Math.max(30, Math.ceil(props.duration * FPS)),
});

const thumbDemo: ThumbProps = {
  dateRange: "NOV 16 – 22, 2026",
  storyCount: 15,
  topHeadline: "Example headline of the week",
};

export const RemotionRoot: React.FC = () => (
  <>
    <Composition
      id="NewsShort"
      component={NewsShort}
      durationInFrames={1350}
      fps={FPS}
      width={1080}
      height={1920}
      defaultProps={demo as ShortProps}
      calculateMetadata={shortMeta}
    />
    <Composition
      id="WeeklyShow"
      component={WeeklyShow}
      durationInFrames={27000}
      fps={FPS}
      width={1920}
      height={1080}
      defaultProps={weeklyDemo as WeeklyProps}
      calculateMetadata={weeklyMeta}
    />
    <Still id="WeeklyThumb" component={WeeklyThumb} width={1280} height={720} defaultProps={thumbDemo} />
  </>
);

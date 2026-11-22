import React from "react";
import { CalculateMetadataFunction, Composition } from "remotion";
import demo from "./demo-props.json";
import { NewsShort } from "./NewsShort";
import type { ShortProps } from "./types";

const FPS = 30;

const calculateMetadata: CalculateMetadataFunction<ShortProps> = ({ props }) => ({
  durationInFrames: Math.max(30, Math.ceil(props.duration * FPS)),
});

export const RemotionRoot: React.FC = () => (
  <Composition
    id="NewsShort"
    component={NewsShort}
    durationInFrames={1350}
    fps={FPS}
    width={1080}
    height={1920}
    defaultProps={demo as ShortProps}
    calculateMetadata={calculateMetadata}
  />
);

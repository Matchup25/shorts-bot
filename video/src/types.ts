export type Word = {
  text: string;
  start: number; // seconds
  end: number; // seconds
};

export type Media = {
  type: "video" | "image";
  src: string; // path inside public/
  credit?: string;
  width?: number;
  height?: number;
};

export type Scene = {
  start: number; // seconds
  end: number; // seconds
  headline: string;
  kind: "media" | "stat" | "map";
  media: Media; // for "map" scenes: a dark placeholder (not shown)
  place?: { label: string; country: string; lat: number; lon: number }; // "map" scenes
  media2?: Media; // second shot for the second half of the scene (faster rhythm)
  stat?: { value: string; unit: string };
  transition: "zoom" | "whip-left" | "whip-right" | "flash" | "cut";
};

export type ShortProps = {
  channel: string;
  accent?: string; // channel colour (default yellow)
  look?: "3d"; // "3d": stills get a slow orbiting camera (explainer channel)
  category: string;
  audio: string; // path inside public/
  duration: number; // seconds
  scenes: Scene[];
  words: Word[];
};

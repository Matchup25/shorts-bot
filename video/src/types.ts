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
  kind: "media" | "stat";
  media: Media;
  stat?: { value: string; unit: string };
  transition: "zoom" | "whip-left" | "whip-right" | "flash";
};

export type ShortProps = {
  channel: string;
  category: string;
  audio: string; // path inside public/
  duration: number; // seconds
  scenes: Scene[];
  words: Word[];
};

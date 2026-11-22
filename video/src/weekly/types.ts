import type { Media, Word } from "../types";

export type Place = {
  label: string; // e.g. "Seoul, South Korea"
  country: string; // English country name or "Global"
  lat: number;
  lon: number;
};

export type WScene = {
  start: number;
  end: number;
  kind: "map" | "media" | "stat";
  media?: Media;
  stat?: { value: string; unit: string };
  transition: "zoom" | "whip-left" | "whip-right" | "flash";
};

export type Segment = {
  rank: number; // countdown number shown on screen (15 … 1)
  start: number;
  end: number;
  headline: string;
  category: string;
  place: Place;
  scenes: WScene[];
};

export type WeeklyProps = {
  channel: string;
  dateRange: string; // e.g. "NOV 16 – 22, 2026"
  storyCount: number;
  audio: string;
  duration: number;
  intro: { start: number; end: number };
  outro: { start: number; end: number };
  segments: Segment[];
  words: Word[];
};

export type ThumbProps = {
  dateRange: string;
  storyCount: number;
  topHeadline: string;
  image?: string; // path in public/ (image only)
  place?: Place;
};

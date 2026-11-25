import React from "react";

export const YELLOW = "#FFD23F";
// accent colour of the channel (World in a Shot: yellow, RerumFabrica: orange), set by the composition
export const AccentContext = React.createContext<string>(YELLOW);
export const useAccent = () => React.useContext(AccentContext);
export const RED = "#FF3B3B";
export const WHITE = "#FFFFFF";

export const CATEGORY_COLORS: Record<string, string> = {
  space: "#8B7CFF",
  science: "#4FD1C5",
  tech: "#38BDF8",
  world: "#FF6B57",
  business: "#34D399",
  health: "#60A5FA",
  nature: "#86EFAC",
  weird: "#F472B6",
  culture: "#FBBF24",
  education: "#FF6A1A",
};

export const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

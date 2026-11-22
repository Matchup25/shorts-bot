import { geoGraticule10, geoOrthographic, geoPath } from "d3-geo";
import React, { useMemo } from "react";
import { COUNTRIES, findCountry } from "./geo";
import { YELLOW } from "../theme";

/** Orthographic globe drawn as SVG: countries, graticule, a highlighted country and a pulsing pin. */
export const Globe: React.FC<{
  size: number;
  rotate: [number, number];
  zoom: number;
  country?: string;
  pin?: { lat: number; lon: number };
  pulse: number; // 0..1
  highlight: number; // 0..1 opacity of the highlighted country
}> = ({ size, rotate, zoom, country, pin, pulse, highlight }) => {
  const target = useMemo(() => (country ? findCountry(country) : undefined), [country]);
  const r = (size / 2) * 0.92;
  const projection = geoOrthographic()
    .scale(r * zoom)
    .translate([size / 2, size / 2])
    .rotate([rotate[0], rotate[1], 0])
    .clipAngle(90);
  const path = geoPath(projection);
  const sphere = path({ type: "Sphere" }) ?? "";
  const grid = path(geoGraticule10()) ?? "";
  const land = COUNTRIES.features.map((f) => path(f) ?? "").join(" ");
  const hi = target ? path(target) ?? "" : "";
  const p = pin ? projection([pin.lon, pin.lat]) : null;

  return (
    <svg width={size} height={size} style={{ overflow: "visible" }}>
      <defs>
        <radialGradient id="ocean" cx="40%" cy="35%" r="75%">
          <stop offset="0%" stopColor="#1B2440" />
          <stop offset="100%" stopColor="#0A0E1C" />
        </radialGradient>
        <radialGradient id="atmo" cx="50%" cy="50%" r="50%">
          <stop offset="85%" stopColor="rgba(255,210,63,0)" />
          <stop offset="100%" stopColor="rgba(255,210,63,0.25)" />
        </radialGradient>
      </defs>
      <circle cx={size / 2} cy={size / 2} r={r * zoom * 1.06} fill="url(#atmo)" />
      <path d={sphere} fill="url(#ocean)" stroke="rgba(255,210,63,0.45)" strokeWidth={3} />
      <path d={grid} fill="none" stroke="rgba(255,255,255,0.07)" strokeWidth={1.2} />
      <path d={land} fill="#2A3352" stroke="#46507A" strokeWidth={0.8} />
      {hi ? (
        <path
          d={hi}
          fill={YELLOW}
          fillOpacity={0.92 * highlight}
          stroke="#FFF3C4"
          strokeWidth={1.5}
          style={{ filter: `drop-shadow(0 0 ${18 * highlight}px rgba(255,210,63,0.9))` }}
        />
      ) : null}
      {p ? (
        <g opacity={highlight}>
          <circle cx={p[0]} cy={p[1]} r={10 + 46 * pulse} fill="none" stroke={YELLOW} strokeWidth={4} opacity={1 - pulse} />
          <circle cx={p[0]} cy={p[1]} r={11} fill="#FF3B3B" stroke="white" strokeWidth={4} />
        </g>
      ) : null}
    </svg>
  );
};

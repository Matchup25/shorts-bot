import { feature } from "topojson-client";
import type { Feature, FeatureCollection, Geometry } from "geojson";
import atlas from "./countries-50m.json";

type Props = { name: string };

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const topo = atlas as any;
export const COUNTRIES = feature(topo, topo.objects.countries) as unknown as FeatureCollection<Geometry, Props>;

const ALIASES: Record<string, string> = {
  "usa": "United States of America",
  "us": "United States of America",
  "united states": "United States of America",
  "america": "United States of America",
  "uk": "United Kingdom",
  "britain": "United Kingdom",
  "great britain": "United Kingdom",
  "england": "United Kingdom",
  "scotland": "United Kingdom",
  "wales": "United Kingdom",
  "northern ireland": "United Kingdom",
  "democratic republic of the congo": "Dem. Rep. Congo",
  "dr congo": "Dem. Rep. Congo",
  "drc": "Dem. Rep. Congo",
  "republic of the congo": "Congo",
  "czech republic": "Czechia",
  "ivory coast": "Côte d'Ivoire",
  "cote d'ivoire": "Côte d'Ivoire",
  "bosnia": "Bosnia and Herz.",
  "bosnia and herzegovina": "Bosnia and Herz.",
  "central african republic": "Central African Rep.",
  "south sudan": "S. Sudan",
  "dominican republic": "Dominican Rep.",
  "equatorial guinea": "Eq. Guinea",
  "gaza": "Palestine",
  "west bank": "Palestine",
  "palestinian territories": "Palestine",
  "korea": "South Korea",
  "republic of korea": "South Korea",
  "dprk": "North Korea",
  "uae": "United Arab Emirates",
  "eswatini": "eSwatini",
  "north macedonia": "Macedonia",
  "myanmar": "Myanmar",
  "burma": "Myanmar",
  "vatican": "Italy",
  "vatican city": "Italy",
  "hong kong": "China",
};

export const findCountry = (name: string): Feature<Geometry, Props> | undefined => {
  if (!name) return undefined;
  const key = name.trim().toLowerCase();
  const target = (ALIASES[key] ?? name).toLowerCase();
  return (
    COUNTRIES.features.find((f) => f.properties.name.toLowerCase() === target) ??
    COUNTRIES.features.find((f) => f.properties.name.toLowerCase().startsWith(target)) ??
    COUNTRIES.features.find((f) => target.includes(f.properties.name.toLowerCase()))
  );
};

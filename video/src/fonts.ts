import { loadFont } from "@remotion/fonts";
import { staticFile } from "remotion";

export const HEAD = "Anton";
export const BODY = "Montserrat";

loadFont({ family: HEAD, url: staticFile("fonts/Anton-Regular.ttf"), weight: "400" });
loadFont({ family: BODY, url: staticFile("fonts/Montserrat.ttf"), weight: "100 900" });

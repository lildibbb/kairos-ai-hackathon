import { loadFont as loadInter } from "@remotion/google-fonts/Inter";
import { loadFont as loadInterTight } from "@remotion/google-fonts/InterTight";

// Palette sampled from "Kairos Next Best Action" deck, pushed darker for the cinematic look.
export const C = {
  ink: "#06013A",
  inkDeep: "#030020",
  indigo: "#13009A",
  blue: "#1A00E6",
  glow: "#4A3BFF",
  peri: "#9DB4F7",
  orange: "#FF6200",
  orangeSoft: "#FF8A3D",
  white: "#FFFFFF",
  paper: "#F3F6FD",
  line: "#DCE3F5",
  text: "#0B0A2E",
  muted: "#5B6285",
  green: "#12B76A",
  greenSoft: "#E3F8EE",
  amber: "#E07B00",
  amberSoft: "#FFF1E3",
};

const display = loadInterTight("normal", { weights: ["500", "600", "700", "800"], subsets: ["latin"] });
const ui = loadInter("normal", { weights: ["400", "500", "600", "700"], subsets: ["latin"] });

export const F = {
  display: display.fontFamily,
  ui: ui.fontFamily,
};

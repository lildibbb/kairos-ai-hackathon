import { bundle } from "@remotion/bundler";
import { renderStill, selectComposition } from "@remotion/renderer";
import path from "node:path";

const out = process.env.OUT;
const times = process.argv.slice(2).map(Number);
const serveUrl = await bundle({ entryPoint: path.resolve("src/index.ts") });
const composition = await selectComposition({ serveUrl, id: "KairosPromo" });
for (const s of times) {
  const frame = Math.round(s * 30);
  await renderStill({ composition, serveUrl, frame, output: `${out}/t${String(s).replace(".", "_")}.jpg`, imageFormat: "jpeg", scale: 0.5 });
  console.log("still", s);
}

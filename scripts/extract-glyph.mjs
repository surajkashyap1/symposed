// Dev utility: find the cached Newsreader woff2 and print the "S" glyph as
// an SVG path scaled into a 64x64 viewBox.
//   node scripts/extract-glyph.mjs
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { execFileSync } from "node:child_process";
import opentype from "opentype.js";

const dir = ".next/dev/static/media";
const files = readdirSync(dir).filter((f) => f.endsWith(".woff2"));

for (const f of files) {
  const woff = join(dir, f);
  // opentype.js can't parse woff2 directly; decompress with woff2_decompress
  // if available, else try fontkit-style raw parse via python? Simplest:
  // use the wawoff2 npm package.
  const { decompress } = await import("wawoff2");
  const ttf = await decompress(readFileSync(woff));
  let font;
  try {
    font = opentype.parse(Uint8Array.from(ttf).buffer);
  } catch {
    continue;
  }
  const name = font.names?.fontFamily?.en ?? "?";
  const weight = font.tables?.os2?.usWeightClass;
  const italic = font.tables?.head?.macStyle & 2 ? "italic" : "";
  if (!/newsreader/i.test(name)) continue;
  console.log(`# ${f}: ${name} ${weight} ${italic}`);
  if (weight !== 600 || italic) continue;

  const glyph = font.charToGlyph("S");
  const unitsPerEm = font.unitsPerEm;
  // Scale so cap height fills ~46 units of the 64 box, centered.
  const path = glyph.getPath(0, 0, 64 * (unitsPerEm / (font.tables.os2.sCapHeight ?? unitsPerEm * 0.7)) * 0.72);
  const bb = path.getBoundingBox();
  const w = bb.x2 - bb.x1, h = bb.y2 - bb.y1;
  const dx = (64 - w) / 2 - bb.x1, dy = (64 - h) / 2 - bb.y1;
  let d = "";
  for (const c of path.commands) {
    if (c.type === "M") d += `M${(c.x + dx).toFixed(1)} ${(c.y + dy).toFixed(1)}`;
    else if (c.type === "L") d += `L${(c.x + dx).toFixed(1)} ${(c.y + dy).toFixed(1)}`;
    else if (c.type === "C") d += `C${(c.x1 + dx).toFixed(1)} ${(c.y1 + dy).toFixed(1)} ${(c.x2 + dx).toFixed(1)} ${(c.y2 + dy).toFixed(1)} ${(c.x + dx).toFixed(1)} ${(c.y + dy).toFixed(1)}`;
    else if (c.type === "Q") d += `Q${(c.x1 + dx).toFixed(1)} ${(c.y1 + dy).toFixed(1)} ${(c.x + dx).toFixed(1)} ${(c.y + dy).toFixed(1)}`;
    else if (c.type === "Z") d += "Z";
  }
  console.log(`S bbox ${w.toFixed(1)}x${h.toFixed(1)}`);
  console.log(d);
  break;
}

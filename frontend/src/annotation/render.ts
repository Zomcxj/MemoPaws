// Annotation rendering core: drawMarks draws marks in original pixel coordinates on any 2D context;
// composePng uses the same renderer to compose "image + marks → selection crop → rounded transparency"
// into one PNG. Preview and export share this pipeline, guaranteeing what you see is what you export.
// Mosaic block-averages already-drawn pixels (not a DOM overlay), so earlier marks get pixelated too.
import type { Mark } from "./model";

export function drawMarks(ctx: CanvasRenderingContext2D, marks: Mark[]) {
  for (const mark of marks) {
    const a = mark.points[0];
    const b = mark.points[mark.points.length - 1];
    if (!a || !b) continue;
    ctx.save();
    ctx.strokeStyle = ctx.fillStyle = mark.color;
    ctx.lineWidth = mark.width;
    ctx.lineCap = ctx.lineJoin = "round";
    if (mark.tool === "text") {
      const size = Math.max(12, mark.width * 6);
      ctx.font = `${size}px sans-serif`;
      ctx.textBaseline = "top";
      (mark.text || "").split("\n").forEach((line, i) => ctx.fillText(line, a.x, a.y + i * size * 1.3));
    } else if (mark.tool === "mosaic") {
      const block = Math.max(4, Math.round(mark.width * 4));
      const left = Math.floor(Math.min(a.x, b.x));
      const top = Math.floor(Math.min(a.y, b.y));
      const right = Math.ceil(Math.max(a.x, b.x));
      const bottom = Math.ceil(Math.max(a.y, b.y));
      const transform = ctx.getTransform();
      for (let y = top; y < bottom; y += block) {
        for (let x = left; x < right; x += block) {
          const w = Math.min(block, right - x);
          const h = Math.min(block, bottom - y);
          // Mark coordinates → canvas device pixels: when the preview canvas has a scale transform, sampling still hits real pixels.
          const sx = Math.round(x * transform.a + transform.e);
          const sy = Math.round(y * transform.d + transform.f);
          const sw = Math.max(1, Math.round(w * transform.a));
          const sh = Math.max(1, Math.round(h * transform.d));
          const px = Math.max(0, sx);
          const py = Math.max(0, sy);
          const pw = Math.min(ctx.canvas.width, sx + sw) - px;
          const ph = Math.min(ctx.canvas.height, sy + sh) - py;
          if (pw <= 0 || ph <= 0) continue;
          const pixels = ctx.getImageData(px, py, pw, ph).data;
          const sum = [0, 0, 0, 0];
          for (let i = 0; i < pixels.length; i += 4) {
            for (let c = 0; c < 4; c++) sum[c] += pixels[i + c];
          }
          const n = pixels.length / 4;
          ctx.fillStyle = `rgba(${sum[0] / n},${sum[1] / n},${sum[2] / n},${sum[3] / n / 255})`;
          ctx.fillRect(x, y, w, h);
        }
      }
    } else if (mark.tool === "rectangle") {
      ctx.strokeRect(Math.min(a.x, b.x), Math.min(a.y, b.y), Math.abs(b.x - a.x), Math.abs(b.y - a.y));
    } else {
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      for (const p of mark.points.slice(1)) ctx.lineTo(p.x, p.y);
      ctx.stroke();
      if (mark.tool === "arrow") {
        const angle = Math.atan2(b.y - a.y, b.x - a.x);
        const len = Math.max(10, mark.width * 4);
        ctx.beginPath();
        ctx.moveTo(b.x, b.y);
        ctx.lineTo(b.x - len * Math.cos(angle - Math.PI / 6), b.y - len * Math.sin(angle - Math.PI / 6));
        ctx.moveTo(b.x, b.y);
        ctx.lineTo(b.x - len * Math.cos(angle + Math.PI / 6), b.y - len * Math.sin(angle + Math.PI / 6));
        ctx.stroke();
      }
    }
    ctx.restore();
  }
}

export async function composePng(
  image: HTMLImageElement,
  region: { x: number; y: number; width: number; height: number },
  scale: number,
  radius: number,
  marks: Mark[],
): Promise<Uint8Array> {
  const x = Math.max(0, Math.round(region.x * scale));
  const y = Math.max(0, Math.round(region.y * scale));
  const w = Math.min(Math.round(region.width * scale), image.naturalWidth - x);
  const h = Math.min(Math.round(region.height * scale), image.naturalHeight - y);
  if (w <= 0 || h <= 0) throw new Error("截图选区超出图片边界");
  // Marks are drawn on the full original image and then cropped: marks (and mosaic blocks) partially
  // outside the selection stay consistent with the export.
  const full = document.createElement("canvas");
  full.width = image.naturalWidth;
  full.height = image.naturalHeight;
  const source = full.getContext("2d");
  if (!source) throw new Error("无法创建标注画布");
  source.drawImage(image, 0, 0);
  drawMarks(source, marks);
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("无法创建截图画布");
  ctx.drawImage(full, x, y, w, h, 0, 0, w, h);
  const r = Math.max(0, Math.min(radius * scale, w / 2, h / 2));
  ctx.globalCompositeOperation = "destination-in";
  ctx.fillStyle = "#000";
  ctx.beginPath();
  ctx.moveTo(r, 0);
  ctx.arcTo(w, 0, w, h, r);
  ctx.arcTo(w, h, 0, h, r);
  ctx.arcTo(0, h, 0, 0, r);
  ctx.arcTo(0, 0, w, 0, r);
  ctx.closePath();
  ctx.fill();
  ctx.globalCompositeOperation = "source-over";
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/png"));
  if (!blob) throw new Error("无法生成截图 PNG 图片");
  return new Uint8Array(await blob.arrayBuffer());
}

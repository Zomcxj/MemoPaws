// Pixel-space model for screenshot annotations: mark points are always stored in original (screenshot)
// pixel coordinates, independent of CSS display scaling. This module must stay pure with zero
// React/Tauri dependencies; the browser flow annotationModelFlow self-checks it via a Vite module import.
export interface Point { x: number; y: number }
export type Tool = "move" | "arrow" | "rectangle" | "pen" | "text" | "mosaic";
export interface Mark {
  tool: Exclude<Tool, "move">;
  points: Point[];
  color: string;
  width: number;
  text?: string;
}
export interface History { past: Mark[][]; marks: Mark[]; future: Mark[][] }

export const emptyHistory = (): History => ({ past: [], marks: [], future: [] });

// color/width freeze with each mark: replaying old marks must never read the current toolbar state.
export function addMark(h: History, mark: Mark): History {
  return { past: [...h.past, h.marks], marks: [...h.marks, mark], future: [] };
}

export function undo(h: History): History {
  if (!h.past.length) return h;
  return { past: h.past.slice(0, -1), marks: h.past[h.past.length - 1], future: [h.marks, ...h.future] };
}

export function redo(h: History): History {
  if (!h.future.length) return h;
  return { past: [...h.past, h.marks], marks: h.future[0], future: h.future.slice(1) };
}

// Client coordinates → original image pixels; clamped to the image bounds.
export function imagePoint(
  client: Point,
  bounds: { offsetX: number; offsetY: number; scale: number; nw: number; nh: number },
): Point {
  return {
    x: Math.max(0, Math.min(bounds.nw, (client.x - bounds.offsetX) * bounds.scale)),
    y: Math.max(0, Math.min(bounds.nh, (client.y - bounds.offsetY) * bounds.scale)),
  };
}

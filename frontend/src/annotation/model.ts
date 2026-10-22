// 截图标注的像素空间模型：标注点始终存原图（截图）像素坐标，
// 与 CSS 显示缩放无关。此模块必须保持纯函数、零 React/Tauri 依赖，
// 浏览器流 annotationModelFlow 通过 Vite 模块导入直接自检。
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

// color/width 随标记定格：回放旧标注时不得读取当前工具栏状态。
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

// 客户端坐标 → 原图像素坐标；越界钳制到图片边界内。
export function imagePoint(
  client: Point,
  bounds: { offsetX: number; offsetY: number; scale: number; nw: number; nh: number },
): Point {
  return {
    x: Math.max(0, Math.min(bounds.nw, (client.x - bounds.offsetX) * bounds.scale)),
    y: Math.max(0, Math.min(bounds.nh, (client.y - bounds.offsetY) * bounds.scale)),
  };
}

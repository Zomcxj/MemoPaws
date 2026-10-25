import { useCallback, useEffect, useRef, useState, type MouseEvent as ReactMouseEvent, type PointerEvent as ReactPointerEvent } from "react";
import { type History, type Mark, type Tool, addMark, emptyHistory, imagePoint, redo, undo } from "../annotation/model";
import { drawMarks } from "../annotation/render";
import "./CaptureOverlay.css";

export interface RegionCss { x: number; y: number; width: number; height: number }

interface DragState { startX: number; startY: number; x: number; y: number; width: number; height: number }
type ResizeHandle = "n" | "ne" | "e" | "se" | "s" | "sw" | "w" | "nw";
interface SelectionEdit { kind: "move" | ResizeHandle; startX: number; startY: number; rect: DragState }
export interface CaptureLabels {
  recognize: string;
  translate: string;
  copyImage: string;
  saveImage: string;
  confirm: string;
  cancel: string;
  copied: string;
  colorHint: string;
  processing: string;
  panelTitle: string;
  resize: string;
  toolMove: string;
  toolArrow: string;
  toolRectangle: string;
  toolPen: string;
  toolText: string;
  toolMosaic: string;
  strokeColor: string;
  strokeWidth: string;
  undo: string;
  redo: string;
  textCommit: string;
  textCancel: string;
  localOcr: string;
  localOcrLanguage: string;
}

interface Props {
  background: string;
  hint: string;
  onConfirm: (result: { image: Uint8Array; ocrText: string; translation: string }) => Promise<void> | void;
  // Single composition entry: every action first obtains the "marked full PNG" through it, then dispatches.
  onCrop: (region: RegionCss, scale: number, cornerRadius: number, marks: Mark[]) => Promise<Uint8Array>;
  onCancel: () => void;
  onRecognize?: (image: Uint8Array) => Promise<string>;
  onTranslate?: (image: Uint8Array) => Promise<{ ocrText: string; translation: string }>;
  onLocalRecognize?: (image: Uint8Array) => Promise<string>;
  localLanguages?: { tag: string; name: string }[];
  localLanguage?: string;
  onLocalLanguageChange?: (tag: string) => void;
  onPinImage?: (image: Uint8Array, cornerRadius: number) => Promise<void> | void;
  onCopyImage?: (image: Uint8Array) => Promise<void> | void;
  onSaveImage?: (image: Uint8Array) => Promise<void> | void;
  // Visually hides the overlay (visibility:hidden) while keeping it mounted — restoreCaptureWindow
  // uses this so the app UI becomes the last composited frame before the window hides.
  visualHidden?: boolean;
  labels?: Partial<CaptureLabels>;
}

const MIN_SIZE = 8;
const MAGNIFIER_SIZE = 132;
const MAGNIFIER_ZOOM = 8;
const MAGNIFIER_OFFSET = 24;
const RESULT_WINDOW_MIN_WIDTH = 450;
const RESULT_WINDOW_MIN_HEIGHT = 533;
const RESULT_WINDOW_MAX_WIDTH = 900;
const RESULT_WINDOW_MAX_HEIGHT = 800;
const RESULT_WINDOW_GAP = 16;

const DEFAULT_LABELS: CaptureLabels = {
  recognize: "Recognize",
  translate: "Translate",
  copyImage: "Copy image",
  saveImage: "Save",
  confirm: "Confirm",
  cancel: "Cancel",
  copied: "Copied",
  colorHint: "Press C to copy HEX",
  processing: "Working…",
  panelTitle: "Result",
  resize: "Resize result window",
  toolMove: "Move",
  toolArrow: "Arrow",
  toolRectangle: "Rectangle",
  toolPen: "Pen",
  toolText: "Text",
  toolMosaic: "Mosaic",
  strokeColor: "Stroke color",
  strokeWidth: "Stroke width",
  undo: "Undo",
  redo: "Redo",
  textCommit: "Commit text",
  textCancel: "Discard text",
  localOcr: "Offline OCR",
  localOcrLanguage: "Offline OCR language",
};

const TOOLS: { name: Exclude<Tool, "move"> | "move"; labelKey: keyof CaptureLabels }[] = [
  { name: "move", labelKey: "toolMove" },
  { name: "arrow", labelKey: "toolArrow" },
  { name: "rectangle", labelKey: "toolRectangle" },
  { name: "pen", labelKey: "toolPen" },
  { name: "text", labelKey: "toolText" },
  { name: "mosaic", labelKey: "toolMosaic" },
];

const toHex = (r: number, g: number, b: number) =>
  `#${[r, g, b].map((value) => value.toString(16).padStart(2, "0")).join("")}`.toUpperCase();

export function CaptureOverlay({
  background,
  hint,
  onConfirm,
  onCrop,
  onCancel,
  onRecognize,
  onTranslate,
  onLocalRecognize,
  localLanguages,
  localLanguage,
  onLocalLanguageChange,
  onPinImage,
  onCopyImage,
  onSaveImage,
  visualHidden,
  labels,
}: Props) {
  const text = { ...DEFAULT_LABELS, ...labels };
  const imgRef = useRef<HTMLImageElement>(null);
  const startRef = useRef<{ x: number; y: number } | null>(null);
  const sampleRef = useRef<HTMLCanvasElement | null>(null);
  const magnifierRef = useRef<HTMLCanvasElement>(null);
  const [drag, setDrag] = useState<DragState | null>(null);
  const [cornerRadius, setCornerRadius] = useState(12);
  // Annotation state: tool/history/in-progress draft/color+width/text draft.
  // Marks in history are never mutated in place — undo/redo/addMark all return new objects.
  const [tool, setTool] = useState<Tool>("move");
  const [history, setHistory] = useState<History>(emptyHistory);
  const [draft, setDraft] = useState<Mark | null>(null);
  const draftRef = useRef<Mark | null>(null);
  const drawingRef = useRef(false);
  const [penColor, setPenColor] = useState("#ff6565");
  const [penWidth, setPenWidth] = useState(3);
  const [textDraft, setTextDraft] = useState<{ image: { x: number; y: number }; left: number; top: number; value: string } | null>(null);
  const [toolbarSize, setToolbarSize] = useState<{ width: number; height: number } | null>(null);
  const previewCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const [selection, setSelection] = useState<{ region: RegionCss; scale: number; rect: DragState } | null>(null);
  const [editing, setEditing] = useState(false);
  const editRef = useRef<SelectionEdit | null>(null);
  const [pointer, setPointer] = useState<{ x: number; y: number } | null>(null);
  const [color, setColor] = useState<{ hex: string; rgb: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const [ocrText, setOcrText] = useState("");
  const [translation, setTranslation] = useState("");
  const [busy, setBusy] = useState(false);
  const [resultError, setResultError] = useState("");
  const [resultWindow, setResultWindow] = useState<{ left: number; top: number; width: number; height: number } | null>(null);
  const [draggingResultWindow, setDraggingResultWindow] = useState<{ pointerId: number; x: number; y: number; left: number; top: number } | null>(null);
  const [resizingResultWindow, setResizingResultWindow] = useState<{ pointerId: number; x: number; y: number; width: number; height: number } | null>(null);
  const confirmSelectionRef = useRef<() => Promise<void>>(async () => {});
  const operationTokenRef = useRef(0);
  const cancelSelection = useCallback(() => { operationTokenRef.current += 1; onCancel(); }, [onCancel]);

  // Geometry shared by preview sampling and region math: the image is object-fit: contain.
  const layout = useCallback(() => {
    const img = imgRef.current;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const nw = img?.naturalWidth || 0;
    const nh = img?.naturalHeight || 0;
    if (nw <= 0 || nh <= 0) {
      return { nw: 0, nh: 0, offsetX: 0, offsetY: 0, renderedW: vw, renderedH: vh, scale: window.devicePixelRatio || 1 };
    }
    const cssScale = Math.min(vw / nw, vh / nh);
    const renderedW = nw * cssScale;
    const renderedH = nh * cssScale;
    return {
      nw,
      nh,
      offsetX: (vw - renderedW) / 2,
      offsetY: (vh - renderedH) / 2,
      renderedW,
      renderedH,
      scale: renderedW > 0 ? nw / renderedW : window.devicePixelRatio || 1,
    };
  }, []);

  const regionFrom = useCallback(
    (ax: number, ay: number, bx: number, by: number) => {
      const { offsetX, offsetY, renderedW, renderedH, scale } = layout();
      const left = Math.min(ax, bx) - offsetX;
      const top = Math.min(ay, by) - offsetY;
      const width = Math.abs(bx - ax);
      const height = Math.abs(by - ay);
      if (left >= renderedW || top >= renderedH || left + width <= 0 || top + height <= 0) return null;
      const x = Math.max(0, left);
      const y = Math.max(0, top);
       const right = Math.min(left + width, renderedW);
       const bottom = Math.min(top + height, renderedH);
       return {
         region: {
           x: Math.round(x),
           y: Math.round(y),
           width: Math.max(1, right - x),
           height: Math.max(1, bottom - y),
        },
        scale,
      };
    },
    [layout],
  );

  // Offscreen copy of the screenshot so we can read pixels for the loupe and picker.
  useEffect(() => {
    const image = new Image();
    image.src = background;
    image.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = image.naturalWidth;
      canvas.height = image.naturalHeight;
      canvas.getContext("2d")?.drawImage(image, 0, 0);
      sampleRef.current = canvas;
    };
  }, [background]);

  const sampleAt = useCallback(
    (clientX: number, clientY: number) => {
      const canvas = sampleRef.current;
      const { offsetX, offsetY, scale } = layout();
      if (!canvas) return null;
      const ix = Math.round((clientX - offsetX) * scale);
      const iy = Math.round((clientY - offsetY) * scale);
      if (ix < 0 || iy < 0 || ix >= canvas.width || iy >= canvas.height) return null;
      return { canvas, ix, iy };
    },
    [layout],
  );

  useEffect(() => {
    if (!pointer) return;
    const sample = sampleAt(pointer.x, pointer.y);
    const target = magnifierRef.current;
    if (!sample || !target) return;
    const context = target.getContext("2d");
    if (!context) return;
    const span = MAGNIFIER_SIZE / MAGNIFIER_ZOOM;
    context.imageSmoothingEnabled = false;
    context.clearRect(0, 0, MAGNIFIER_SIZE, MAGNIFIER_SIZE);
    context.drawImage(
      sample.canvas,
      sample.ix - span / 2,
      sample.iy - span / 2,
      span,
      span,
      0,
      0,
      MAGNIFIER_SIZE,
      MAGNIFIER_SIZE,
    );
    context.strokeStyle = "rgba(255,255,255,0.9)";
    context.lineWidth = 1;
    context.beginPath();
    context.moveTo(MAGNIFIER_SIZE / 2, 0);
    context.lineTo(MAGNIFIER_SIZE / 2, MAGNIFIER_SIZE);
    context.moveTo(0, MAGNIFIER_SIZE / 2);
    context.lineTo(MAGNIFIER_SIZE, MAGNIFIER_SIZE / 2);
    context.stroke();
    try {
      const pixel = sample.canvas.getContext("2d")?.getImageData(sample.ix, sample.iy, 1, 1).data;
      if (pixel) {
        setColor({ hex: toHex(pixel[0], pixel[1], pixel[2]), rgb: `${pixel[0]}, ${pixel[1]}, ${pixel[2]}` });
      }
    } catch {
      /* tainted canvas: keep the loupe without the readout */
    }
  }, [pointer, sampleAt]);

  useEffect(() => {
    const onMove = (event: MouseEvent) => setPointer({ x: event.clientX, y: event.clientY });
    window.addEventListener("mousemove", onMove);
    return () => window.removeEventListener("mousemove", onMove);
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      // While the text editor/color/width inputs are focused, shortcuts belong to the editor, not the
      // overlay; Enter/Esc during IME composition (isComposing) must not confirm or cancel either.
      if (event.isComposing) return;
      const target = event.target as HTMLElement | null;
      if (target && (target.isContentEditable || target.tagName === "INPUT" || target.tagName === "TEXTAREA")) return;
      if (event.key === "Escape") {
        cancelSelection();
        return;
      }
      if (event.key === "Enter" && selection) {
        event.preventDefault();
        void confirmSelectionRef.current();
        return;
      }
      if ((event.key === "c" || event.key === "C") && color) {
        void navigator.clipboard
          .writeText(color.hex)
          .then(() => {
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1200);
          })
          .catch(() => {});
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [cancelSelection, onConfirm, selection, color]);

  useEffect(() => {
    if (!drag && !editRef.current) return;
    const onMove = (event: MouseEvent) => {
      const edit = editRef.current;
      if (edit) {
        const bounds = layout();
        const minWidth = Math.min(MIN_SIZE, bounds.renderedW);
        const minHeight = Math.min(MIN_SIZE, bounds.renderedH);
        const original = edit.rect;
        let left = Math.min(original.startX, original.x);
        let top = Math.min(original.startY, original.y);
        let right = left + Math.abs(original.width);
        let bottom = top + Math.abs(original.height);
        const maxX = bounds.offsetX + bounds.renderedW;
        const maxY = bounds.offsetY + bounds.renderedH;
        if (edit.kind === "move") {
          const width = right - left;
          const height = bottom - top;
          left = Math.max(bounds.offsetX, Math.min(edit.rect.startX + event.clientX - edit.startX, maxX - width));
          top = Math.max(bounds.offsetY, Math.min(edit.rect.startY + event.clientY - edit.startY, maxY - height));
          right = left + width;
          bottom = top + height;
        } else {
          if (edit.kind.includes("w")) left = Math.max(bounds.offsetX, Math.min(event.clientX, right - minWidth));
          if (edit.kind.includes("e")) right = Math.min(maxX, Math.max(event.clientX, left + minWidth));
          if (edit.kind.includes("n")) top = Math.max(bounds.offsetY, Math.min(event.clientY, bottom - minHeight));
          if (edit.kind.includes("s")) bottom = Math.min(maxY, Math.max(event.clientY, top + minHeight));
        }
        const resolved = regionFrom(left, top, right, bottom);
        if (resolved) setSelection({ ...resolved, rect: { startX: left, startY: top, x: right, y: bottom, width: right - left, height: bottom - top } });
        return;
      }
      setDrag((current) =>
        current
          ? { ...current, x: event.clientX, y: event.clientY, width: event.clientX - current.startX, height: event.clientY - current.startY }
          : current,
      );
    };
    const onUp = (event: MouseEvent) => {
      if (editRef.current) {
        editRef.current = null;
        setEditing(false);
        return;
      }
      const start = startRef.current;
      setDrag(null);
      if (!start) return;
      if (Math.abs(event.clientX - start.x) < MIN_SIZE || Math.abs(event.clientY - start.y) < MIN_SIZE) {
        cancelSelection();
        return;
      }
      const resolved = regionFrom(start.x, start.y, event.clientX, event.clientY);
      if (!resolved) {
         cancelSelection();
        return;
      }
      const bounds = layout();
      const left = Math.max(bounds.offsetX, Math.min(start.x, event.clientX));
      const top = Math.max(bounds.offsetY, Math.min(start.y, event.clientY));
      const right = Math.min(bounds.offsetX + bounds.renderedW, Math.max(start.x, event.clientX));
      const bottom = Math.min(bounds.offsetY + bounds.renderedH, Math.max(start.y, event.clientY));
      // Keep the selection so the action bar can act on it.
      setSelection({
        ...resolved,
        rect: {
          startX: left,
          startY: top,
          x: right,
          y: bottom,
          width: right - left,
          height: bottom - top,
        },
      });
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [drag !== null, editing, layout, onCancel, regionFrom]);

  const beginSelectionEdit = (kind: SelectionEdit["kind"], event: ReactMouseEvent<HTMLDivElement | HTMLButtonElement>) => {
    // In drawing mode the selection is only a canvas: no move, no resize (handles render in move mode only).
    if (tool !== "move" || !selection || busy || event.button !== 0) return;
    event.preventDefault();
    event.stopPropagation();
    editRef.current = { kind, startX: event.clientX, startY: event.clientY, rect: selection.rect };
    setEditing(true);
  };

  const handleMouseDown = (event: ReactMouseEvent<HTMLDivElement>) => {
    // The mousedown right after a drawing press belongs to the same press and must not clear the selection.
    // busy does not block here: while actions are pending the user can still draw/new-select, which then
    // bumps the token and invalidates stale results.
    if (drawingRef.current) return;
    if (event.button !== 0) return;
      if ((event.target as HTMLElement).closest(".capture-result-window")) return;
    event.preventDefault();
    event.stopPropagation();
    operationTokenRef.current += 1;
    setSelection(null);
    setResultWindow(null);
    setOcrText("");
    setTranslation("");
    setResultError("");
    startRef.current = { x: event.clientX, y: event.clientY };
    setDrag({ startX: event.clientX, startY: event.clientY, x: event.clientX, y: event.clientY, width: 0, height: 0 });
  };

  // Drawing entry: starts a draft only when an annotation tool is active and the press lands inside the
  // selection. Presses outside are left to handleMouseDown — "choosing a new selection" keeps existing marks.
  const handlePointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    // busy does not block drawing: annotation continues while actions are pending, and drawing
    // invalidates stale pending results.
    if (tool === "move" || event.button !== 0) return;
    if ((event.target as HTMLElement).closest(".capture-overlay-toolbar, .capture-result-window, .capture-overlay-text-editor, input, button, .capture-overlay-rect-radius")) return;
    if (!selection) return;
    const rect = selection.rect;
    const left = Math.min(rect.startX, rect.x);
    const top = Math.min(rect.startY, rect.y);
    const right = Math.max(rect.startX, rect.x);
    const bottom = Math.max(rect.startY, rect.y);
    if (event.clientX < left || event.clientX > right || event.clientY < top || event.clientY > bottom) return;
    event.preventDefault();
    const bounds = layout();
    const point = imagePoint(
      { x: event.clientX, y: event.clientY },
      { offsetX: bounds.offsetX, offsetY: bounds.offsetY, scale: bounds.scale, nw: bounds.nw, nh: bounds.nh },
    );
    if (tool === "text") {
      // Text tool: no drag-to-draw; place a bounded editor (clamped to the viewport) at the anchor.
      const left = Math.min(Math.max(4, event.clientX), Math.max(4, window.innerWidth - 288));
      const top = Math.min(Math.max(4, event.clientY), Math.max(4, window.innerHeight - 160));
      setTextDraft({ image: point, left, top, value: "" });
      return;
    }
    event.currentTarget.setPointerCapture(event.pointerId);
    drawingRef.current = true;
    // Drawing is a new operation: invalidates delayed stale OCR results, but keeps mark history.
    operationTokenRef.current += 1;
    setOcrText("");
    setTranslation("");
    setResultError("");
    const mark: Mark = { tool: tool as Exclude<Tool, "move">, points: [point], color: penColor, width: penWidth };
    draftRef.current = mark;
    setDraft(mark);
  };

  // Window-level pointer listeners exist only while a draft exists: pen appends points, other tools
  // replace the endpoint.
  useEffect(() => {
    if (!draft) return;
    const onMove = (event: PointerEvent) => {
      const current = draftRef.current;
      if (!current) return;
      const bounds = layout();
      const point = imagePoint(
        { x: event.clientX, y: event.clientY },
        { offsetX: bounds.offsetX, offsetY: bounds.offsetY, scale: bounds.scale, nw: bounds.nw, nh: bounds.nh },
      );
      const next: Mark = current.tool === "pen"
        ? { ...current, points: [...current.points, point] }
        : { ...current, points: [current.points[0], point] };
      draftRef.current = next;
      setDraft(next);
    };
    const finish = (commit: boolean) => {
      const current = draftRef.current;
      draftRef.current = null;
      drawingRef.current = false;
      setDraft(null);
      if (current && commit) setHistory((h) => addMark(h, current));
    };
    const onUp = () => finish(true);
    const onCancel = () => finish(false);
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onCancel);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onCancel);
    };
  }, [draft !== null, layout]);

  const active = drag ?? selection?.rect ?? null;
  const rectStyle = active
    ? {
        left: Math.min(active.startX, active.x),
        top: Math.min(active.startY, active.y),
        width: Math.abs(active.width),
        height: Math.abs(active.height),
      }
    : null;

  const { scale: displayScale, offsetX, offsetY, renderedW, renderedH } = layout();
  const info = active
    ? (() => {
        const resolved = regionFrom(active.startX, active.startY, active.x, active.y);
        if (!resolved) return null;
        return resolved.region;
      })()
    : null;

  // Flip the size tag below the selection when it would clip the viewport top.
  const tagBelow = rectStyle ? rectStyle.top < 28 : false;

  const magnifierStyle = (() => {
    if (!pointer) return undefined;
    const flipX = pointer.x + MAGNIFIER_OFFSET + MAGNIFIER_SIZE > window.innerWidth;
    const flipY = pointer.y + MAGNIFIER_OFFSET + MAGNIFIER_SIZE + 34 > window.innerHeight;
    return {
      left: flipX ? pointer.x - MAGNIFIER_OFFSET - MAGNIFIER_SIZE : pointer.x + MAGNIFIER_OFFSET,
      top: flipY ? pointer.y - MAGNIFIER_OFFSET - MAGNIFIER_SIZE - 34 : pointer.y + MAGNIFIER_OFFSET,
    };
  })();

  const defaultResultWindow = (() => {
    if (!rectStyle) return undefined;
    const left = rectStyle.left + rectStyle.width + RESULT_WINDOW_GAP + RESULT_WINDOW_MIN_WIDTH <= window.innerWidth
      ? rectStyle.left + rectStyle.width + RESULT_WINDOW_GAP
      : Math.max(0, rectStyle.left - RESULT_WINDOW_GAP - RESULT_WINDOW_MIN_WIDTH);
    return {
      left: Math.min(left, Math.max(0, window.innerWidth - RESULT_WINDOW_MIN_WIDTH)),
      top: Math.max(0, Math.min(rectStyle.top, window.innerHeight - RESULT_WINDOW_MIN_HEIGHT)),
      width: RESULT_WINDOW_MIN_WIDTH,
      height: RESULT_WINDOW_MIN_HEIGHT,
    };
  })();

  const clampResultWindow = (next: { left: number; top: number; width: number; height: number }) => {
    const width = Math.min(RESULT_WINDOW_MAX_WIDTH, Math.max(RESULT_WINDOW_MIN_WIDTH, Math.min(next.width, window.innerWidth)));
    const height = Math.min(RESULT_WINDOW_MAX_HEIGHT, Math.max(RESULT_WINDOW_MIN_HEIGHT, Math.min(next.height, window.innerHeight)));
    return {
      left: Math.max(0, Math.min(next.left, window.innerWidth - width)),
      top: Math.max(0, Math.min(next.top, window.innerHeight - height)),
      width,
      height,
    };
  };

  // The image seam shared by all actions: same selection, same marks → same PNG.
  const imageForSelection = () => {
    if (!selection) throw new Error("没有截图选区");
    return onCrop(selection.region, selection.scale, cornerRadius, history.marks);
  };

  const confirmSelection = async () => {
    if (!selection || busy) return;
    const operationToken = ++operationTokenRef.current;
    setBusy(true);
    setResultError("");
    try {
      const image = await imageForSelection();
      if (operationTokenRef.current === operationToken) await onConfirm({ image, ocrText, translation });
    } catch (reason) {
      setResultError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  };
  confirmSelectionRef.current = confirmSelection;

  const runRecognize = async () => {
    if (!selection || !onRecognize || busy) return;
    const operationToken = ++operationTokenRef.current;
    if (!resultWindow && defaultResultWindow) setResultWindow(defaultResultWindow);
    setBusy(true); setResultError("");
    try {
      const image = await imageForSelection();
      const result = await onRecognize(image);
      if (operationTokenRef.current === operationToken) setOcrText(result);
    }
    catch (reason) { setResultError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  };

  const runTranslate = async () => {
    if (!selection || !onTranslate || busy) return;
    const operationToken = ++operationTokenRef.current;
    if (!resultWindow && defaultResultWindow) setResultWindow(defaultResultWindow);
    setBusy(true); setResultError("");
    try {
      const image = await imageForSelection();
      const result = await onTranslate(image);
      if (operationTokenRef.current === operationToken) {
        setOcrText(result.ocrText); setTranslation(result.translation);
      }
    } catch (reason) { setResultError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  };

  // Offline OCR: same composited image, same operation token; the button stays disabled until the
  // language is ready. Failures report errors only and never fall back to AI recognize/translate.
  const runLocalRecognize = async () => {
    if (!selection || !onLocalRecognize || busy || !localLanguage) return;
    const operationToken = ++operationTokenRef.current;
    if (!resultWindow && defaultResultWindow) setResultWindow(defaultResultWindow);
    setBusy(true); setResultError("");
    try {
      const image = await imageForSelection();
      const result = await onLocalRecognize(image);
      if (operationTokenRef.current === operationToken) setOcrText(result);
    } catch (reason) { setResultError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  };

  const localLanguagePicker = (onLocalRecognize && localLanguages && localLanguages.length > 0 && (
    <select
      className="capture-overlay-local-language"
      aria-label={text.localOcrLanguage}
      value={localLanguage}
      onMouseDown={(event) => event.stopPropagation()}
      onChange={(event) => onLocalLanguageChange?.(event.target.value)}
    >
      {localLanguages.map((item) => <option key={item.tag} value={item.tag}>{item.name}</option>)}
    </select>
  )) || null;

  // Preview canvas: backing store = original image pixels, CSS size = the contain layout rectangle.
  // Shares drawMarks with the exporter (preview is what you export); rAF coalesces same-frame invalidations.
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      const canvas = previewCanvasRef.current;
      const img = imgRef.current;
      if (!canvas || !img || !img.naturalWidth) return;
      if (canvas.width !== img.naturalWidth || canvas.height !== img.naturalHeight) {
        canvas.width = img.naturalWidth;
        canvas.height = img.naturalHeight;
      }
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0);
      drawMarks(ctx, history.marks);
      if (draft) drawMarks(ctx, [draft]);
    });
    return () => cancelAnimationFrame(frame);
  }, [background, history.marks, draft]);

  // The two-row toolbar's real size is unknown up front: measure it, then clamp the left edge and flip
  // above the selection when near the bottom.
  const toolbarRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const node = toolbarRef.current;
    if (!node) return;
    const measure = () => setToolbarSize({ width: node.offsetWidth, height: node.offsetHeight });
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, [selection, resultWindow]);

  const commitTextDraft = () => {
    const current = textDraft;
    if (!current || !current.value.trim()) return;
    setHistory((h) => addMark(h, { tool: "text", points: [current.image], color: penColor, width: penWidth, text: current.value }));
    setTextDraft(null);
  };

  const toolbarStyle = rectStyle
    ? (() => {
        const width = toolbarSize?.width ?? 420;
        const height = toolbarSize?.height ?? 88;
        const left = Math.min(Math.max(4, rectStyle.left), Math.max(4, window.innerWidth - width - 4));
        const below = rectStyle.top + rectStyle.height + 8;
        const top = below + height > window.innerHeight ? Math.max(4, rectStyle.top - height - 8) : below;
        return { left, top };
      })()
    : undefined;

  const resultWindowStyle = resultWindow ? {
    left: resultWindow.left,
    top: resultWindow.top,
    width: resultWindow.width,
    height: resultWindow.height,
  } : undefined;

  const beginResultWindowDrag = (event: React.PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0 || !resultWindow) return;
    event.preventDefault(); event.stopPropagation(); event.currentTarget.setPointerCapture(event.pointerId);
    setDraggingResultWindow({ pointerId: event.pointerId, x: event.clientX, y: event.clientY, left: resultWindow.left, top: resultWindow.top });
  };
  const moveResultWindow = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!draggingResultWindow || draggingResultWindow.pointerId !== event.pointerId) return;
    setResultWindow(clampResultWindow({ ...resultWindow!, left: draggingResultWindow.left + event.clientX - draggingResultWindow.x, top: draggingResultWindow.top + event.clientY - draggingResultWindow.y }));
  };
  const endResultWindowDrag = (event: React.PointerEvent<HTMLDivElement>) => {
    if (draggingResultWindow?.pointerId === event.pointerId) setDraggingResultWindow(null);
  };
  const beginResultWindowResize = (event: React.PointerEvent<HTMLButtonElement>) => {
    if (event.button !== 0 || !resultWindow) return;
    event.preventDefault(); event.stopPropagation(); event.currentTarget.setPointerCapture(event.pointerId);
    setResizingResultWindow({ pointerId: event.pointerId, x: event.clientX, y: event.clientY, width: resultWindow.width, height: resultWindow.height });
  };
  const resizeResultWindow = (event: React.PointerEvent<HTMLButtonElement>) => {
    if (!resizingResultWindow || resizingResultWindow.pointerId !== event.pointerId) return;
    setResultWindow(clampResultWindow({ ...resultWindow!, width: resizingResultWindow.width + event.clientX - resizingResultWindow.x, height: resizingResultWindow.height + event.clientY - resizingResultWindow.y }));
  };
  const endResultWindowResize = (event: React.PointerEvent<HTMLButtonElement>) => {
    if (resizingResultWindow?.pointerId === event.pointerId) setResizingResultWindow(null);
  };

  const act = (handler?: (image: Uint8Array, cornerRadius: number) => Promise<void> | void) => async () => {
    if (!selection || !handler || busy) return;
    setBusy(true);
    setResultError("");
    try {
      const image = await imageForSelection();
      await handler(image, cornerRadius);
    } catch (reason) {
      setResultError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={`capture-overlay${visualHidden ? " is-hidden" : ""}`} role="dialog" aria-modal="true" onMouseDown={handleMouseDown} onPointerDown={handlePointerDown}>
      <img ref={imgRef} src={background} alt="" draggable={false} />
      <canvas
        ref={previewCanvasRef}
        className="capture-overlay-annotations"
        style={{ left: offsetX, top: offsetY, width: renderedW, height: renderedH }}
        aria-hidden="true"
      />
      <div className="capture-overlay-hint">{hint}</div>

      {pointer && !draft && !textDraft && (
        <div className="capture-overlay-magnifier" style={magnifierStyle} aria-hidden="true">
          <canvas ref={magnifierRef} width={MAGNIFIER_SIZE} height={MAGNIFIER_SIZE} />
          {color && (
            <div className="capture-overlay-color">
              <span className="capture-overlay-swatch" style={{ background: color.hex }} />
              <span>{color.hex}</span>
              <span className="capture-overlay-rgb">{color.rgb}</span>
            </div>
          )}
        </div>
      )}

      <div className="capture-overlay-live" aria-live="polite">
        {busy ? text.processing : copied ? text.copied : color ? `${color.hex} — ${text.colorHint}` : ""}
      </div>

      {selection && resultWindow && (
        <aside className={`capture-result-window${busy ? " is-running" : ""}`} style={resultWindowStyle} onMouseDown={(event) => event.stopPropagation()}>
          <div className="capture-result-window-title" onPointerDown={beginResultWindowDrag} onPointerMove={moveResultWindow} onPointerUp={endResultWindowDrag}>
            <span>{text.panelTitle}</span><span>{busy ? text.processing : ""}</span>
          </div>
          <section className="capture-result-section"><h3>{text.recognize}</h3><textarea aria-label={text.recognize} value={ocrText} readOnly /></section>
          <section className="capture-result-section"><h3>{text.translate}</h3><textarea aria-label={text.translate} value={translation} readOnly /></section>
          {resultError && <div className="capture-result-error" role="alert">{resultError}</div>}
          <div className="capture-result-actions">
            {onRecognize && <button className="capture-overlay-action capture-overlay-action--label" type="button" aria-label={text.recognize} onClick={() => void runRecognize()} disabled={busy}>{text.recognize}</button>}
            {onTranslate && <button className="capture-overlay-action capture-overlay-action--label" type="button" aria-label={text.translate} onClick={() => void runTranslate()} disabled={busy}>{text.translate}</button>}
            {onLocalRecognize && <button className="capture-overlay-action capture-overlay-action--label" type="button" aria-label={text.localOcr} onClick={() => void runLocalRecognize()} disabled={busy || !localLanguages?.length}>{text.localOcr}</button>}
            {localLanguagePicker}
            {onCopyImage && <button className="capture-overlay-action capture-overlay-action--label" type="button" aria-label={text.copyImage} onClick={act(onCopyImage)} disabled={busy}>{text.copyImage}</button>}
            {onSaveImage && <button className="capture-overlay-action capture-overlay-action--label" type="button" aria-label={text.saveImage} onClick={act(onSaveImage)} disabled={busy}>{text.saveImage}</button>}
             {onPinImage && <button className="capture-overlay-action capture-overlay-action--label" type="button" aria-label="Pin image" onClick={act(onPinImage)} disabled={busy}>钉图</button>}
            <button className="capture-overlay-action is-primary" type="button" aria-label={text.confirm} onClick={() => void confirmSelection()} disabled={busy}>✓</button>
           <button className="capture-overlay-action" type="button" aria-label={text.cancel} onClick={cancelSelection} disabled={busy}>×</button>
          </div>
          <button className="capture-result-window-resize" type="button" aria-label={text.resize} onPointerDown={beginResultWindowResize} onPointerMove={resizeResultWindow} onPointerUp={endResultWindowResize} />
        </aside>
      )}

      {selection && !resultWindow && (
        <div className="capture-overlay-toolbar" style={toolbarStyle} ref={toolbarRef} onMouseDown={(event) => event.stopPropagation()}>
          <div className="capture-overlay-tools" role="toolbar" aria-label={text.panelTitle}>
            {TOOLS.map(({ name, labelKey }) => (
              <button
                key={name}
                type="button"
                className={`capture-overlay-tool${tool === name ? " is-active" : ""}`}
                aria-pressed={tool === name}
                onMouseDown={(event) => event.stopPropagation()}
                onClick={() => setTool(name)}
              >
                {text[labelKey]}
              </button>
            ))}
            <input type="color" className="capture-overlay-tool-color" aria-label={text.strokeColor} value={penColor} onChange={(event) => setPenColor(event.target.value)} />
            <input type="range" className="capture-overlay-tool-width" aria-label={text.strokeWidth} min={1} max={20} value={penWidth} onChange={(event) => setPenWidth(Number(event.target.value))} />
            <button type="button" className="capture-overlay-tool" aria-label={text.undo} disabled={!history.past.length} onMouseDown={(event) => event.stopPropagation()} onClick={() => setHistory((h) => undo(h))}>{text.undo}</button>
            <button type="button" className="capture-overlay-tool" aria-label={text.redo} disabled={!history.future.length} onMouseDown={(event) => event.stopPropagation()} onClick={() => setHistory((h) => redo(h))}>{text.redo}</button>
          </div>
          <div className="capture-overlay-actions">
            {onRecognize && <button className="capture-overlay-action capture-overlay-action--label" type="button" aria-label={text.recognize} onClick={() => void runRecognize()} disabled={busy}>{text.recognize}</button>}
            {onTranslate && <button className="capture-overlay-action capture-overlay-action--label" type="button" aria-label={text.translate} onClick={() => void runTranslate()} disabled={busy}>{text.translate}</button>}
            {onLocalRecognize && <button className="capture-overlay-action capture-overlay-action--label" type="button" aria-label={text.localOcr} onClick={() => void runLocalRecognize()} disabled={busy || !localLanguages?.length}>{text.localOcr}</button>}
            {localLanguagePicker}
            {onCopyImage && <button className="capture-overlay-action capture-overlay-action--label" type="button" aria-label={text.copyImage} onClick={act(onCopyImage)} disabled={busy}>{text.copyImage}</button>}
            {onSaveImage && <button className="capture-overlay-action capture-overlay-action--label" type="button" aria-label={text.saveImage} onClick={act(onSaveImage)} disabled={busy}>{text.saveImage}</button>}
             {onPinImage && <button className="capture-overlay-action capture-overlay-action--label" type="button" aria-label="Pin image" onClick={act(onPinImage)} disabled={busy}>钉图</button>}
            <button className="capture-overlay-action is-primary" type="button" aria-label={text.confirm} onClick={() => void confirmSelection()} disabled={busy}>✓</button>
              <button className="capture-overlay-action" type="button" aria-label={text.cancel} onClick={cancelSelection} disabled={busy}>×</button>
             {resultError && <div className="capture-result-error" role="alert">{resultError}</div>}
           </div>
        </div>
      )}

      {textDraft && (
        <div className="capture-overlay-text-editor" style={{ left: textDraft.left, top: textDraft.top }} onMouseDown={(event) => event.stopPropagation()} onPointerDown={(event) => event.stopPropagation()}>
          <textarea
            autoFocus
            aria-label={text.toolText}
            value={textDraft.value}
            style={{ fontSize: Math.max(12, penWidth * 6), lineHeight: 1.3 }}
            onChange={(event) => setTextDraft({ ...textDraft, value: event.target.value })}
            onKeyDown={(event) => {
              // Keys during IME composition belong to the IME: Enter/Esc must not commit or discard.
              if (event.nativeEvent.isComposing) return;
              if (event.key === "Escape") {
                event.preventDefault();
                event.stopPropagation();
                setTextDraft(null);
              } else if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
                event.preventDefault();
                commitTextDraft();
              }
            }}
          />
          <div className="capture-overlay-text-editor-actions">
            <button type="button" className="capture-overlay-action" onClick={commitTextDraft} disabled={!textDraft.value.trim()}>{text.textCommit}</button>
            <button type="button" className="capture-overlay-action" onClick={() => setTextDraft(null)}>{text.textCancel}</button>
          </div>
        </div>
      )}

      {rectStyle && Math.abs(active!.width) >= MIN_SIZE && Math.abs(active!.height) >= MIN_SIZE && (
        <>
          <div className="capture-overlay-rect" style={{ ...rectStyle, borderRadius: cornerRadius }} onMouseDown={(event) => beginSelectionEdit("move", event)}>
            <div className="capture-overlay-rect-radius" onMouseDown={(e) => e.stopPropagation()}>
              <input type="range" min={0} max={40} value={cornerRadius} onChange={(e) => setCornerRadius(Number(e.target.value))} title="圆角" />
            </div>
            {tool === "move" && selection && (["n", "ne", "e", "se", "s", "sw", "w", "nw"] as ResizeHandle[]).map((handle) => (
              <button
                key={handle}
                type="button"
                className={`capture-overlay-handle capture-overlay-handle--${handle}`}
                aria-label={`Resize ${handle}`}
                onMouseDown={(event) => beginSelectionEdit(handle, event)}
              />
            ))}
          </div>
          <div
            className={`capture-overlay-size${tagBelow ? " is-below" : ""}`}
            style={{ left: rectStyle.left, top: tagBelow ? rectStyle.top + rectStyle.height : rectStyle.top }}
          >
            {info
              ? `${info.x}, ${info.y} · ${Math.round(info.width * displayScale)} × ${Math.round(info.height * displayScale)}`
              : `${Math.round(Math.abs(active!.width) * displayScale)} × ${Math.round(Math.abs(active!.height) * displayScale)}`}
          </div>
        </>
      )}

    </div>
  );
}

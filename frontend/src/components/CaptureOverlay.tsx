import { useCallback, useEffect, useRef, useState, type MouseEvent as ReactMouseEvent } from "react";
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
}

interface Props {
  background: string;
  hint: string;
  onConfirm: (result: { image: Uint8Array; ocrText: string; translation: string }) => Promise<void> | void;
  onCrop: (region: RegionCss, scale: number) => Promise<Uint8Array>;
  onCancel: () => void;
  onRecognize?: (region: RegionCss, scale: number) => Promise<string>;
  onTranslate?: (region: RegionCss, scale: number) => Promise<{ ocrText: string; translation: string }>;
  onCopyImage?: (region: RegionCss, scale: number) => void;
  onSaveImage?: (region: RegionCss, scale: number) => void;
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
};

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
  onCopyImage,
  onSaveImage,
  labels,
}: Props) {
  const text = { ...DEFAULT_LABELS, ...labels };
  const imgRef = useRef<HTMLImageElement>(null);
  const startRef = useRef<{ x: number; y: number } | null>(null);
  const sampleRef = useRef<HTMLCanvasElement | null>(null);
  const magnifierRef = useRef<HTMLCanvasElement>(null);
  const [drag, setDrag] = useState<DragState | null>(null);
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
    if (!selection || busy || event.button !== 0) return;
    event.preventDefault();
    event.stopPropagation();
    editRef.current = { kind, startX: event.clientX, startY: event.clientY, rect: selection.rect };
    setEditing(true);
  };

  const handleMouseDown = (event: ReactMouseEvent<HTMLDivElement>) => {
    if (busy) return;
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

  const active = drag ?? selection?.rect ?? null;
  const rectStyle = active
    ? {
        left: Math.min(active.startX, active.x),
        top: Math.min(active.startY, active.y),
        width: Math.abs(active.width),
        height: Math.abs(active.height),
      }
    : null;

  const { scale: displayScale } = layout();
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

  const confirmSelection = async () => {
    if (!selection || busy) return;
    const operationToken = ++operationTokenRef.current;
    setBusy(true);
    setResultError("");
    try {
      const image = await onCrop(selection.region, selection.scale);
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
      const result = await onRecognize(selection.region, selection.scale);
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
      const result = await onTranslate(selection.region, selection.scale);
      if (operationTokenRef.current === operationToken) {
        setOcrText(result.ocrText); setTranslation(result.translation);
      }
    } catch (reason) { setResultError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  };

  const resultWindowStyle = resultWindow ? {
    left: resultWindow.left,
    top: resultWindow.top,
    width: resultWindow.width,
    height: resultWindow.height,
  } : undefined;

  const actionStyle = rectStyle ? {
    left: Math.min(Math.max(4, rectStyle.left), Math.max(4, window.innerWidth - 216)),
    top: rectStyle.top + rectStyle.height + 36 > window.innerHeight
      ? Math.max(4, rectStyle.top - 36)
      : rectStyle.top + rectStyle.height + 8,
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

  const act = (handler?: (region: RegionCss, scale: number) => void) => () => {
    if (!selection || !handler) return;
    handler(selection.region, selection.scale);
  };

  return (
    <div className="capture-overlay" role="dialog" aria-modal="true" onMouseDown={handleMouseDown}>
      <img ref={imgRef} src={background} alt="" draggable={false} />
      <div className="capture-overlay-hint">{hint}</div>

      {pointer && (
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
            {onRecognize && <button className="capture-overlay-action" type="button" aria-label={text.recognize} onClick={() => void runRecognize()} disabled={busy}>R</button>}
            {onTranslate && <button className="capture-overlay-action" type="button" aria-label={text.translate} onClick={() => void runTranslate()} disabled={busy}>T</button>}
            {onCopyImage && <button className="capture-overlay-action" type="button" aria-label={text.copyImage} onClick={act(onCopyImage)} disabled={busy}>C</button>}
            {onSaveImage && <button className="capture-overlay-action" type="button" aria-label={text.saveImage} onClick={act(onSaveImage)} disabled={busy}>S</button>}
            <button className="capture-overlay-action is-primary" type="button" aria-label={text.confirm} onClick={() => void confirmSelection()} disabled={busy}>✓</button>
           <button className="capture-overlay-action" type="button" aria-label={text.cancel} onClick={cancelSelection} disabled={busy}>×</button>
          </div>
          <button className="capture-result-window-resize" type="button" aria-label={text.resize} onPointerDown={beginResultWindowResize} onPointerMove={resizeResultWindow} onPointerUp={endResultWindowResize} />
        </aside>
      )}

      {selection && !resultWindow && (
        <div className="capture-overlay-actions" style={actionStyle} onMouseDown={(event) => event.stopPropagation()}>
          {onRecognize && <button className="capture-overlay-action" type="button" aria-label={text.recognize} onClick={() => void runRecognize()} disabled={busy}>R</button>}
          {onTranslate && <button className="capture-overlay-action" type="button" aria-label={text.translate} onClick={() => void runTranslate()} disabled={busy}>T</button>}
          {onCopyImage && <button className="capture-overlay-action" type="button" aria-label={text.copyImage} onClick={act(onCopyImage)} disabled={busy}>C</button>}
          {onSaveImage && <button className="capture-overlay-action" type="button" aria-label={text.saveImage} onClick={act(onSaveImage)} disabled={busy}>S</button>}
          <button className="capture-overlay-action is-primary" type="button" aria-label={text.confirm} onClick={() => void confirmSelection()} disabled={busy}>✓</button>
           <button className="capture-overlay-action" type="button" aria-label={text.cancel} onClick={cancelSelection} disabled={busy}>×</button>
        </div>
      )}

      {rectStyle && Math.abs(active!.width) >= MIN_SIZE && Math.abs(active!.height) >= MIN_SIZE && (
        <>
          <div className="capture-overlay-rect" style={rectStyle} onMouseDown={(event) => beginSelectionEdit("move", event)}>
            {selection && (["n", "ne", "e", "se", "s", "sw", "w", "nw"] as ResizeHandle[]).map((handle) => (
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

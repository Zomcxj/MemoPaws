import { useLayoutEffect, useRef, useState } from "react";
import "./SegmentedControl.css";

interface Props {
  value: string;
  options: [string, string][];
  onChange: (value: string) => void;
  ariaLabel?: string;
  className?: string;
  disabled?: boolean;
}

export function SegmentedControl({
  value,
  options,
  onChange,
  ariaLabel,
  className = "",
  disabled = false,
}: Props) {
  const rootRef = useRef<HTMLDivElement>(null);
  const firstPaint = useRef(true);
  const [indicator, setIndicator] = useState({ left: 0, width: 0, ready: false, animate: false });

  useLayoutEffect(() => {
    const root = rootRef.current;
    if (!root) return;

    const measure = (animate: boolean) => {
      const buttons = Array.from(root.querySelectorAll<HTMLButtonElement>("button[data-seg]"));
      const active = buttons.find((button) => button.dataset.value === value) ?? buttons[0];
      if (!active) return;
      const left = active.offsetLeft;
      const width = active.offsetWidth;
      if (width <= 0) return;
      setIndicator({ left, width, ready: true, animate });
    };

    const shouldAnimate = !firstPaint.current;
    firstPaint.current = false;
    measure(shouldAnimate);

    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(() => measure(false)) : null;
    ro?.observe(root);
    void document.fonts?.ready?.then(() => measure(false));

    return () => ro?.disconnect();
  }, [value, options]);

  return (
    <div
      ref={rootRef}
      className={`seg-control ${className}`.trim()}
      role="group"
      aria-label={ariaLabel}
    >
      <span
        className={`seg-indicator${indicator.ready ? " is-ready" : ""}${indicator.animate ? " is-animate" : ""}`}
        style={{
          transform: `translate3d(${Math.round(indicator.left)}px,0,0)`,
          width: Math.round(indicator.width),
        }}
        aria-hidden="true"
      />
      {options.map(([key, label]) => (
        <button
          type="button"
          key={key}
          data-seg=""
          data-value={key}
          aria-pressed={value === key}
          className={value === key ? "active" : ""}
          disabled={disabled}
          onClick={() => onChange(key)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

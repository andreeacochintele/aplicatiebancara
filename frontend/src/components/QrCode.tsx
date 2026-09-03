import { useMemo } from "react";

import { encodeQr } from "../features/payments/qr";

/** Modules of light margin around the symbol. The specification requires four;
 *  scanners are unreliable without it, however clean the symbol itself is. */
const QUIET_ZONE = 4;

interface QrCodeProps {
  /** The text the scanner should read back. */
  value: string;
  /** Accessible name, since the symbol carries meaning. */
  label: string;
  className?: string;
}

/**
 * Renders `value` as a scannable QR symbol, drawn as one SVG path so it stays
 * crisp at any size and costs a single node rather than one per module.
 *
 * Deliberately fixed to dark modules on a white ground in both themes: an
 * inverted symbol is off-specification and many phone cameras refuse it, so
 * this is one of the few places that must not follow the theme.
 */
export function QrCode({ value, label, className }: QrCodeProps) {
  const symbol = useMemo(() => {
    try {
      const matrix = encodeQr(value);
      const dimension = matrix.length + QUIET_ZONE * 2;
      // One path, one subpath per dark module.
      const path = matrix
        .flatMap((row, r) =>
          row.map((dark, c) => (dark ? `M${c + QUIET_ZONE} ${r + QUIET_ZONE}h1v1h-1z` : "")),
        )
        .join("");
      return { dimension, path };
    } catch {
      // A payload too long for version 10 must not take the page down with it.
      return null;
    }
  }, [value]);

  if (symbol === null) return null;

  return (
    <svg
      className={className}
      viewBox={`0 0 ${symbol.dimension} ${symbol.dimension}`}
      role="img"
      aria-label={label}
      shapeRendering="crispEdges"
    >
      <rect width={symbol.dimension} height={symbol.dimension} fill="#ffffff" />
      <path d={symbol.path} fill="#000000" />
    </svg>
  );
}

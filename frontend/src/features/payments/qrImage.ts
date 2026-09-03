import { encodeQr } from "./qr";

/** Matches the quiet zone <QrCode> draws, so a saved file scans as reliably
 *  as the one on screen. */
const QUIET_ZONE = 4;

/** Pixels per module. Eight keeps a request-id symbol around 300px square:
 *  large enough to survive a messaging app's recompression, small enough to
 *  stay a sub-10KB attachment. */
const MODULE_PIXELS = 8;

/**
 * Renders `value` as a PNG and hands it to the browser's save dialog.
 *
 * A canvas rather than a serialised copy of the on-screen SVG: the symbol is
 * cheap to redraw from the matrix, and going through the DOM would inherit
 * whatever the page's stylesheet had done to it - the one thing a QR must not
 * pick up.
 *
 * Silently does nothing if the payload cannot be encoded or the canvas is
 * unavailable; a failed download must not take the payments page with it.
 */
export function downloadQrPng(value: string, filename: string): void {
  let matrix;
  try {
    matrix = encodeQr(value);
  } catch {
    return;
  }

  const dimension = (matrix.length + QUIET_ZONE * 2) * MODULE_PIXELS;
  const canvas = document.createElement("canvas");
  canvas.width = dimension;
  canvas.height = dimension;
  const context = canvas.getContext("2d");
  if (context === null) return;

  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, dimension, dimension);
  context.fillStyle = "#000000";
  matrix.forEach((row, r) => {
    row.forEach((dark, c) => {
      if (!dark) return;
      context.fillRect(
        (c + QUIET_ZONE) * MODULE_PIXELS,
        (r + QUIET_ZONE) * MODULE_PIXELS,
        MODULE_PIXELS,
        MODULE_PIXELS,
      );
    });
  });

  canvas.toBlob((blob) => {
    if (blob === null) return;
    // Same throwaway-object-URL dance as utils/downloadBlob, which serves the
    // server-streamed exports.
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(objectUrl);
  }, "image/png");
}

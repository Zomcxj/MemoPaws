import jsQR from "jsqr";

// Decodes the first QR code found in a PNG/JPEG byte buffer; null when the
// image carries no readable code.
export async function decodeQrImage(bytes: Uint8Array): Promise<string | null> {
  const bitmap = await createImageBitmap(new Blob([bytes.slice()], { type: "image/png" }));
  const canvas = document.createElement("canvas");
  canvas.width = bitmap.width;
  canvas.height = bitmap.height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  ctx.drawImage(bitmap, 0, 0);
  bitmap.close();
  const result = jsQR(ctx.getImageData(0, 0, canvas.width, canvas.height).data, canvas.width, canvas.height);
  return result ? result.data : null;
}

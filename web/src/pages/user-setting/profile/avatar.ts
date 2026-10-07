import { avatarDataUrl } from "@/components/avatar-initials";

/** The stored avatar is a 256 by 256 raster the app itself encoded, at most 256 KB decoded (D-29, mirrored by the server). */
export const AVATAR_SIZE = 256;
export const AVATAR_MAX_BYTES = 256 * 1024;

/** Refuse to even decode files far beyond any real avatar (decompression bombs, accidental huge photos). */
const MAX_INPUT_BYTES = 25 * 1024 * 1024;
const MAX_SOURCE_PIXELS = 100_000_000;
const JPEG_QUALITIES = [0.92, 0.85, 0.75, 0.6, 0.45] as const;

export type AvatarErrorKey = "errors.avatar.type" | "errors.avatar.decode" | "errors.avatar.size";

/** A rejection the page shows inline. `key` is an i18n key; the message never echoes file content. */
export class AvatarError extends Error {
  readonly key: AvatarErrorKey;

  constructor(key: AvatarErrorKey) {
    super(key);
    this.name = "AvatarError";
    this.key = key;
  }
}

export type ImageKind = "png" | "jpeg" | "webp";

/** The image type named by the first bytes, never by the file name or the browser-reported type. SVG and GIF are not recognised. */
export function sniffImageType(bytes: Uint8Array): ImageKind | null {
  const at = (offset: number, ...expected: number[]) => expected.every((value, index) => bytes[offset + index] === value);
  if (bytes.length >= 8 && at(0, 0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a)) return "png";
  if (bytes.length >= 3 && at(0, 0xff, 0xd8, 0xff)) return "jpeg";
  if (bytes.length >= 12 && at(0, 0x52, 0x49, 0x46, 0x46) && at(8, 0x57, 0x45, 0x42, 0x50)) return "webp";
  return null;
}

/** Decoded size of a base64 data URL in bytes. */
export function decodedBytes(dataUrl: string): number {
  const payload = dataUrl.slice(dataUrl.indexOf(",") + 1);
  const padding = payload.endsWith("==") ? 2 : payload.endsWith("=") ? 1 : 0;
  return Math.floor((payload.length * 3) / 4) - padding;
}

function readHead(file: Blob): Promise<Uint8Array> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(new Uint8Array(reader.result as ArrayBuffer));
    reader.onerror = () => reject(new AvatarError("errors.avatar.decode"));
    reader.readAsArrayBuffer(file.slice(0, 16));
  });
}

interface Decoded {
  image: HTMLImageElement;
  width: number;
  height: number;
}

/** Decodes by loading the bytes as an image: a file that is not really an image fails here. The object URL is always revoked by the caller. */
function decode(url: string): Promise<Decoded> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => {
      const width = image.naturalWidth;
      const height = image.naturalHeight;
      if (width < 1 || height < 1 || width * height > MAX_SOURCE_PIXELS) reject(new AvatarError("errors.avatar.decode"));
      else resolve({ image, width, height });
    };
    image.onerror = () => reject(new AvatarError("errors.avatar.decode"));
    image.src = url;
  });
}

/** A centred square crop of the source scaled to 256 by 256. `flatten` paints white first, for JPEG which has no alpha. */
function render({ image, width, height }: Decoded, flatten: boolean): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = AVATAR_SIZE;
  canvas.height = AVATAR_SIZE;
  const context = canvas.getContext("2d");
  if (!context) throw new AvatarError("errors.avatar.decode");
  if (flatten) {
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, AVATAR_SIZE, AVATAR_SIZE);
  }
  context.imageSmoothingQuality = "high";
  const side = Math.min(width, height);
  context.drawImage(image, Math.floor((width - side) / 2), Math.floor((height - side) / 2), side, side, 0, 0, AVATAR_SIZE, AVATAR_SIZE);
  return canvas;
}

/**
 * Turns a chosen file into the avatar data URL the server accepts (UI-34).
 *
 * The file is checked by its first bytes (PNG, JPEG or WebP only), decoded by the browser, cropped to a centred
 * square and drawn on a 256 by 256 canvas, then encoded again by the app. The stored value is therefore always
 * produced here and never the uploaded bytes. PNG is tried first for PNG and WebP sources (they may carry alpha),
 * then JPEG at falling quality, until the result is at most 256 KB.
 */
export async function downscaleToDataUrl(file: File): Promise<string> {
  if (file.size === 0) throw new AvatarError("errors.avatar.type");
  const kind = sniffImageType(await readHead(file));
  if (kind === null) throw new AvatarError("errors.avatar.type");
  if (file.size > MAX_INPUT_BYTES) throw new AvatarError("errors.avatar.decode");

  const url = URL.createObjectURL(file);
  try {
    const decoded = await decode(url);
    const attempts: Array<{ mime: "image/png" | "image/jpeg"; quality?: number }> = [
      ...(kind === "jpeg" ? [] : [{ mime: "image/png" as const }]),
      ...JPEG_QUALITIES.map((quality) => ({ mime: "image/jpeg" as const, quality })),
    ];
    let transparent: HTMLCanvasElement | null = null;
    let flat: HTMLCanvasElement | null = null;
    let oversized = false;
    for (const attempt of attempts) {
      let canvas: HTMLCanvasElement;
      if (attempt.mime === "image/png") canvas = transparent ??= render(decoded, false);
      else canvas = flat ??= render(decoded, true);
      const dataUrl = canvas.toDataURL(attempt.mime, attempt.quality);
      // A canvas that cannot encode answers "data:," or a type we do not store; nothing is passed through unchecked.
      if (avatarDataUrl(dataUrl) === null) throw new AvatarError("errors.avatar.decode");
      if (decodedBytes(dataUrl) <= AVATAR_MAX_BYTES) return dataUrl;
      oversized = true;
    }
    if (oversized) throw new AvatarError("errors.avatar.size");
    throw new AvatarError("errors.avatar.decode");
  } finally {
    URL.revokeObjectURL(url);
  }
}

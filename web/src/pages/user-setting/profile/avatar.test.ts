import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AVATAR_MAX_BYTES, AVATAR_SIZE, AvatarError, decodedBytes, downscaleToDataUrl, sniffImageType } from "./avatar";

const PNG_HEAD = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];
const JPEG_HEAD = [0xff, 0xd8, 0xff, 0xe0];
const WEBP_HEAD = [0x52, 0x49, 0x46, 0x46, 0, 0, 0, 0, 0x57, 0x45, 0x42, 0x50];

function file(head: number[], name: string, type: string, extra = 32): File {
  return new File([new Uint8Array([...head, ...new Array(extra).fill(7)])], name, { type });
}
function textFile(text: string, name: string, type: string): File {
  return new File([text], name, { type });
}

/** A base64 payload of a given decoded size (the bytes are irrelevant, only the length is measured). */
function payload(bytes: number): string {
  return "A".repeat(Math.ceil((bytes * 4) / 3));
}

type Mode = "ok" | "error";
let imageMode: Mode = "ok";
let natural = { width: 400, height: 300 };
let created: string[] = [];
let revoked: string[] = [];
let drawCalls: unknown[][] = [];
let encodings: Array<{ type: string | undefined; quality: number | undefined }> = [];
let encoder: (type: string | undefined, quality: number | undefined) => string;

class FakeImage {
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  naturalWidth = 0;
  naturalHeight = 0;
  set src(_value: string) {
    queueMicrotask(() => {
      if (imageMode === "error") {
        this.onerror?.();
        return;
      }
      this.naturalWidth = natural.width;
      this.naturalHeight = natural.height;
      this.onload?.();
    });
  }
}

beforeEach(() => {
  imageMode = "ok";
  natural = { width: 400, height: 300 };
  created = [];
  revoked = [];
  drawCalls = [];
  encodings = [];
  encoder = (type) => `data:${type ?? "image/png"};base64,${payload(1000)}`;
  vi.stubGlobal("Image", FakeImage);
  let counter = 0;
  URL.createObjectURL = vi.fn(() => {
    const url = `blob:test/${(counter += 1)}`;
    created.push(url);
    return url;
  });
  URL.revokeObjectURL = vi.fn((url: string) => {
    revoked.push(url);
  });
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(
    () =>
      ({
        drawImage: (...args: unknown[]) => drawCalls.push(args),
        fillRect: () => undefined,
        fillStyle: "",
        imageSmoothingQuality: "low",
      }) as unknown as CanvasRenderingContext2D,
  );
  vi.spyOn(HTMLCanvasElement.prototype, "toDataURL").mockImplementation((type?: string, quality?: number) => {
    encodings.push({ type, quality });
    return encoder(type, quality);
  });
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function rejection(promise: Promise<unknown>): Promise<AvatarError> {
  try {
    await promise;
  } catch (error) {
    expect(error).toBeInstanceOf(AvatarError);
    return error as AvatarError;
  }
  throw new Error("expected the promise to reject");
}

describe("sniffImageType (magic bytes)", () => {
  it("recognises PNG, JPEG and WebP only", () => {
    expect(sniffImageType(new Uint8Array([...PNG_HEAD, 1, 2]))).toBe("png");
    expect(sniffImageType(new Uint8Array([...JPEG_HEAD, 1, 2]))).toBe("jpeg");
    expect(sniffImageType(new Uint8Array([...WEBP_HEAD]))).toBe("webp");
  });

  it.each([
    ["GIF", [0x47, 0x49, 0x46, 0x38, 0x39, 0x61, 0, 0, 0, 0, 0, 0]],
    ["SVG", Array.from(new TextEncoder().encode('<svg xmlns="http://www.w3.org/2000/svg"/>'))],
    ["RIFF but not WebP", [0x52, 0x49, 0x46, 0x46, 0, 0, 0, 0, 0x57, 0x41, 0x56, 0x45]],
    ["a truncated PNG signature", [0x89, 0x50, 0x4e, 0x47]],
    ["empty", []],
  ])("refuses %s", (_name, bytes) => {
    expect(sniffImageType(new Uint8Array(bytes))).toBeNull();
  });
});

describe("decodedBytes", () => {
  it("counts the decoded size of a data URL, padding included", () => {
    expect(decodedBytes("data:image/png;base64,QUJD")).toBe(3);
    expect(decodedBytes("data:image/png;base64,QUI=")).toBe(2);
    expect(decodedBytes("data:image/png;base64,QQ==")).toBe(1);
  });
});

describe("downscaleToDataUrl: type check by first bytes", () => {
  it("rejects a text file that claims to be a PNG (browser type and extension are not trusted)", async () => {
    const error = await rejection(downscaleToDataUrl(textFile("not an image at all", "a.png", "image/png")));
    expect(error.key).toBe("errors.avatar.type");
    expect(created).toEqual([]);
  });

  it("rejects an SVG even when it is named .png and typed image/png", async () => {
    const svg = textFile('<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', "a.png", "image/png");
    expect((await rejection(downscaleToDataUrl(svg))).key).toBe("errors.avatar.type");
  });

  it("rejects a GIF", async () => {
    const gif = file([0x47, 0x49, 0x46, 0x38, 0x39, 0x61], "a.gif", "image/gif");
    expect((await rejection(downscaleToDataUrl(gif))).key).toBe("errors.avatar.type");
  });

  it("rejects an empty file", async () => {
    expect((await rejection(downscaleToDataUrl(new File([], "a.png", { type: "image/png" })))).key).toBe("errors.avatar.type");
  });

  it("accepts a real PNG whose browser-reported type is empty (magic bytes decide)", async () => {
    const url = await downscaleToDataUrl(file(PNG_HEAD, "a.png", ""));
    expect(url.startsWith("data:image/png;base64,")).toBe(true);
  });
});

describe("downscaleToDataUrl: decoding", () => {
  it("reports an undecodable file with its own message key and revokes the object URL", async () => {
    imageMode = "error";
    const error = await rejection(downscaleToDataUrl(file(PNG_HEAD, "a.png", "image/png")));
    expect(error.key).toBe("errors.avatar.decode");
    expect(created).toHaveLength(1);
    expect(revoked).toEqual(created);
  });

  it("rejects an image with no pixels", async () => {
    natural = { width: 0, height: 0 };
    expect((await rejection(downscaleToDataUrl(file(PNG_HEAD, "a.png", "image/png")))).key).toBe("errors.avatar.decode");
    expect(revoked).toEqual(created);
  });

  it("rejects an absurdly large pixel count before drawing it", async () => {
    natural = { width: 30_000, height: 30_000 };
    expect((await rejection(downscaleToDataUrl(file(PNG_HEAD, "a.png", "image/png")))).key).toBe("errors.avatar.decode");
    expect(drawCalls).toEqual([]);
    expect(revoked).toEqual(created);
  });

  it("reports a canvas that cannot give a 2d context as undecodable", async () => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(() => null);
    expect((await rejection(downscaleToDataUrl(file(PNG_HEAD, "a.png", "image/png")))).key).toBe("errors.avatar.decode");
    expect(revoked).toEqual(created);
  });

  it("does not pass a canvas result that is not a safe raster data URL through", async () => {
    encoder = () => "data:image/svg+xml;base64,PHN2Zz4=";
    expect((await rejection(downscaleToDataUrl(file(PNG_HEAD, "a.png", "image/png")))).key).toBe("errors.avatar.decode");
  });
});

describe("downscaleToDataUrl: result", () => {
  it("draws a centred square crop at 256x256 and returns an app-produced PNG data URL under 256 KB", async () => {
    const url = await downscaleToDataUrl(file(PNG_HEAD, "a.png", "image/png"));
    expect(url.startsWith("data:image/png;base64,")).toBe(true);
    expect(decodedBytes(url)).toBeLessThanOrEqual(AVATAR_MAX_BYTES);
    expect(drawCalls).toHaveLength(1);
    // 400x300: the shorter side (300) is the crop, centred horizontally.
    expect(drawCalls[0]!.slice(1)).toEqual([50, 0, 300, 300, 0, 0, AVATAR_SIZE, AVATAR_SIZE]);
    expect(created).toHaveLength(1);
    expect(revoked).toEqual(created);
  });

  it("re-encodes instead of passing the source file through", async () => {
    encoder = () => `data:image/png;base64,${payload(500)}`;
    const source = file(PNG_HEAD, "a.png", "image/png", 5000);
    const url = await downscaleToDataUrl(source);
    expect(decodedBytes(url)).toBe(500);
    expect(encodings[0]).toEqual({ type: "image/png", quality: undefined });
  });

  it("falls back to JPEG with falling quality when the PNG is over 256 KB", async () => {
    encoder = (type, quality) => {
      if (type === "image/png") return `data:image/png;base64,${payload(AVATAR_MAX_BYTES + 10)}`;
      return quality !== undefined && quality > 0.8 ? `data:image/jpeg;base64,${payload(AVATAR_MAX_BYTES + 10)}` : `data:image/jpeg;base64,${payload(40_000)}`;
    };
    const url = await downscaleToDataUrl(file(WEBP_HEAD, "a.webp", "image/webp"));
    expect(url.startsWith("data:image/jpeg;base64,")).toBe(true);
    expect(decodedBytes(url)).toBeLessThanOrEqual(AVATAR_MAX_BYTES);
    expect(encodings[0]!.type).toBe("image/png");
    expect(encodings.slice(1).every((e) => e.type === "image/jpeg")).toBe(true);
  });

  it("encodes a JPEG source as JPEG straight away", async () => {
    await downscaleToDataUrl(file(JPEG_HEAD, "a.jpg", "image/jpeg"));
    expect(encodings[0]!.type).toBe("image/jpeg");
  });

  it("reports the over-256 KB message when no encoding fits", async () => {
    encoder = (type) => `data:${type ?? "image/png"};base64,${payload(AVATAR_MAX_BYTES + 100)}`;
    const error = await rejection(downscaleToDataUrl(file(PNG_HEAD, "a.png", "image/png")));
    expect(error.key).toBe("errors.avatar.size");
    expect(revoked).toEqual(created);
  });

  it("accepts a result of exactly 256 KB", async () => {
    encoder = (type) => `data:${type ?? "image/png"};base64,${payload(AVATAR_MAX_BYTES)}`;
    const url = await downscaleToDataUrl(file(PNG_HEAD, "a.png", "image/png"));
    expect(decodedBytes(url)).toBeLessThanOrEqual(AVATAR_MAX_BYTES);
  });
});

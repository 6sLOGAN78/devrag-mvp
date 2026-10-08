import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useLastDefined } from "./use-last-defined";

describe("useLastDefined (IN-F08)", () => {
  it("returns the value while it is set and keeps the previous one after it becomes null", () => {
    const { result, rerender } = renderHook(({ value }: { value: string | null }) => useLastDefined(value), { initialProps: { value: null as string | null } });
    expect(result.current).toBeNull();
    rerender({ value: "workspace A" });
    expect(result.current).toBe("workspace A");
    rerender({ value: null });
    expect(result.current).toBe("workspace A");
    rerender({ value: "workspace B" });
    expect(result.current).toBe("workspace B");
  });
});

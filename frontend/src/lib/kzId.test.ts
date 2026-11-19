import { describe, expect, it } from "vitest";

import { isProgressEvent } from "../types/api";
import { isValidKzId } from "./kzId";

describe("isValidKzId (backend-тесттердегі сол мәндер)", () => {
  it.each(["900101300017", "901101300019"])("қабылдайды %s", (v) => expect(isValidKzId(v)).toBe(true));
  it.each(["900101300018", "90010130001", "9001013000171", "90010130001a", ""])("қабылдамайды %s", (v) =>
    expect(isValidKzId(v)).toBe(false),
  );
});

describe("isProgressEvent", () => {
  it("бэкенд оқиғасын қабылдайды", () => {
    expect(isProgressEvent({ status: "completed", progress: 100 })).toBe(true);
  });
  it.each([null, "x", { status: "weird", progress: 1 }, { status: "completed" }])("қабылдамайды %j", (v) =>
    expect(isProgressEvent(v)).toBe(false),
  );
});

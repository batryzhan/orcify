import { describe, expect, it } from "vitest";

import { isProgressEvent } from "../types/api";
import { isValidKzId } from "./kzId";

describe("isValidKzId (те же значения, что в backend-тестах)", () => {
  it.each(["900101300017", "901101300019"])("принимает %s", (v) => expect(isValidKzId(v)).toBe(true));
  it.each(["900101300018", "90010130001", "9001013000171", "90010130001a", ""])("отклоняет %s", (v) =>
    expect(isValidKzId(v)).toBe(false),
  );
});

describe("isProgressEvent", () => {
  it("принимает событие бэкенда", () => {
    expect(isProgressEvent({ status: "completed", progress: 100 })).toBe(true);
  });
  it.each([null, "x", { status: "weird", progress: 1 }, { status: "completed" }])("отклоняет %j", (v) =>
    expect(isProgressEvent(v)).toBe(false),
  );
});

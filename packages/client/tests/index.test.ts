import { describe, expect, it } from "vitest";
import { DebounceCancelledError, SemanticAutocompleteClient } from "../src/index";

describe("public API surface", () => {
  it("exports SemanticAutocompleteClient and DebounceCancelledError", () => {
    expect(SemanticAutocompleteClient).toBeTypeOf("function");
    expect(new DebounceCancelledError()).toBeInstanceOf(Error);
  });
});

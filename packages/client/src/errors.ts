export class DebounceCancelledError extends Error {
  constructor(message = "A newer call cancelled this pending debounced call") {
    super(message);
    this.name = "DebounceCancelledError";
  }
}

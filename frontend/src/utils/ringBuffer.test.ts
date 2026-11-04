import { describe, expect, it } from "vitest";
import { RingBuffer } from "./ringBuffer";

describe("RingBuffer", () => {
  it("initializes with fixed capacity and empty state", () => {
    const rb = new RingBuffer<number>(5);
    expect(rb.size()).toBe(0);
    expect(rb.getCapacity()).toBe(5);
    expect(rb.isEmpty()).toBe(true);
    expect(rb.isFull()).toBe(false);
    expect(rb.toArray()).toEqual([]);
  });

  it("throws error for non-positive or non-integer capacity", () => {
    expect(() => new RingBuffer<number>(0)).toThrow();
    expect(() => new RingBuffer<number>(-3)).toThrow();
    expect(() => new RingBuffer<number>(3.5)).toThrow();
  });

  it("pushes elements within capacity in chronological order", () => {
    const rb = new RingBuffer<string>(3);
    rb.push("A");
    rb.push("B");
    expect(rb.size()).toBe(2);
    expect(rb.toArray()).toEqual(["A", "B"]);
    expect(rb.peekLatest()).toBe("B");
    expect(rb.peekOldest()).toBe("A");
  });

  it("strictly bounds elements to capacity by overwriting oldest elements (FIFO eviction)", () => {
    const rb = new RingBuffer<number>(3);
    rb.push(1);
    rb.push(2);
    rb.push(3);
    expect(rb.isFull()).toBe(true);
    expect(rb.toArray()).toEqual([1, 2, 3]);

    // Overwrite oldest (1 -> 4)
    rb.push(4);
    expect(rb.size()).toBe(3);
    expect(rb.toArray()).toEqual([2, 3, 4]);
    expect(rb.peekOldest()).toBe(2);
    expect(rb.peekLatest()).toBe(4);

    // Overwrite oldest (2 -> 5)
    rb.push(5);
    expect(rb.size()).toBe(3);
    expect(rb.toArray()).toEqual([3, 4, 5]);

    // Push many
    rb.pushMany([6, 7, 8, 9, 10]);
    expect(rb.size()).toBe(3);
    expect(rb.toArray()).toEqual([8, 9, 10]);
  });

  it("clears elements and resets size and pointers", () => {
    const rb = new RingBuffer<number>(4);
    rb.pushMany([10, 20, 30, 40]);
    expect(rb.size()).toBe(4);
    rb.clear();
    expect(rb.size()).toBe(0);
    expect(rb.isEmpty()).toBe(true);
    expect(rb.peekLatest()).toBeUndefined();
    expect(rb.peekOldest()).toBeUndefined();
    expect(rb.toArray()).toEqual([]);

    // Can push again after clear
    rb.push(99);
    expect(rb.toArray()).toEqual([99]);
  });

  it("handles large stream of 10,000 pushes with zero heap expansion beyond capacity", () => {
    const rb = new RingBuffer<number>(500); // 500 max points for chart
    for (let i = 0; i < 10000; i++) {
      rb.push(i);
    }
    expect(rb.size()).toBe(500);
    expect(rb.isFull()).toBe(true);
    const arr = rb.toArray();
    expect(arr.length).toBe(500);
    expect(arr[0]).toBe(9500);
    expect(arr[499]).toBe(9999);
  });
});

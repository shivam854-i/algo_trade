/**
 * Generic bounded circular / ring buffer.
 *
 * Guarantees strictly O(1) push and lookup, pre-allocates an internal array of fixed size,
 * and overwrites the oldest element when capacity is reached.
 * Ensures zero heap expansion beyond initial capacity and minimizes GC churn during continuous
 * high-frequency streaming.
 */
export class RingBuffer<T> {
  private buffer: (T | undefined)[];
  private capacity: number;
  private head: number = 0; // index of oldest item
  private tail: number = 0; // index where next item will be inserted
  private count: number = 0;

  constructor(capacity: number) {
    if (capacity <= 0 || !Number.isInteger(capacity)) {
      throw new Error(`RingBuffer capacity must be a positive integer, got: ${capacity}`);
    }
    this.capacity = capacity;
    this.buffer = new Array<T | undefined>(capacity);
  }

  /**
   * Appends an item to the ring buffer.
   * If capacity is reached, overwrites the oldest item in O(1) time.
   */
  public push(item: T): void {
    this.buffer[this.tail] = item;
    this.tail = (this.tail + 1) % this.capacity;

    if (this.count < this.capacity) {
      this.count++;
    } else {
      // Overwrite oldest item: advance head
      this.head = (this.head + 1) % this.capacity;
    }
  }

  /**
   * Appends multiple items in sequential order.
   */
  public pushMany(items: T[]): void {
    if (!items || !Array.isArray(items)) return;
    for (let i = 0; i < items.length; i++) {
      this.push(items[i]);
    }
  }

  /**
   * Returns a snapshot of items in chronological order (oldest to newest).
   */
  public toArray(): T[] {
    const result: T[] = new Array<T>(this.count);
    for (let i = 0; i < this.count; i++) {
      result[i] = this.buffer[(this.head + i) % this.capacity] as T;
    }
    return result;
  }

  /**
   * Peeks at the most recently added item without removing it.
   */
  public peekLatest(): T | undefined {
    if (this.count === 0) return undefined;
    const latestIndex = (this.tail - 1 + this.capacity) % this.capacity;
    return this.buffer[latestIndex];
  }

  /**
   * Peeks at the oldest item in the buffer.
   */
  public peekOldest(): T | undefined {
    if (this.count === 0) return undefined;
    return this.buffer[this.head];
  }

  /**
   * Clears all items and resets pointers without reallocating buffer memory.
   */
  public clear(): void {
    for (let i = 0; i < this.capacity; i++) {
      this.buffer[i] = undefined;
    }
    this.head = 0;
    this.tail = 0;
    this.count = 0;
  }

  /**
   * Returns current number of items stored in buffer.
   */
  public size(): number {
    return this.count;
  }

  /**
   * Returns maximum capacity of buffer.
   */
  public getCapacity(): number {
    return this.capacity;
  }

  /**
   * Returns true if buffer is completely filled.
   */
  public isFull(): boolean {
    return this.count === this.capacity;
  }

  /**
   * Returns true if buffer contains zero items.
   */
  public isEmpty(): boolean {
    return this.count === 0;
  }
}

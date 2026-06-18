const CHUNK_FRAMES = 4096;

class PcmRecorderProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.freeBuffers = [];
    this.current = this.takeBuffer();
    this.offset = 0;

    this.port.onmessage = (event) => {
      const message = event.data;
      if (message && message.type === 'return-buffer' && message.buffer) {
        this.freeBuffers.push(new Float32Array(message.buffer));
      }
      if (message && message.type === 'flush') {
        this.flush();
        this.port.postMessage({ type: 'flushed' });
      }
    };
  }

  process(inputs) {
    const input = inputs[0];
    const channel = input && input[0];
    if (channel && channel.length > 0) {
      this.append(channel);
    }
    return true;
  }

  append(channel) {
    let readOffset = 0;
    while (readOffset < channel.length) {
      if (!this.current) {
        this.current = this.takeBuffer();
        this.offset = 0;
      }

      const writable = Math.min(channel.length - readOffset, CHUNK_FRAMES - this.offset);
      this.current.set(channel.subarray(readOffset, readOffset + writable), this.offset);
      this.offset += writable;
      readOffset += writable;

      if (this.offset === CHUNK_FRAMES) {
        this.flush();
      }
    }
  }

  flush() {
    if (!this.current || this.offset === 0) {
      return;
    }

    const buffer = this.current.buffer;
    this.port.postMessage({ type: 'pcm-chunk', buffer, frames: this.offset }, [buffer]);
    this.current = null;
    this.offset = 0;
  }

  takeBuffer() {
    return this.freeBuffers.pop() || new Float32Array(CHUNK_FRAMES);
  }
}

registerProcessor('pcm-recorder', PcmRecorderProcessor);

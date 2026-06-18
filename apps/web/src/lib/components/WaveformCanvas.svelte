<script lang="ts">
  import { afterUpdate, onMount } from 'svelte';

  export let samples: Float32Array | null = null;
  export let sampleRateHz = 0;

  let canvas: HTMLCanvasElement;
  let resizeObserver: ResizeObserver;

  onMount(() => {
    resizeObserver = new ResizeObserver(draw);
    resizeObserver.observe(canvas);
    draw();
    return () => resizeObserver.disconnect();
  });

  afterUpdate(draw);

  function draw(): void {
    if (!canvas) {
      return;
    }

    const context = canvas.getContext('2d');
    if (!context) {
      return;
    }

    const rect = canvas.getBoundingClientRect();
    const scale = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.floor(rect.width * scale));
    canvas.height = Math.max(1, Math.floor(rect.height * scale));
    context.setTransform(scale, 0, 0, scale, 0, 0);

    const width = rect.width;
    const height = rect.height;
    context.clearRect(0, 0, width, height);
    context.fillStyle = '#0c1110';
    context.fillRect(0, 0, width, height);

    drawGrid(context, width, height);

    if (!samples || samples.length === 0) {
      context.fillStyle = '#9fb0aa';
      context.font = '14px system-ui, sans-serif';
      context.fillText('Waiting for probe audio', 18, 32);
      return;
    }

    const centerY = height / 2;
    const verticalScale = height * 0.42;
    const step = Math.max(1, Math.ceil(samples.length / width));

    context.beginPath();
    context.strokeStyle = '#49d195';
    context.lineWidth = 1.5;

    for (let x = 0; x < width; x += 1) {
      const start = Math.floor(x * step);
      let min = 1;
      let max = -1;
      for (let index = start; index < Math.min(samples.length, start + step); index += 1) {
        const sample = samples[index] ?? 0;
        min = Math.min(min, sample);
        max = Math.max(max, sample);
      }
      context.moveTo(x, centerY - max * verticalScale);
      context.lineTo(x, centerY - min * verticalScale);
    }
    context.stroke();

    if (sampleRateHz > 0) {
      context.fillStyle = '#9fb0aa';
      context.font = '12px system-ui, sans-serif';
      context.fillText(`${(samples.length / sampleRateHz).toFixed(2)} s at ${sampleRateHz} Hz`, 18, height - 18);
    }
  }

  function drawGrid(context: CanvasRenderingContext2D, width: number, height: number): void {
    context.strokeStyle = 'rgba(88, 185, 209, 0.18)';
    context.lineWidth = 1;

    for (let x = 0; x <= width; x += Math.max(40, width / 8)) {
      context.beginPath();
      context.moveTo(x, 0);
      context.lineTo(x, height);
      context.stroke();
    }

    for (let y = 0; y <= height; y += Math.max(36, height / 6)) {
      context.beginPath();
      context.moveTo(0, y);
      context.lineTo(width, y);
      context.stroke();
    }

    context.strokeStyle = 'rgba(231, 240, 234, 0.35)';
    context.beginPath();
    context.moveTo(0, height / 2);
    context.lineTo(width, height / 2);
    context.stroke();
  }
</script>

<canvas bind:this={canvas} aria-label="Recorded probe waveform"></canvas>

<style>
  canvas {
    display: block;
    width: 100%;
    height: 100%;
    min-height: 280px;
  }
</style>

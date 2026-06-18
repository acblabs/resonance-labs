<script lang="ts">
  import { afterUpdate, onMount } from 'svelte';
  import type { SpectrogramGrid } from '$lib/audio/types';

  export let grid: SpectrogramGrid | null = null;

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
    const padding = { left: 46, right: 16, top: 16, bottom: 30 };
    context.clearRect(0, 0, width, height);
    context.fillStyle = '#0c1110';
    context.fillRect(0, 0, width, height);

    if (!grid || grid.magnitude_db.length === 0 || grid.times_seconds.length === 0) {
      drawEmpty(context);
      return;
    }

    const rows = grid.magnitude_db.length;
    const columns = grid.times_seconds.length;
    const plotWidth = Math.max(1, width - padding.left - padding.right);
    const plotHeight = Math.max(1, height - padding.top - padding.bottom);
    const cellWidth = plotWidth / columns;
    const cellHeight = plotHeight / rows;
    const { minDb, maxDb } = colorDomain(grid.magnitude_db);

    for (let row = 0; row < rows; row += 1) {
      const values = grid.magnitude_db[row];
      for (let column = 0; column < columns; column += 1) {
        const normalized = (values[column] - minDb) / (maxDb - minDb || 1);
        context.fillStyle = heatColor(normalized);
        context.fillRect(
          padding.left + column * cellWidth,
          padding.top + (rows - row - 1) * cellHeight,
          Math.max(1, Math.ceil(cellWidth)),
          Math.max(1, Math.ceil(cellHeight))
        );
      }
    }

    drawFrame(context, width, height, padding);
    drawLabels(context, width, height, padding, grid);
  }

  function colorDomain(values: number[][]): { minDb: number; maxDb: number } {
    const flattened = values.flat().filter(Number.isFinite);
    if (flattened.length === 0) {
      return { minDb: -120, maxDb: 0 };
    }
    const sorted = [...flattened].sort((a, b) => a - b);
    const low = sorted[Math.floor(sorted.length * 0.08)] ?? sorted[0];
    const high = sorted[Math.floor(sorted.length * 0.98)] ?? sorted[sorted.length - 1];
    return {
      minDb: Math.min(low, high - 12),
      maxDb: high
    };
  }

  function heatColor(value: number): string {
    const t = Math.max(0, Math.min(1, value));
    const stops = [
      [12, 17, 16],
      [28, 61, 78],
      [38, 121, 109],
      [73, 209, 149],
      [240, 179, 90]
    ];
    const scaled = t * (stops.length - 1);
    const index = Math.min(stops.length - 2, Math.floor(scaled));
    const mix = scaled - index;
    const from = stops[index];
    const to = stops[index + 1];
    const r = Math.round(from[0] + (to[0] - from[0]) * mix);
    const g = Math.round(from[1] + (to[1] - from[1]) * mix);
    const b = Math.round(from[2] + (to[2] - from[2]) * mix);
    return `rgb(${r}, ${g}, ${b})`;
  }

  function drawFrame(
    context: CanvasRenderingContext2D,
    width: number,
    height: number,
    padding: { left: number; right: number; top: number; bottom: number }
  ): void {
    context.strokeStyle = 'rgba(231, 240, 234, 0.28)';
    context.lineWidth = 1;
    context.strokeRect(
      padding.left,
      padding.top,
      width - padding.left - padding.right,
      height - padding.top - padding.bottom
    );
  }

  function drawLabels(
    context: CanvasRenderingContext2D,
    width: number,
    height: number,
    padding: { left: number; right: number; top: number; bottom: number },
    source: SpectrogramGrid
  ): void {
    const firstTime = source.times_seconds[0] ?? 0;
    const lastTime = source.times_seconds[source.times_seconds.length - 1] ?? firstTime;
    const firstFrequency = source.frequency_bins_hz[0] ?? 0;
    const lastFrequency = source.frequency_bins_hz[source.frequency_bins_hz.length - 1] ?? firstFrequency;

    context.fillStyle = '#9fb0aa';
    context.font = '12px system-ui, sans-serif';
    context.fillText(`${firstTime.toFixed(2)} s`, padding.left, height - 10);
    const timeLabel = `${lastTime.toFixed(2)} s`;
    context.fillText(timeLabel, width - padding.right - context.measureText(timeLabel).width, height - 10);
    context.fillText(`${Math.round(lastFrequency)} Hz`, 10, padding.top + 8);
    context.fillText(`${Math.round(firstFrequency)} Hz`, 10, height - padding.bottom);
  }

  function drawEmpty(context: CanvasRenderingContext2D): void {
    context.fillStyle = '#9fb0aa';
    context.font = '14px system-ui, sans-serif';
    context.fillText('Waiting for spectrogram analysis', 18, 32);
  }
</script>

<canvas bind:this={canvas} aria-label="STFT spectrogram"></canvas>

<style>
  canvas {
    display: block;
    width: 100%;
    height: 100%;
    min-height: 280px;
  }
</style>

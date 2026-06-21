<script lang="ts">
  import { afterUpdate, onMount } from 'svelte';
  import type { ResponseTrace } from '$lib/audio/types';

  export let trace: ResponseTrace | null = null;
  export let label = 'Response trace';
  export let stroke = '#58b9d1';

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
    const padding = { left: 50, right: 18, top: 18, bottom: 32 };
    context.clearRect(0, 0, width, height);
    context.fillStyle = '#0c1110';
    context.fillRect(0, 0, width, height);
    drawGrid(context, width, height, padding);

    const times = trace?.times_seconds ?? [];
    const magnitudes = trace?.magnitude_db ?? [];
    if (times.length < 2 || times.length !== magnitudes.length) {
      drawEmpty(context);
      return;
    }

    const minTime = times[0];
    const maxTime = times[times.length - 1];
    const minDb = -96;
    const maxDb = 0;
    const plotWidth = Math.max(1, width - padding.left - padding.right);
    const plotHeight = Math.max(1, height - padding.top - padding.bottom);

    context.beginPath();
    for (let index = 0; index < times.length; index += 1) {
      const x = padding.left + normalize(times[index], minTime, maxTime) * plotWidth;
      const y =
        padding.top +
        (1 - normalize(magnitudes[index], minDb, maxDb)) * plotHeight;
      if (index === 0) {
        context.moveTo(x, y);
      } else {
        context.lineTo(x, y);
      }
    }
    context.strokeStyle = stroke;
    context.lineWidth = 1.8;
    context.stroke();

    drawPeakMarker(context, {
      minTime,
      maxTime,
      plotWidth,
      plotHeight,
      padding
    });

    context.fillStyle = '#9fb0aa';
    context.font = '12px system-ui, sans-serif';
    context.fillText(label, padding.left, padding.top + 10);
    context.fillText(`${Math.round(minTime * 1000)} ms`, padding.left, height - 10);
    const maxLabel = `${Math.round(maxTime * 1000)} ms`;
    context.fillText(maxLabel, width - padding.right - context.measureText(maxLabel).width, height - 10);
    context.fillText('0 dB', 14, padding.top + 8);
    context.fillText('-96 dB', 10, height - padding.bottom);
  }

  function drawGrid(
    context: CanvasRenderingContext2D,
    width: number,
    height: number,
    padding: { left: number; right: number; top: number; bottom: number }
  ): void {
    const plotLeft = padding.left;
    const plotRight = width - padding.right;
    const plotTop = padding.top;
    const plotBottom = height - padding.bottom;
    context.strokeStyle = 'rgba(88, 185, 209, 0.16)';
    context.lineWidth = 1;

    for (let x = plotLeft; x <= plotRight; x += Math.max(48, (plotRight - plotLeft) / 6)) {
      context.beginPath();
      context.moveTo(x, plotTop);
      context.lineTo(x, plotBottom);
      context.stroke();
    }
    for (let y = plotTop; y <= plotBottom; y += Math.max(36, (plotBottom - plotTop) / 5)) {
      context.beginPath();
      context.moveTo(plotLeft, y);
      context.lineTo(plotRight, y);
      context.stroke();
    }
    context.strokeStyle = 'rgba(231, 240, 234, 0.28)';
    context.strokeRect(plotLeft, plotTop, plotRight - plotLeft, plotBottom - plotTop);
  }

  function drawPeakMarker(
    context: CanvasRenderingContext2D,
    bounds: {
      minTime: number;
      maxTime: number;
      plotWidth: number;
      plotHeight: number;
      padding: { left: number; right: number; top: number; bottom: number };
    }
  ): void {
    const peakTime = trace?.peak_time_seconds;
    if (peakTime === null || peakTime === undefined || !Number.isFinite(peakTime)) {
      return;
    }
    if (peakTime < bounds.minTime || peakTime > bounds.maxTime) {
      return;
    }
    const x = bounds.padding.left + normalize(peakTime, bounds.minTime, bounds.maxTime) * bounds.plotWidth;
    context.strokeStyle = 'rgba(240, 179, 90, 0.8)';
    context.beginPath();
    context.moveTo(x, bounds.padding.top);
    context.lineTo(x, bounds.padding.top + bounds.plotHeight);
    context.stroke();
    context.fillStyle = '#f0b35a';
    context.font = '11px system-ui, sans-serif';
    const labelText = `${Math.round(peakTime * 1000)} ms`;
    const labelX = Math.min(
      x + 5,
      bounds.padding.left + bounds.plotWidth - context.measureText(labelText).width
    );
    context.fillText(labelText, Math.max(bounds.padding.left, labelX), bounds.padding.top + 24);
  }

  function drawEmpty(context: CanvasRenderingContext2D): void {
    context.fillStyle = '#9fb0aa';
    context.font = '14px system-ui, sans-serif';
    context.fillText('Waiting for response analysis', 18, 32);
  }

  function normalize(value: number, min: number, max: number): number {
    if (!Number.isFinite(value) || !Number.isFinite(min) || !Number.isFinite(max) || max <= min) {
      return 0.5;
    }
    return Math.max(0, Math.min(1, (value - min) / (max - min)));
  }
</script>

<canvas bind:this={canvas} aria-label={label}></canvas>

<style>
  canvas {
    display: block;
    width: 100%;
    height: 100%;
    min-height: 280px;
  }
</style>

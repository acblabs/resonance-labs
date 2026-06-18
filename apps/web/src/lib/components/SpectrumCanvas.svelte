<script lang="ts">
  import { afterUpdate, onMount } from 'svelte';
  import type { FrequencySeries, PeakFeature } from '$lib/audio/types';

  export let series: FrequencySeries | null = null;
  export let peaks: PeakFeature[] = [];

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
    const padding = { left: 46, right: 16, top: 18, bottom: 28 };
    context.clearRect(0, 0, width, height);
    context.fillStyle = '#0c1110';
    context.fillRect(0, 0, width, height);
    drawGrid(context, width, height, padding);

    const frequencies = series?.frequency_bins_hz ?? [];
    const magnitudes = series?.magnitude_db ?? [];
    if (frequencies.length < 2 || magnitudes.length !== frequencies.length) {
      drawEmpty(context);
      return;
    }

    const minFrequency = frequencies[0];
    const maxFrequency = frequencies[frequencies.length - 1];
    const maxDb = Math.max(...magnitudes);
    const minDb = Math.max(Math.min(...magnitudes), maxDb - 78);
    const plotWidth = Math.max(1, width - padding.left - padding.right);
    const plotHeight = Math.max(1, height - padding.top - padding.bottom);

    context.beginPath();
    for (let index = 0; index < frequencies.length; index += 1) {
      const x = padding.left + ((frequencies[index] - minFrequency) / (maxFrequency - minFrequency)) * plotWidth;
      const y = padding.top + (1 - (magnitudes[index] - minDb) / (maxDb - minDb || 1)) * plotHeight;
      if (index === 0) {
        context.moveTo(x, y);
      } else {
        context.lineTo(x, y);
      }
    }
    context.strokeStyle = '#49d195';
    context.lineWidth = 1.7;
    context.stroke();

    drawPeaks(context, peaks, {
      minFrequency,
      maxFrequency,
      minDb,
      maxDb,
      plotWidth,
      plotHeight,
      padding
    });

    context.fillStyle = '#9fb0aa';
    context.font = '12px system-ui, sans-serif';
    context.fillText(`${Math.round(minFrequency)} Hz`, padding.left, height - 10);
    const maxLabel = `${Math.round(maxFrequency / 1000)} kHz`;
    context.fillText(maxLabel, width - padding.right - context.measureText(maxLabel).width, height - 10);
    context.fillText(`${Math.round(maxDb)} dB`, 12, padding.top + 8);
  }

  function drawGrid(
    context: CanvasRenderingContext2D,
    width: number,
    height: number,
    padding: { left: number; right: number; top: number; bottom: number }
  ): void {
    context.strokeStyle = 'rgba(88, 185, 209, 0.16)';
    context.lineWidth = 1;

    const plotLeft = padding.left;
    const plotRight = width - padding.right;
    const plotTop = padding.top;
    const plotBottom = height - padding.bottom;

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
  }

  function drawPeaks(
    context: CanvasRenderingContext2D,
    peakList: PeakFeature[],
    bounds: {
      minFrequency: number;
      maxFrequency: number;
      minDb: number;
      maxDb: number;
      plotWidth: number;
      plotHeight: number;
      padding: { left: number; right: number; top: number; bottom: number };
    }
  ): void {
    const visiblePeaks = peakList.slice(0, 4).filter((peak) => {
      return peak.frequency_hz >= bounds.minFrequency && peak.frequency_hz <= bounds.maxFrequency;
    });

    context.font = '11px system-ui, sans-serif';
    for (const peak of visiblePeaks) {
      const x =
        bounds.padding.left +
        ((peak.frequency_hz - bounds.minFrequency) / (bounds.maxFrequency - bounds.minFrequency)) *
          bounds.plotWidth;
      const y =
        bounds.padding.top +
        (1 - (peak.magnitude_db - bounds.minDb) / (bounds.maxDb - bounds.minDb || 1)) *
          bounds.plotHeight;

      context.strokeStyle = 'rgba(240, 179, 90, 0.75)';
      context.beginPath();
      context.moveTo(x, bounds.padding.top);
      context.lineTo(x, bounds.padding.top + bounds.plotHeight);
      context.stroke();

      context.fillStyle = '#f0b35a';
      context.beginPath();
      context.arc(x, y, 3.5, 0, Math.PI * 2);
      context.fill();

      const label = `${Math.round(peak.frequency_hz)} Hz`;
      const labelX = Math.min(x + 5, bounds.padding.left + bounds.plotWidth - context.measureText(label).width);
      context.fillText(label, Math.max(bounds.padding.left, labelX), Math.max(14, y - 7));
    }
  }

  function drawEmpty(context: CanvasRenderingContext2D): void {
    context.fillStyle = '#9fb0aa';
    context.font = '14px system-ui, sans-serif';
    context.fillText('Waiting for FFT analysis', 18, 32);
  }
</script>

<canvas bind:this={canvas} aria-label="FFT magnitude spectrum"></canvas>

<style>
  canvas {
    display: block;
    width: 100%;
    height: 100%;
    min-height: 280px;
  }
</style>

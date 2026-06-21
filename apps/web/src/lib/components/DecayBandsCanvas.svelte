<script lang="ts">
  import { afterUpdate, onMount } from 'svelte';
  import type { DecayBandFeature } from '$lib/audio/types';

  export let bands: DecayBandFeature[] = [];

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
    const padding = { left: 132, right: 70, top: 18, bottom: 26 };
    context.clearRect(0, 0, width, height);
    context.fillStyle = '#0c1110';
    context.fillRect(0, 0, width, height);

    const visible = bands.slice(0, 3);
    if (!visible.length) {
      drawEmpty(context);
      return;
    }

    const rt60Values = visible
      .map((band) => band.rt60_seconds)
      .filter((value): value is number => value !== null && Number.isFinite(value));
    const maxRt60 = Math.max(0.1, ...rt60Values);
    const plotLeft = padding.left;
    const plotWidth = Math.max(1, width - padding.left - padding.right);
    const rowHeight = Math.max(42, (height - padding.top - padding.bottom) / visible.length);

    drawAxis(context, width, height, padding, maxRt60);
    visible.forEach((band, index) => {
      const y = padding.top + index * rowHeight + rowHeight * 0.5;
      drawBand(context, band, y, plotLeft, plotWidth, maxRt60);
    });
  }

  function drawBand(
    context: CanvasRenderingContext2D,
    band: DecayBandFeature,
    y: number,
    x: number,
    width: number,
    maxRt60: number
  ): void {
    const rt60 = band.rt60_seconds;
    const valueWidth =
      rt60 === null || !Number.isFinite(rt60) || rt60 <= 0
        ? 0
        : Math.max(5, Math.min(1, rt60 / maxRt60) * width);
    const color = band.label === 'low' ? '#f0b35a' : band.label === 'mid' ? '#49d195' : '#58b9d1';

    context.fillStyle = '#9fb0aa';
    context.font = '700 12px system-ui, sans-serif';
    context.textAlign = 'right';
    context.fillText(
      `${band.label.toUpperCase()} ${formatHz(band.start_hz)}-${formatHz(band.end_hz)}`,
      x - 12,
      y + 4
    );

    roundedRect(context, x, y - 10, width, 20, 5, '#24312d');
    if (valueWidth > 0) {
      roundedRect(context, x, y - 10, valueWidth, 20, 5, color);
    }

    context.fillStyle = '#e7f0ea';
    context.textAlign = 'left';
    context.font = '800 13px system-ui, sans-serif';
    context.fillText(formatSeconds(rt60), x + width + 12, y + 4);
    context.fillStyle = '#9fb0aa';
    context.font = '11px system-ui, sans-serif';
    context.fillText(
      band.fit_r2 === null ? 'fit --' : `fit ${band.fit_r2.toFixed(2)}`,
      x + width + 12,
      y + 19
    );
  }

  function drawAxis(
    context: CanvasRenderingContext2D,
    width: number,
    height: number,
    padding: { left: number; right: number; top: number; bottom: number },
    maxRt60: number
  ): void {
    const plotLeft = padding.left;
    const plotRight = width - padding.right;
    const plotBottom = height - padding.bottom;
    context.strokeStyle = 'rgba(88, 185, 209, 0.16)';
    context.lineWidth = 1;
    for (let tick = 0; tick <= 4; tick += 1) {
      const x = plotLeft + ((plotRight - plotLeft) * tick) / 4;
      context.beginPath();
      context.moveTo(x, padding.top);
      context.lineTo(x, plotBottom);
      context.stroke();
    }
    context.fillStyle = '#9fb0aa';
    context.font = '11px system-ui, sans-serif';
    context.textAlign = 'left';
    context.fillText('0 s', plotLeft, height - 8);
    context.textAlign = 'right';
    context.fillText(`${maxRt60.toFixed(2)} s`, plotRight, height - 8);
    context.textAlign = 'left';
  }

  function drawEmpty(context: CanvasRenderingContext2D): void {
    context.fillStyle = '#9fb0aa';
    context.font = '14px system-ui, sans-serif';
    context.fillText('Waiting for decay-band analysis', 18, 32);
  }

  function formatHz(value: number): string {
    if (value >= 1000) {
      return `${(value / 1000).toFixed(value >= 10000 ? 1 : 2)} kHz`;
    }
    return `${Math.round(value)} Hz`;
  }

  function formatSeconds(value: number | null): string {
    if (value === null || !Number.isFinite(value)) {
      return '--';
    }
    return `${value.toFixed(3)} s`;
  }

  function roundedRect(
    context: CanvasRenderingContext2D,
    x: number,
    y: number,
    width: number,
    height: number,
    radius: number,
    fill: string
  ): void {
    context.beginPath();
    context.moveTo(x + radius, y);
    context.lineTo(x + width - radius, y);
    context.quadraticCurveTo(x + width, y, x + width, y + radius);
    context.lineTo(x + width, y + height - radius);
    context.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
    context.lineTo(x + radius, y + height);
    context.quadraticCurveTo(x, y + height, x, y + height - radius);
    context.lineTo(x, y + radius);
    context.quadraticCurveTo(x, y, x + radius, y);
    context.closePath();
    context.fillStyle = fill;
    context.fill();
  }
</script>

<canvas bind:this={canvas} aria-label="Decay-band RT60 proxy chart"></canvas>

<style>
  canvas {
    display: block;
    width: 100%;
    height: 100%;
    min-height: 180px;
  }
</style>

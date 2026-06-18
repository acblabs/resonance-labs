<script lang="ts">
  import '../app.css';
</script>

<div class="app-shell">
  <header class="topbar">
    <a class="brand" href="/">
      <span class="brand-mark">RL</span>
      <span>ResonanceLab</span>
    </a>
    <nav class="nav" aria-label="Primary">
      <a href="/">Probe</a>
      <a href="/lab">Lab</a>
    </nav>
  </header>
  <slot />
</div>

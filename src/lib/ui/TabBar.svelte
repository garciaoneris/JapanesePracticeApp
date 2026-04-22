<script lang="ts">
  import { link, location } from 'svelte-spa-router';

  interface Tab {
    id: string;
    label: string;
    /** Route to navigate to on tap. */
    href: string;
    /** Routes that should highlight this tab (prefix match). Lets
     *  `/learn/食` highlight Home, `/vocab/water` highlight Vocabulary,
     *  etc. */
    matches: (path: string) => boolean;
    icon: 'home' | 'review' | 'vocab' | 'fill' | 'profile';
  }

  const TABS: readonly Tab[] = [
    {
      id: 'home',
      label: 'Home',
      href: '/',
      matches: (p) => p === '/' || p.startsWith('/learn') || p.startsWith('/complete') || p.startsWith('/reinforce'),
      icon: 'home',
    },
    {
      id: 'review',
      label: 'Review',
      href: '/review',
      matches: (p) => p.startsWith('/review'),
      icon: 'review',
    },
    {
      id: 'vocab',
      label: 'Vocabulary',
      href: '/vocabulary',
      matches: (p) => p.startsWith('/vocabulary') || p.startsWith('/vocab/'),
      icon: 'vocab',
    },
    {
      id: 'fill',
      label: 'Fill Kanji',
      href: '/fill-kanji',
      matches: (p) => p.startsWith('/fill-kanji'),
      icon: 'fill',
    },
    {
      id: 'profile',
      label: 'Profile',
      href: '/settings',
      matches: (p) => p.startsWith('/settings'),
      icon: 'profile',
    },
  ];

  const activeId = $derived(TABS.find((t) => t.matches($location))?.id ?? 'home');
</script>

<nav class="tabbar" aria-label="Primary">
  {#each TABS as t (t.id)}
    <a
      class="tab"
      class:active={activeId === t.id}
      href={t.href}
      use:link
      aria-label={t.label}
      aria-current={activeId === t.id ? 'page' : undefined}
    >
      <span class="tab-icon" aria-hidden="true">
        {#if t.icon === 'home'}
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
            <polyline points="9 22 9 12 15 12 15 22"/>
          </svg>
        {:else if t.icon === 'review'}
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polygon points="6 3 20 12 6 21 6 3"/>
          </svg>
        {:else if t.icon === 'vocab'}
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
            <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
          </svg>
        {:else if t.icon === 'fill'}
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 20h9"/>
            <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4z"/>
          </svg>
        {:else}
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
            <circle cx="12" cy="7" r="4"/>
          </svg>
        {/if}
      </span>
      <span class="tab-label">{t.label}</span>
      <span class="tab-ind" aria-hidden="true"></span>
    </a>
  {/each}
</nav>

<style>
  .tabbar {
    position: fixed;
    left: 12px;
    right: 12px;
    bottom: calc(12px + env(safe-area-inset-bottom, 0px));
    height: 64px;
    display: flex;
    align-items: stretch;
    padding: 0 8px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 999px;
    box-shadow: var(--shadow-md);
    z-index: 100;
    max-width: 820px;
    margin: 0 auto;
  }
  .tab {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 2px;
    padding: 8px 4px;
    text-decoration: none;
    color: var(--ink-2);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.02em;
    min-width: 0;
    border-radius: 999px;
  }
  .tab-icon { display: inline-flex; line-height: 0; }
  .tab-label {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 100%;
  }
  .tab.active { color: var(--accent); }
  .tab-ind {
    width: 4px;
    height: 4px;
    border-radius: 999px;
    background: currentColor;
    opacity: 0;
    margin-top: 1px;
  }
  .tab.active .tab-ind { opacity: 1; }

  @media (max-width: 420px) {
    .tab-label { font-size: 10px; }
  }
</style>

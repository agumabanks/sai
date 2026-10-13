@props([
    'shell' => [],
    'metrics' => [],
])

@php
    $live = $shell['live'] ?? [];
    $dockMetrics = $live['metrics'] ?? $metrics;
    $devices = $live['devices']['connected'] ?? [];
    $deviceStats = $live['devices']['stats'] ?? [];
    $ecosystem = $live['ecosystem']['apps'] ?? [];
    $ecosystemSummary = $live['ecosystem']['summary'] ?? [];
    $shortcuts = $shell['quick_launch'] ?? [];
    $registry = $shell['registry'] ?? [];
    $needsHeal = collect($ecosystem)->filter(fn ($a) => ($a['can_heal'] ?? false) && ($a['status'] ?? '') !== 'healthy');
@endphp

<div {{ $attributes->merge(['class' => 'sanaa-command-dock']) }} x-data="{
    healing: null,
    async healApp(key) {
        this.healing = key;
        try {
            const res = await fetch(`/os/ecosystem/${key}/heal`, {
                method: 'POST',
                headers: {
                    'Accept': 'application/json',
                    'Content-Type': 'application/json',
                    'X-CSRF-TOKEN': document.querySelector('meta[name=csrf-token]')?.content || '',
                },
                credentials: 'same-origin',
            });
            const data = await res.json();
            if (!res.ok || !data.success) throw new Error(data.error || 'Heal failed');
            $dispatch('notify', { title: 'Heal dispatched', body: key + ': ' + data.action_taken });
        } catch (e) {
            $dispatch('notify', { title: 'Heal failed', body: e.message });
        } finally {
            this.healing = null;
        }
    },
    async pollApps() {
        await fetch('/os/ecosystem/poll', {
            method: 'POST',
            headers: {
                'Accept': 'application/json',
                'X-CSRF-TOKEN': document.querySelector('meta[name=csrf-token]')?.content || '',
            },
            credentials: 'same-origin',
        });
        location.reload();
    }
}">
    <div class="sanaa-command-dock-inner">
        <div class="sanaa-command-dock-section sanaa-command-dock-shortcuts">
            <span class="sanaa-command-dock-label">Shortcuts</span>
            <div class="sanaa-command-dock-chip-row">
                @forelse($shortcuts as $shortcut)
                    <a
                        href="{{ ($shortcut['external'] ?? false) ? ($shortcut['url'] ?? '#') : ($shortcut['url'] ?? url('/')) }}"
                        class="sanaa-command-dock-chip sanaa-command-dock-shortcut"
                        style="--dock-accent: {{ $shortcut['accent'] ?? '#6366f1' }}"
                        @if($shortcut['external'] ?? false) target="_blank" rel="noopener" @endif
                    >
                        <span class="sanaa-command-dock-chip-title">{{ $shortcut['label'] }}</span>
                    </a>
                @empty
                    <span class="sanaa-command-dock-muted">No shortcuts configured</span>
                @endforelse
            </div>
        </div>

        <div class="sanaa-command-dock-section sanaa-command-dock-stats">
            <span class="sanaa-command-dock-label">Live</span>
            <div class="sanaa-command-dock-chip-row">
                <span class="sanaa-command-dock-stat">CPU <strong>{{ $dockMetrics['cpu'] ?? 0 }}%</strong></span>
                <span class="sanaa-command-dock-stat">RAM <strong>{{ $dockMetrics['memory'] ?? 0 }}%</strong></span>
                <span class="sanaa-command-dock-stat">Disk <strong>{{ $dockMetrics['disk'] ?? 0 }}%</strong></span>
                <span class="sanaa-command-dock-stat {{ ($dockMetrics['alerts'] ?? 0) > 0 ? 'is-warning' : '' }}">Alerts <strong>{{ $dockMetrics['alerts'] ?? 0 }}</strong></span>
                <span class="sanaa-command-dock-stat">Devices <strong>{{ $deviceStats['online'] ?? 0 }}/{{ $deviceStats['total'] ?? 0 }}</strong></span>
                <span class="sanaa-command-dock-stat">Apps <strong>{{ $ecosystemSummary['healthy'] ?? 0 }}/{{ $ecosystemSummary['total'] ?? 0 }}</strong></span>
            </div>
        </div>

        <div class="sanaa-command-dock-section sanaa-command-dock-devices">
            <span class="sanaa-command-dock-label">Devices</span>
            <div class="sanaa-command-dock-chip-row">
                @forelse($devices as $device)
                    <a href="{{ $registry['device_army_url'] ?? '#' }}" class="sanaa-command-dock-chip sanaa-command-dock-device is-{{ $device['status'] ?? 'offline' }}">
                        <span class="sanaa-command-dock-dot"></span>
                        <span>{{ $device['name'] ?? 'Device' }}</span>
                    </a>
                @empty
                    <span class="sanaa-command-dock-muted">No workers connected</span>
                @endforelse
            </div>
        </div>

        <div class="sanaa-command-dock-section sanaa-command-dock-apps">
            <div class="flex items-center justify-between gap-2 w-full mb-1">
                <span class="sanaa-command-dock-label mb-0">Sanaa Apps</span>
                <div class="flex items-center gap-1.5">
                    @if($needsHeal->isNotEmpty())
                        <button type="button" @click="pollApps()" class="sanaa-command-dock-heal-btn">Refresh</button>
                    @endif
                    <a href="{{ $registry['doctor_url'] ?? '#' }}" class="sanaa-command-dock-heal-btn">Doctor</a>
                </div>
            </div>
            <div class="sanaa-command-dock-chip-row">
                @forelse($ecosystem as $app)
                    <span class="inline-flex items-center gap-1">
                        <a
                            href="{{ $app['external_url'] ?: ($registry['doctor_url'] ?? '#') }}"
                            class="sanaa-command-dock-chip sanaa-command-dock-app is-{{ $app['status'] ?? 'unknown' }}"
                            @if(!empty($app['external_url'])) target="_blank" rel="noopener" @endif
                        >
                            <span class="sanaa-command-dock-dot"></span>
                            <span>{{ $app['name'] ?? $app['key'] }}</span>
                        </a>
                        @if(($app['can_heal'] ?? false) && ($app['status'] ?? '') !== 'healthy')
                            <button
                                type="button"
                                class="sanaa-command-dock-heal-btn"
                                :disabled="healing === '{{ $app['key'] }}'"
                                @click="healApp('{{ $app['key'] }}')"
                            >Heal</button>
                        @endif
                    </span>
                @empty
                    <span class="sanaa-command-dock-muted">No monitored apps</span>
                @endforelse
            </div>
        </div>
    </div>
</div>
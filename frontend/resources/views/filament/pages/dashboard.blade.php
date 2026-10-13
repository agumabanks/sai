@php
    $dashboardModules = \App\Support\SanaaModules::dashboardTiles();
    $launcherModules = \App\Support\SanaaModules::all();
@endphp

<x-sanaa-module-shell-script :modules="$launcherModules" />

<x-filament-panels::page class="relative">
    {{-- Dashboard background --}}
    <div class="sanaa-dashboard-backdrop fixed inset-0 z-0 pointer-events-none w-full h-full overflow-hidden"></div>

    <div class="sanaa-dashboard-shell relative z-10 space-y-4 sm:space-y-5 lg:space-y-6 w-full max-w-[1400px] mx-auto">

        {{-- ── Header ──────────────────────────────────────────────────────── --}}
        <div class="sanaa-dashboard-header flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div class="flex items-center gap-4">
                <div class="sanaa-dashboard-logo">
                    <x-sanaa-logo class="w-6 h-6 text-white" />
                </div>
                <div>
                    <h1 class="text-xl font-semibold text-white/95">Sanaa Command Center</h1>
                    <p class="text-[12px] text-white/45 font-medium">Primary hub — chat, terminal, skills, and all platform modules</p>
                </div>
            </div>
            <div class="flex items-center gap-2.5 flex-wrap">
                @php
                    $statusColor = match($systemMetrics['overallStatus'] ?? 'unknown') {
                        'ok' => 'text-[#30d158] bg-[#30d158]/10 border-[#30d158]/20',
                        'warning' => 'text-[#ff9f0a] bg-[#ff9f0a]/10 border-[#ff9f0a]/20',
                        'critical' => 'text-[#ff453a] bg-[#ff453a]/10 border-[#ff453a]/20',
                        default => 'text-white/50 bg-white/5 border-white/10',
                    };
                    $statusDot = match($systemMetrics['overallStatus'] ?? 'unknown') {
                        'ok' => 'bg-[#30d158]', 'warning' => 'bg-[#ff9f0a]', 'critical' => 'bg-[#ff453a]', default => 'bg-white/50',
                    };
                    $statusLabel = match($systemMetrics['overallStatus'] ?? 'unknown') {
                        'ok' => 'All Systems Nominal', 'warning' => 'Warning', 'critical' => 'Critical', default => 'Checking...',
                    };
                @endphp
                <div class="flex items-center gap-2 px-3 py-1.5 rounded-full backdrop-blur-md border {{ $statusColor }} text-[11px] font-medium tracking-wide uppercase">
                    <div class="relative flex items-center justify-center">
                        @if(($systemMetrics['overallStatus'] ?? 'unknown') !== 'ok')
                            <div class="w-2 h-2 rounded-full {{ $statusDot }} animate-ping absolute opacity-50"></div>
                        @endif
                        <div class="w-2 h-2 rounded-full {{ $statusDot }}"></div>
                    </div>
                    {{ $statusLabel }}
                </div>
                <div class="flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/[0.05] border border-white/[0.08] backdrop-blur-md text-[11px] font-medium text-white/50 uppercase tracking-wide">
                    <span class="w-1.5 h-1.5 rounded-full bg-[#5e5ce6]"></span>
                    {{ strtoupper($systemMetrics['activeBrain'] ?? 'Unknown') }} Brain
                </div>
            </div>
        </div>

        @if(!empty($systemMetrics['backendWarning']))
            <div class="rounded-2xl border border-amber-400/20 bg-amber-400/10 px-5 py-4 text-amber-50 shadow-[0_8px_30px_rgba(245,158,11,0.08)]">
                <div class="flex items-start gap-3">
                    <div class="mt-0.5 flex h-9 w-9 items-center justify-center rounded-2xl bg-amber-300/10 text-amber-200">
                        <x-heroicon-m-exclamation-triangle class="h-5 w-5" />
                    </div>
                    <div>
                        <p class="text-[11px] font-bold uppercase tracking-[0.22em] text-amber-200">Backend Misconfiguration</p>
                        <p class="mt-2 text-sm leading-6">{{ $systemMetrics['backendWarning'] }}</p>
                    </div>
                </div>
            </div>
        @endif

        {{-- ── Quick Shortcuts (registry-driven) ───────────────────────────── --}}
        @if(!empty($shellData['quick_launch']))
            <div class="sanaa-dashboard-shortcuts">
                <div class="sanaa-dashboard-shortcuts-head">
                    <p class="text-[10px] font-semibold tracking-[0.16em] text-white/30 uppercase">Quick Shortcuts</p>
                    <p class="mt-1 text-sm text-white/55">Launch Sanaa OS, command center, and pinned modules</p>
                </div>
                <div class="sanaa-dashboard-shortcuts-row">
                    @foreach($shellData['quick_launch'] as $shortcut)
                        <a
                            href="{{ ($shortcut['external'] ?? false) ? ($shortcut['url'] ?? '#') : ($shortcut['url'] ?? url('/')) }}"
                            class="sanaa-dashboard-shortcut"
                            style="--dock-accent: {{ $shortcut['accent'] ?? '#6366f1' }}"
                            @if($shortcut['external'] ?? false) target="_blank" rel="noopener" @endif
                        >
                            <span class="sanaa-dashboard-shortcut-label">{{ $shortcut['label'] }}</span>
                            <span class="sanaa-dashboard-shortcut-sub">{{ $shortcut['description'] ?? '' }}</span>
                        </a>
                    @endforeach
                </div>
            </div>
        @endif

        {{-- ── Sanaa AI App Launcher ───────────────────────────────────────── --}}
        <div class="sanaa-dashboard-launcher" x-data="sanaaAppLauncher">
            <div class="flex items-center justify-between gap-3">
                <div>
                    <p class="text-[10px] font-semibold tracking-[0.16em] text-white/30 uppercase">Sanaa AI Modules</p>
                    <p class="mt-1 text-sm text-white/65" x-text="activeModule?.label || 'Dashboard'"></p>
                </div>
                <span class="sanaa-dashboard-active-pill" x-text="activeModule?.short_label || 'Home'"></span>
            </div>

            <div class="sanaa-dashboard-module-grid">
                @foreach($dashboardModules as $module)
                    <a
                        href="{{ $module['url'] }}"
                        class="sanaa-dashboard-module"
                        style="--sanaa-module-accent: {{ $module['accent'] }}"
                        @if(!empty($module['external'])) target="_blank" rel="noopener" @endif
                        x-on:click="selectModule('{{ $module['id'] }}', {{ !empty($module['external']) ? 'true' : 'false' }})"
                    >
                        <span class="sanaa-dashboard-module-icon">
                            <x-dynamic-component :component="$module['icon']" class="h-6 w-6" />
                        </span>
                        <span class="sanaa-dashboard-module-label">{{ $module['label'] }}</span>
                        <span class="sanaa-dashboard-module-sub">{{ $module['description'] }}</span>
                    </a>
                @endforeach
            </div>
        </div>

        {{-- ── Metrics Strip ───────────────────────────────────────────────── --}}
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-3">
            @php $cpuColor = ($systemMetrics['cpu'] ?? 0) > 80 ? 'danger' : (($systemMetrics['cpu'] ?? 0) > 60 ? 'warning' : 'success'); @endphp
            <x-metric-card label="CPU" :value="($systemMetrics['cpu'] ?? 0) . '%'" icon="heroicon-m-cpu-chip" :description="($systemMetrics['cpuCores'] ?? 0) . ' cores'" :color="$cpuColor" :trend="($systemMetrics['cpuStatus'] ?? 'ok') === 'ok' ? 'Normal' : 'High'" />
            @php $memColor = ($systemMetrics['memory'] ?? 0) > 85 ? 'danger' : (($systemMetrics['memory'] ?? 0) > 70 ? 'warning' : 'info'); @endphp
            <x-metric-card label="Memory" :value="($systemMetrics['memory'] ?? 0) . '%'" icon="heroicon-m-square-3-stack-3d" :description="($systemMetrics['memoryTotal'] ?? 0) . ' GB'" :color="$memColor" :trend="($systemMetrics['memoryStatus'] ?? 'ok') === 'ok' ? 'Normal' : 'Elevated'" />
            <x-metric-card label="Disk" :value="($systemMetrics['disk'] ?? 0) . '%'" icon="heroicon-m-circle-stack" :description="($systemMetrics['diskFree'] ?? 0) . ' GB free'" :color="($systemMetrics['disk'] ?? 0) > 85 ? 'danger' : 'primary'" :trend="($systemMetrics['diskStatus'] ?? 'ok') === 'ok' ? 'Healthy' : 'Low'" />
            <x-metric-card label="Uptime" :value="$systemMetrics['uptime'] ?? 'N/A'" icon="heroicon-m-clock" description="Since restart" color="success" trend="Stable" />
            @php $alertCount = $systemMetrics['alertCount'] ?? 0; @endphp
            <x-metric-card label="Alerts" :value="(string) $alertCount" icon="heroicon-m-bell-alert" description="Unacked" :color="$alertCount > 10 ? 'danger' : ($alertCount > 0 ? 'warning' : 'success')" :trend="$alertCount === 0 ? 'All Clear' : ($alertCount > 10 ? '-Critical' : '-Active')" />
        </div>

        {{-- ── Row 1: Control Center + Services (matched height) ───────────── --}}
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 items-stretch">
            <div class="min-h-0">
                @livewire(\App\Filament\Widgets\ControlCenterWidget::class)
            </div>
            <div class="min-h-0">
                @livewire(\App\Filament\Widgets\ServicesStatusWidget::class)
            </div>
        </div>

        {{-- ── Row 2: Alerts + Intelligence (matched height) ───────────────── --}}
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 items-stretch">
            <div class="min-h-0">
                @livewire(\App\Filament\Widgets\AlertsOverviewWidget::class)
            </div>
            <div class="min-h-0">
                @livewire(\App\Filament\Widgets\IntelligencePreviewWidget::class)
            </div>
        </div>

        {{-- ── Neural Link Terminal ────────────────────────────────────────── --}}
        <div class="sanaa-dashboard-chat-preview pb-24 sm:pb-28">
            @livewire(\App\Filament\Widgets\TerminalWidget::class)
        </div>

    </div>

    <x-sanaa-command-dock
        class="fixed bottom-0 left-0 right-0 z-40"
        :shell="$shellData"
        :metrics="$systemMetrics"
    />
</x-filament-panels::page>

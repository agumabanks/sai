<x-filament-panels::page class="relative">
    {{-- Ambient macOS Wallpaper Background --}}
    <div class="fixed inset-0 z-0 pointer-events-none w-full h-full overflow-hidden">
        {{-- Deep dark background --}}
        <div class="absolute inset-0 bg-[#000000]"></div>
        {{-- Abstract macOS Monterey/Sonoma style blurs --}}
        <div class="absolute top-[-20%] left-[10%] w-[60vw] h-[60vw] bg-[#5e5ce6]/20 blur-[120px] rounded-[100%] mix-blend-screen opacity-60"></div>
        <div class="absolute bottom-[-10%] right-[-10%] w-[50vw] h-[50vw] bg-[#0a84ff]/15 blur-[100px] rounded-[100%] mix-blend-screen opacity-50"></div>
        <div class="absolute top-[40%] right-[20%] w-[40vw] h-[40vw] bg-[#ff453a]/10 blur-[120px] rounded-[100%] mix-blend-screen opacity-30"></div>
    </div>

    <div class="relative z-10 space-y-4 max-w-[1400px] mx-auto">
        {{-- Hero Section / System Command --}}
        <div class="bg-white/[0.04] dark:bg-[#1c1c1e]/40 backdrop-blur-[40px] backdrop-saturate-[180%] rounded-[32px] xl:rounded-[40px] p-6 lg:p-10 shadow-[0_8px_32px_rgba(0,0,0,0.3)] border border-white/[0.08]">
            
            {{-- Header --}}
            <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-6 mb-10 pb-8 border-b border-white/[0.08]">
                <div class="flex items-center gap-5">
                    <div class="w-14 h-14 rounded-2xl bg-white/10 dark:bg-white/5 border border-white/10 flex items-center justify-center shadow-inner backdrop-blur-xl">
                         <x-sanaa-logo class="w-8 h-8 text-white/90" />
                    </div>
                    <div>
                        <h1 class="text-2xl font-semibold tracking-tight text-white/90 mb-1">
                            Intelligence Command
                        </h1>
                        <p class="text-xs text-white/50 tracking-wide font-medium">
                            Autonomous System Operations & Real-Time Analytics
                        </p>
                    </div>
                </div>

                <div class="flex items-center gap-3">
                    {{-- Overall System Status --}}
                    @php
                        $statusColor = match($systemMetrics['overallStatus'] ?? 'unknown') {
                            'ok' => 'text-[#30d158] bg-[#30d158]/10 border-[#30d158]/20',
                            'warning' => 'text-[#ff9f0a] bg-[#ff9f0a]/10 border-[#ff9f0a]/20',
                            'critical' => 'text-[#ff453a] bg-[#ff453a]/10 border-[#ff453a]/20',
                            default => 'text-white/50 bg-white/5 border-white/10',
                        };
                        $statusDot = match($systemMetrics['overallStatus'] ?? 'unknown') {
                            'ok' => 'bg-[#30d158]',
                            'warning' => 'bg-[#ff9f0a]',
                            'critical' => 'bg-[#ff453a]',
                            default => 'bg-white/50',
                        };
                        $statusLabel = match($systemMetrics['overallStatus'] ?? 'unknown') {
                            'ok' => 'All Systems Nominal',
                            'warning' => 'Warning',
                            'critical' => 'Critical',
                            default => 'Checking...',
                        };
                    @endphp
                    <div class="flex items-center gap-2 px-3.5 py-1.5 rounded-full backdrop-blur-md border {{ $statusColor }}">
                        <div class="relative flex items-center justify-center">
                            @if(($systemMetrics['overallStatus'] ?? 'unknown') !== 'ok')
                                <div class="w-2 h-2 rounded-full {{ $statusDot }} animate-ping absolute opacity-50"></div>
                            @endif
                            <div class="w-2 h-2 rounded-full {{ $statusDot }}"></div>
                        </div>
                        <span class="text-[11px] font-medium tracking-wide uppercase">{{ $statusLabel }}</span>
                    </div>
                    <div class="flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-white/[0.05] border border-white/[0.08] backdrop-blur-md">
                        <span class="text-[11px] font-medium tracking-wide text-white/70 uppercase">{{ strtoupper($systemMetrics['activeBrain'] ?? 'Unknown') }} BRAIN</span>
                    </div>
                </div>
            </div>

            {{-- Metrics Grid - 5 cards --}}
            <div class="grid grid-cols-2 md:grid-cols-5 gap-3">
                {{-- CPU --}}
                @php $cpuColor = ($systemMetrics['cpu'] ?? 0) > 80 ? 'danger' : (($systemMetrics['cpu'] ?? 0) > 60 ? 'warning' : 'success'); @endphp
                <x-metric-card
                    label="CPU"
                    :value="($systemMetrics['cpu'] ?? 0) . '%'"
                    icon="heroicon-m-cpu-chip"
                    :description="($systemMetrics['cpuCores'] ?? 0) . ' cores · load ' . ($systemMetrics['cpuLoad'] ?? 0)"
                    :color="$cpuColor"
                    :trend="($systemMetrics['cpuStatus'] ?? 'ok') === 'ok' ? 'Normal' : 'High'"
                />

                {{-- Memory --}}
                @php $memColor = ($systemMetrics['memory'] ?? 0) > 85 ? 'danger' : (($systemMetrics['memory'] ?? 0) > 70 ? 'warning' : 'info'); @endphp
                <x-metric-card
                    label="Memory"
                    :value="($systemMetrics['memory'] ?? 0) . '%'"
                    icon="heroicon-m-square-3-stack-3d"
                    :description="($systemMetrics['memoryTotal'] ?? 0) . ' GB total'"
                    :color="$memColor"
                    :trend="($systemMetrics['memoryStatus'] ?? 'ok') === 'ok' ? 'Normal' : 'Elevated'"
                />

                {{-- Disk --}}
                <x-metric-card
                    label="Disk"
                    :value="($systemMetrics['disk'] ?? 0) . '%'"
                    icon="heroicon-m-circle-stack"
                    :description="($systemMetrics['diskFree'] ?? 0) . ' GB free'"
                    :color="($systemMetrics['disk'] ?? 0) > 85 ? 'danger' : 'primary'"
                    :trend="($systemMetrics['diskStatus'] ?? 'ok') === 'ok' ? 'Healthy' : 'Low'"
                />

                {{-- Uptime --}}
                <x-metric-card
                    label="Uptime"
                    :value="$systemMetrics['uptime'] ?? 'N/A'"
                    icon="heroicon-m-clock"
                    description="Since last restart"
                    color="success"
                    trend="Stable"
                />

                {{-- Alerts --}}
                @php $alertCount = $systemMetrics['alertCount'] ?? 0; @endphp
                <x-metric-card
                    label="Alerts"
                    :value="(string) $alertCount"
                    icon="heroicon-m-bell-alert"
                    description="Unacknowledged"
                    :color="$alertCount > 10 ? 'danger' : ($alertCount > 0 ? 'warning' : 'success')"
                    :trend="$alertCount === 0 ? 'All Clear' : ($alertCount > 10 ? '-Critical' : '-Active')"
                />
            </div>
        </div>

        {{-- Row 1: Control Center + Services Status --}}
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
            @livewire(\App\Filament\Widgets\ControlCenterWidget::class)
            @livewire(\App\Filament\Widgets\ServicesStatusWidget::class)
        </div>

        {{-- Row 2: Alerts + Intelligence Preview --}}
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
            @livewire(\App\Filament\Widgets\AlertsOverviewWidget::class)
            @livewire(\App\Filament\Widgets\IntelligencePreviewWidget::class)
        </div>

        {{-- Row 3: Activity Feed (full width) --}}
        <div>
            @livewire(\App\Filament\Widgets\SystemActivityWidget::class)
        </div>

        {{-- Row 4: Terminal (full width) --}}
        <div class="pb-8">
            @livewire(\App\Filament\Widgets\TerminalWidget::class)
        </div>
    </div>
</x-filament-panels::page>

<x-filament-panels::page class="relative">
    {{-- Ambient Background --}}
    <div class="fixed inset-0 z-0 pointer-events-none w-full h-full overflow-hidden">
        <div class="absolute inset-0 bg-[#000000]"></div>
        <div class="absolute top-[-20%] left-[10%] w-[60vw] h-[60vw] bg-[#5e5ce6]/15 blur-[140px] rounded-[100%] mix-blend-screen opacity-50"></div>
        <div class="absolute bottom-[-10%] right-[-10%] w-[50vw] h-[50vw] bg-[#0a84ff]/10 blur-[120px] rounded-[100%] mix-blend-screen opacity-40"></div>
    </div>

    <div class="relative z-10 space-y-6 max-w-[1400px] mx-auto">

        {{-- ── Header ──────────────────────────────────────────────────────── --}}
        <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div class="flex items-center gap-4">
                <div class="w-11 h-11 rounded-2xl bg-gradient-to-br from-[#5e5ce6] to-[#0a84ff] flex items-center justify-center shadow-lg shadow-[#5e5ce6]/20">
                    @svg('heroicon-o-server-stack', 'w-6 h-6 text-white')
                </div>
                <div>
                    <h1 class="text-lg font-semibold tracking-tight text-white/95">Tenant Control</h1>
                    <p class="text-[11px] text-white/35 tracking-wide font-medium">Unified Service Management Dashboard</p>
                </div>
            </div>
            <div class="flex items-center gap-2.5 flex-wrap">
                @php
                    $overallStatus = $this->getOverallStatus();
                    $overallScore = $this->getOverallScore();
                    $statusColor = match($overallStatus) {
                        'healthy' => 'text-[#30d158] bg-[#30d158]/10 border-[#30d158]/20',
                        'degraded' => 'text-[#ff9f0a] bg-[#ff9f0a]/10 border-[#ff9f0a]/20',
                        'critical', 'down' => 'text-[#ff453a] bg-[#ff453a]/10 border-[#ff453a]/20',
                        default => 'text-white/50 bg-white/5 border-white/10',
                    };
                    $statusDot = match($overallStatus) {
                        'healthy' => 'bg-[#30d158]',
                        'degraded' => 'bg-[#ff9f0a]',
                        'critical', 'down' => 'bg-[#ff453a]',
                        default => 'bg-white/50',
                    };
                @endphp
                <div class="flex items-center gap-2 px-3 py-1.5 rounded-full backdrop-blur-md border {{ $statusColor }} text-[11px] font-medium tracking-wide uppercase">
                    <div class="relative flex items-center justify-center">
                        @if($overallStatus !== 'healthy')
                            <div class="w-2 h-2 rounded-full {{ $statusDot }} animate-ping absolute opacity-50"></div>
                        @endif
                        <div class="w-2 h-2 rounded-full {{ $statusDot }}"></div>
                    </div>
                    {{ ucfirst($overallStatus) }}
                </div>
                <div class="flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/[0.05] border border-white/[0.08] backdrop-blur-md text-[11px] font-medium text-white/50 uppercase tracking-wide">
                    <span class="w-1.5 h-1.5 rounded-full bg-[#5e5ce6]"></span>
                    Score: {{ number_format($overallScore, 1) }}%
                </div>
                <x-filament::button size="sm" wire:click="refreshData" icon="heroicon-o-arrow-path">
                    Refresh
                </x-filament::button>
            </div>
        </div>

        {{-- ── Summary Metrics ─────────────────────────────────────────────── --}}
        @php $counts = $this->getTenantCounts(); @endphp
        <div class="grid grid-cols-2 md:grid-cols-5 gap-3">
            <x-metric-card
                label="Total Tenants"
                :value="(string) $counts['total']"
                icon="heroicon-m-server-stack"
                description="All services"
                color="primary"
                trend="Managed"
            />
            <x-metric-card
                label="Active"
                :value="(string) $counts['active']"
                icon="heroicon-m-check-circle"
                description="Running"
                color="success"
                trend="Online"
            />
            <x-metric-card
                label="Degraded"
                :value="(string) $counts['degraded']"
                icon="heroicon-m-exclamation-triangle"
                description="Needs attention"
                :color="$counts['degraded'] > 0 ? 'warning' : 'success'"
                :trend="$counts['degraded'] > 0 ? '-Warning' : 'Clear'"
            />
            <x-metric-card
                label="Down"
                :value="(string) $counts['down']"
                icon="heroicon-m-x-circle"
                description="Unreachable"
                :color="$counts['down'] > 0 ? 'danger' : 'success'"
                :trend="$counts['down'] > 0 ? '-Critical' : 'Clear'"
            />
            <x-metric-card
                label="Health Score"
                :value="number_format($overallScore, 0) . '%'"
                icon="heroicon-m-heart"
                description="Overall"
                :color="$overallScore >= 80 ? 'success' : ($overallScore >= 60 ? 'warning' : 'danger')"
                :trend="$overallScore >= 80 ? 'Healthy' : ($overallScore >= 60 ? '-Degraded' : '-Critical')"
            />
        </div>

        {{-- ── Tenant Groups ───────────────────────────────────────────────── --}}
        @foreach($this->getGroupedTenants() as $type => $groupTenants)
            <div class="bg-white/[0.03] backdrop-blur-[40px] rounded-2xl p-5 border border-white/[0.06] shadow-[0_4px_24px_rgba(0,0,0,0.2)]">
                {{-- Group Header --}}
                <div class="flex items-center gap-3 mb-4">
                    <div class="w-9 h-9 rounded-xl bg-gradient-to-br {{ $this->getTypeGradient($type) }} flex items-center justify-center shadow-lg">
                        @svg($this->getTypeIcon($type), 'w-5 h-5 text-white')
                    </div>
                    <div>
                        <h2 class="text-sm font-semibold text-white/90 tracking-tight">{{ $this->getTypeLabel($type) }}</h2>
                        <p class="text-[10px] text-white/35 font-medium">{{ count($groupTenants) }} {{ count($groupTenants) === 1 ? 'service' : 'services' }}</p>
                    </div>
                </div>

                {{-- Tenant Cards Grid --}}
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    @foreach($groupTenants as $tenant)
                        @php
                            $badge = $this->getStatusBadge($tenant['status'] ?? 'inactive');
                            $healthScore = (float) ($tenant['health_score'] ?? 0);
                            $healthColor = $this->getHealthColor($healthScore);
                            $lastChecked = $this->formatLastChecked($tenant['last_checked'] ?? null);
                            $tenantId = (int) ($tenant['id'] ?? 0);
                            $isActive = ($tenant['status'] ?? '') === 'active';
                            $isInactive = ($tenant['status'] ?? '') === 'inactive';
                        @endphp
                        <div class="group bg-white/[0.02] border border-white/[0.06] rounded-xl p-4 hover:bg-white/[0.04] hover:border-white/[0.10] transition-all duration-200">
                            {{-- Card Header: Name + Status --}}
                            <div class="flex items-start justify-between mb-3">
                                <div class="flex-1 min-w-0">
                                    <h3 class="text-sm font-semibold text-white/85 truncate">{{ $tenant['name'] ?? 'Unknown' }}</h3>
                                    <p class="text-[10px] text-white/30 truncate mt-0.5">{{ $tenant['url'] ?? '' }}</p>
                                </div>
                                <div class="flex items-center gap-1.5 px-2 py-0.5 rounded-full border {{ $badge['color'] }} text-[10px] font-medium ml-2 shrink-0">
                                    <div class="w-1.5 h-1.5 rounded-full {{ $badge['dot'] }}"></div>
                                    {{ $badge['label'] }}
                                </div>
                            </div>

                            {{-- Health Score + Last Checked --}}
                            <div class="flex items-center gap-4 mb-3">
                                <div class="flex items-center gap-1.5">
                                    @svg('heroicon-o-heart', 'w-3.5 h-3.5 ' . $healthColor)
                                    <span class="text-xs font-semibold {{ $healthColor }}">{{ number_format($healthScore, 0) }}%</span>
                                    <span class="text-[10px] text-white/25">health</span>
                                </div>
                                <div class="flex items-center gap-1.5">
                                    @svg('heroicon-o-clock', 'w-3.5 h-3.5 text-white/30')
                                    <span class="text-[10px] text-white/40">{{ $lastChecked }}</span>
                                </div>
                            </div>

                            {{-- Action Buttons --}}
                            <div class="flex items-center gap-2 pt-2 border-t border-white/[0.05]">
                                @if($isActive)
                                    <button
                                        wire:click="disableTenant({{ $tenantId }})"
                                        wire:loading.attr="disabled"
                                        class="flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] font-medium bg-[#ff453a]/10 text-[#ff453a] hover:bg-[#ff453a]/20 border border-[#ff453a]/20 transition-colors cursor-pointer"
                                    >
                                        @svg('heroicon-o-pause', 'w-3 h-3')
                                        Disable
                                    </button>
                                @elseif($isInactive)
                                    <button
                                        wire:click="enableTenant({{ $tenantId }})"
                                        wire:loading.attr="disabled"
                                        class="flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] font-medium bg-[#30d158]/10 text-[#30d158] hover:bg-[#30d158]/20 border border-[#30d158]/20 transition-colors cursor-pointer"
                                    >
                                        @svg('heroicon-o-play', 'w-3 h-3')
                                        Enable
                                    </button>
                                @endif
                                <button
                                    wire:click="checkTenant({{ $tenantId }})"
                                    wire:loading.attr="disabled"
                                    class="flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] font-medium bg-[#5e5ce6]/10 text-[#5e5ce6] hover:bg-[#5e5ce6]/20 border border-[#5e5ce6]/20 transition-colors cursor-pointer"
                                >
                                    @svg('heroicon-o-arrow-path', 'w-3 h-3')
                                    Check
                                </button>
                            </div>
                        </div>
                    @endforeach
                </div>
            </div>
        @endforeach

        {{-- ── Empty State ─────────────────────────────────────────────────── --}}
        @if(empty($this->tenants))
            <div class="bg-white/[0.03] backdrop-blur-[40px] rounded-2xl p-12 border border-white/[0.06] text-center">
                @svg('heroicon-o-server-stack', 'w-12 h-12 text-white/20 mx-auto mb-4')
                <h3 class="text-sm font-semibold text-white/60">No Tenants Registered</h3>
                <p class="text-[11px] text-white/30 mt-1">Tenants will appear here once they are added via the API.</p>
            </div>
        @endif

    </div>
</x-filament-panels::page>

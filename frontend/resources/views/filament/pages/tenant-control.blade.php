<x-filament-panels::page class="relative" wire:poll.30s="loadData">
    {{-- Ambient Background --}}
    <div class="fixed inset-0 z-0 pointer-events-none w-full h-full overflow-hidden">
        <div class="absolute inset-0 bg-[#000000]"></div>
        <div class="absolute top-[-20%] left-[10%] w-[60vw] h-[60vw] bg-[#5e5ce6]/15 blur-[140px] rounded-[100%] mix-blend-screen opacity-50"></div>
        <div class="absolute bottom-[-10%] right-[-10%] w-[50vw] h-[50vw] bg-[#0a84ff]/10 blur-[120px] rounded-[100%] mix-blend-screen opacity-40"></div>
    </div>

    <div class="relative z-10 space-y-6 max-w-[1400px] mx-auto">

        {{-- ── Header ──────────────────────────────────────────────────────── --}}
        <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
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
                <x-filament::button size="sm" color="primary" tag="a" href="{{ \App\Filament\Pages\TenantProvisioning::getUrl() }}" icon="heroicon-o-plus">
                    Provision
                </x-filament::button>
            </div>
        </div>

        {{-- ── Controls Bar ────────────────────────────────────────────────── --}}
        <div class="bg-white/[0.03] backdrop-blur-[40px] rounded-2xl p-4 border border-white/[0.06] shadow-[0_4px_24px_rgba(0,0,0,0.2)]">
            <div class="flex flex-col lg:flex-row lg:items-center gap-4 justify-between">
                {{-- Search & Sort --}}
                <div class="flex flex-col sm:flex-row gap-3 flex-1">
                    <div class="relative flex-1 max-w-md">
                        @svg('heroicon-o-magnifying-glass', 'w-4 h-4 text-white/30 absolute left-3 top-1/2 -translate-y-1/2')
                        <input
                            type="text"
                            wire:model.live.debounce.300ms="search"
                            placeholder="Search tenants..."
                            class="w-full pl-9 pr-3 py-2 text-sm bg-white/5 border border-white/10 rounded-lg text-white/80 placeholder-white/30 focus:outline-none focus:ring-2 focus:ring-[#5e5ce6]/50"
                        />
                    </div>
                    <select
                        wire:model.live="sortBy"
                        class="px-3 py-2 text-sm bg-white/5 border border-white/10 rounded-lg text-white/80 focus:outline-none focus:ring-2 focus:ring-[#5e5ce6]/50"
                    >
                        <option value="name_asc">Name A → Z</option>
                        <option value="name_desc">Name Z → A</option>
                        <option value="score_high">Health: High → Low</option>
                        <option value="score_low">Health: Low → High</option>
                        <option value="checked_recent">Last Checked: Recent</option>
                    </select>
                    @if($search !== '' || $statusFilter !== 'all')
                        <button
                            wire:click="clearFilters"
                            class="px-3 py-2 text-sm text-white/50 hover:text-white/80 transition-colors"
                        >
                            Clear
                        </button>
                    @endif
                </div>

                {{-- Status Chips --}}
                <div class="flex items-center gap-2 flex-wrap">
                    @php
                        $chips = [
                            'all' => 'All',
                            'healthy' => 'Healthy',
                            'degraded' => 'Degraded',
                            'down' => 'Down',
                            'inactive' => 'Inactive',
                        ];
                        $chipColors = [
                            'all' => 'text-white/70 bg-white/5 border-white/10',
                            'healthy' => 'text-[#30d158] bg-[#30d158]/10 border-[#30d158]/20',
                            'degraded' => 'text-[#ff9f0a] bg-[#ff9f0a]/10 border-[#ff9f0a]/20',
                            'down' => 'text-[#ff453a] bg-[#ff453a]/10 border-[#ff453a]/20',
                            'inactive' => 'text-white/40 bg-white/5 border-white/10',
                        ];
                        $activeChipColors = [
                            'all' => 'text-white bg-white/20 border-white/30',
                            'healthy' => 'text-[#30d158] bg-[#30d158]/20 border-[#30d158]/40',
                            'degraded' => 'text-[#ff9f0a] bg-[#ff9f0a]/20 border-[#ff9f0a]/40',
                            'down' => 'text-[#ff453a] bg-[#ff453a]/20 border-[#ff453a]/40',
                            'inactive' => 'text-white/60 bg-white/15 border-white/25',
                        ];
                    @endphp
                    @foreach($chips as $key => $label)
                        <button
                            wire:click="$set('statusFilter', '{{ $key }}')"
                            class="px-2.5 py-1 rounded-full text-[11px] font-medium border transition-colors {{ $statusFilter === $key ? $activeChipColors[$key] : $chipColors[$key] }}"
                        >
                            {{ $label }}
                        </button>
                    @endforeach
                </div>
            </div>

            {{-- Bulk Actions Toolbar --}}
            @if(count($selectedTenantIds) > 0)
                <div class="mt-4 pt-4 border-t border-white/[0.06] flex flex-col sm:flex-row sm:items-center gap-3 justify-between">
                    <div class="text-sm text-white/60">
                        <span class="font-medium text-white/90">{{ count($selectedTenantIds) }}</span> tenant(s) selected
                    </div>
                    <div class="flex items-center gap-2 flex-wrap">
                        <x-filament::button size="xs" wire:click="selectAllVisible" color="gray">
                            Select all visible
                        </x-filament::button>
                        <x-filament::button size="xs" wire:click="deselectAll" color="gray">
                            Deselect all
                        </x-filament::button>
                        <x-filament::button size="xs" wire:click="bulkCheck" icon="heroicon-o-arrow-path">
                            Check
                        </x-filament::button>
                        <x-filament::button size="xs" wire:click="bulkEnable" color="success" icon="heroicon-o-play">
                            Enable
                        </x-filament::button>
                        <x-filament::button size="xs" wire:click="bulkDisable" color="danger" icon="heroicon-o-pause">
                            Disable
                        </x-filament::button>
                    </div>
                </div>
            @endif
        </div>

        {{-- ── Summary Metrics ─────────────────────────────────────────────── --}}
        @php $counts = $this->getFilteredTenantCounts(); @endphp
        <div class="grid grid-cols-2 md:grid-cols-5 gap-3">
            <x-metric-card
                label="Total"
                :value="(string) $counts['total']"
                icon="heroicon-m-server-stack"
                description="Matching filters"
                color="primary"
                trend="Managed"
            />
            <x-metric-card
                label="Healthy"
                :value="(string) $counts['healthy']"
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

        {{-- ── Global Actions ──────────────────────────────────────────────── --}}
        <div class="flex items-center justify-between">
            <div class="text-xs text-white/30">
                Auto-refresh every 30s • Last updated {{ now()->format('H:i:s') }}
            </div>
            <x-filament::button size="sm" wire:click="checkAllTenants" icon="heroicon-o-bolt">
                Check All Tenants
            </x-filament::button>
        </div>

        {{-- ── Tenant Groups ───────────────────────────────────────────────── --}}
        @php $grouped = $this->getGroupedTenants(); @endphp
        @foreach($grouped as $type => $groupTenants)
            @php $gCounts = $this->getGroupCounts($groupTenants); @endphp
            <div class="bg-white/[0.03] backdrop-blur-[40px] rounded-2xl p-5 border border-white/[0.06] shadow-[0_4px_24px_rgba(0,0,0,0.2)]">
                {{-- Group Header --}}
                <div class="flex items-center gap-3 mb-4 flex-wrap">
                    <div class="w-9 h-9 rounded-xl bg-gradient-to-br {{ $this->getTypeGradient($type) }} flex items-center justify-center shadow-lg">
                        @svg($this->getTypeIcon($type), 'w-5 h-5 text-white')
                    </div>
                    <div>
                        <h2 class="text-sm font-semibold text-white/90 tracking-tight">{{ $this->getTypeLabel($type) }}</h2>
                        <p class="text-[10px] text-white/35 font-medium">{{ count($groupTenants) }} {{ count($groupTenants) === 1 ? 'service' : 'services' }}</p>
                    </div>
                    <div class="flex items-center gap-2 ml-auto">
                        @if($gCounts['healthy'] > 0)
                            <span class="px-2 py-0.5 rounded-full text-[10px] font-medium text-[#30d158] bg-[#30d158]/10 border border-[#30d158]/20">{{ $gCounts['healthy'] }} healthy</span>
                        @endif
                        @if($gCounts['degraded'] > 0)
                            <span class="px-2 py-0.5 rounded-full text-[10px] font-medium text-[#ff9f0a] bg-[#ff9f0a]/10 border border-[#ff9f0a]/20">{{ $gCounts['degraded'] }} degraded</span>
                        @endif
                        @if($gCounts['down'] > 0)
                            <span class="px-2 py-0.5 rounded-full text-[10px] font-medium text-[#ff453a] bg-[#ff453a]/10 border border-[#ff453a]/20">{{ $gCounts['down'] }} down</span>
                        @endif
                        @if($gCounts['inactive'] > 0)
                            <span class="px-2 py-0.5 rounded-full text-[10px] font-medium text-white/40 bg-white/5 border border-white/10">{{ $gCounts['inactive'] }} inactive</span>
                        @endif
                    </div>
                </div>

                {{-- Tenant Cards Grid --}}
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    @foreach($groupTenants as $tenant)
                        @php
                            $healthStatus = $this->getTenantHealthStatus($tenant);
                            $badge = $this->getStatusBadge($healthStatus);
                            $healthScore = (float) ($tenant['health_score'] ?? 0);
                            $healthColor = $this->getHealthColor($healthScore);
                            $healthStroke = $this->getHealthStrokeColor($healthScore);
                            $lastChecked = $this->formatLastChecked($tenant['last_checked'] ?? null);
                            $tenantId = (int) ($tenant['id'] ?? 0);
                            $isActive = ($tenant['status'] ?? '') === 'active';
                            $isInactive = ($tenant['status'] ?? '') === 'inactive';
                            $isSelected = in_array($tenantId, $selectedTenantIds, true);
                            $circumference = 2 * pi() * 14;
                            $dashOffset = $circumference - (($healthScore / 100) * $circumference);
                        @endphp
                        <div class="group bg-white/[0.02] border border-white/[0.06] rounded-xl p-4 hover:bg-white/[0.04] hover:border-white/[0.10] transition-all duration-200 {{ $isSelected ? 'ring-1 ring-[#5e5ce6]/50' : '' }}">
                            {{-- Card Header: Checkbox + Name + Status --}}
                            <div class="flex items-start justify-between mb-3">
                                <div class="flex items-start gap-2 flex-1 min-w-0">
                                    <input
                                        type="checkbox"
                                        wire:click="toggleSelection({{ $tenantId }})"
                                        {{ $isSelected ? 'checked' : '' }}
                                        class="mt-1 w-4 h-4 rounded border-white/20 bg-white/5 text-[#5e5ce6] focus:ring-[#5e5ce6]/40"
                                    />
                                    <div class="min-w-0">
                                        <button wire:click="openDetail({{ $tenantId }})" class="text-left">
                                            <h3 class="text-sm font-semibold text-white/85 truncate hover:text-[#5e5ce6] transition-colors">{{ $tenant['name'] ?? 'Unknown' }}</h3>
                                        </button>
                                        <p class="text-[10px] text-white/30 truncate mt-0.5">{{ $tenant['url'] ?? '' }}</p>
                                        <p class="text-[10px] text-white/25 mt-1 uppercase tracking-wide">
                                            Lifecycle: {{ ucfirst($tenant['status'] ?? 'inactive') }}
                                        </p>
                                    </div>
                                </div>
                                <div class="flex items-center gap-1.5 px-2 py-0.5 rounded-full border {{ $badge['color'] }} text-[10px] font-medium ml-2 shrink-0">
                                    <div class="w-1.5 h-1.5 rounded-full {{ $badge['dot'] }}"></div>
                                    {{ $badge['label'] }}
                                </div>
                            </div>

                            {{-- Health Score Ring + Last Checked --}}
                            <div class="flex items-center justify-between mb-3">
                                <div class="flex items-center gap-3">
                                    {{-- Circular progress --}}
                                    <div class="relative w-10 h-10">
                                        <svg class="w-10 h-10 -rotate-90" viewBox="0 0 32 32">
                                            <circle cx="16" cy="16" r="14" stroke="rgba(255,255,255,0.08)" stroke-width="3" fill="none" />
                                            <circle
                                                cx="16" cy="16" r="14"
                                                stroke="{{ $healthStroke }}"
                                                stroke-width="3"
                                                fill="none"
                                                stroke-linecap="round"
                                                stroke-dasharray="{{ $circumference }}"
                                                stroke-dashoffset="{{ $dashOffset }}"
                                                class="transition-all duration-500"
                                            />
                                        </svg>
                                        <div class="absolute inset-0 flex items-center justify-center">
                                            <span class="text-[10px] font-bold {{ $healthColor }}">{{ number_format($healthScore, 0) }}</span>
                                        </div>
                                    </div>
                                    <div>
                                        <div class="text-[10px] text-white/25">health</div>
                                        <div class="flex items-center gap-1.5">
                                            @svg('heroicon-o-clock', 'w-3 h-3 text-white/30')
                                            <span class="text-[10px] text-white/40">{{ $lastChecked }}</span>
                                        </div>
                                    </div>
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
                                <button
                                    wire:click="openDetail({{ $tenantId }})"
                                    class="ml-auto flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] font-medium text-white/40 hover:text-white/70 transition-colors"
                                >
                                    Details
                                    @svg('heroicon-o-chevron-right', 'w-3 h-3')
                                </button>
                            </div>
                        </div>
                    @endforeach
                </div>
            </div>
        @endforeach

        {{-- ── Empty State ─────────────────────────────────────────────────── --}}
        @if(empty($grouped))
            <div class="bg-white/[0.03] backdrop-blur-[40px] rounded-2xl p-12 border border-white/[0.06] text-center">
                @svg('heroicon-o-server-stack', 'w-12 h-12 text-white/20 mx-auto mb-4')
                <h3 class="text-sm font-semibold text-white/60">
                    {{ empty($this->tenants) ? 'No Tenants Registered' : 'No tenants match your filters' }}
                </h3>
                <p class="text-[11px] text-white/30 mt-1 max-w-sm mx-auto">
                    {{ empty($this->tenants) ? 'Tenants will appear here once they are added via the API.' : 'Try adjusting your search or status filter to see more results.' }}
                </p>
                @if(!empty($this->tenants) && ($search !== '' || $statusFilter !== 'all'))
                    <x-filament::button size="sm" class="mt-4" wire:click="clearFilters">
                        Clear Filters
                    </x-filament::button>
                @endif
            </div>
        @endif

        {{-- ── Recent Actions ──────────────────────────────────────────────── --}}
        @if(count($actionLog) > 0)
            <div class="bg-white/[0.03] backdrop-blur-[40px] rounded-2xl p-5 border border-white/[0.06] shadow-[0_4px_24px_rgba(0,0,0,0.2)]">
                <h3 class="text-sm font-semibold text-white/80 mb-3">Recent Actions</h3>
                <div class="space-y-2">
                    @foreach(array_slice($actionLog, -5) as $log)
                        <div class="flex items-center justify-between text-xs">
                            <div class="flex items-center gap-2">
                                <span class="px-1.5 py-0.5 rounded text-[10px] font-medium {{ $log['action'] === 'Enable' ? 'text-[#30d158] bg-[#30d158]/10' : 'text-[#ff453a] bg-[#ff453a]/10' }}">
                                    {{ $log['action'] }}
                                </span>
                                <span class="text-white/60">{{ $log['tenant'] }}</span>
                            </div>
                            <span class="text-white/30">{{ $log['time'] }}</span>
                        </div>
                    @endforeach
                </div>
            </div>
        @endif
    </div>

    {{-- ── Detail Modal ────────────────────────────────────────────────── --}}
    <x-filament::modal wire:model="showDetailModal" width="2xl">
        <x-slot name="header">
            <div class="flex items-center gap-3">
                @if($detailTenant)
                    <div class="w-8 h-8 rounded-lg bg-gradient-to-br {{ $this->getTypeGradient($detailTenant['type'] ?? 'other') }} flex items-center justify-center">
                        @svg($this->getTypeIcon($detailTenant['type'] ?? 'other'), 'w-4 h-4 text-white')
                    </div>
                    <div>
                        <h2 class="text-base font-semibold text-white/95">{{ $detailTenant['name'] ?? 'Unknown' }}</h2>
                        <p class="text-[10px] text-white/40">{{ $detailTenant['url'] ?? '' }}</p>
                    </div>
                @else
                    <h2 class="text-base font-semibold text-white/95">Tenant Details</h2>
                @endif
            </div>
        </x-slot>

        @if($detailTenant)
            @php
                $dStatus = $detailTenant['computed_status'] ?? 'unknown';
                $dBadge = $this->getStatusBadge($dStatus);
                $dScore = (float) ($detailTenant['health_score'] ?? 0);
            @endphp
            <div class="space-y-5 text-sm">
                <div class="flex items-center gap-3">
                    <span class="px-2.5 py-1 rounded-full border {{ $dBadge['color'] }} text-[11px] font-medium flex items-center gap-1.5">
                        <span class="w-1.5 h-1.5 rounded-full {{ $dBadge['dot'] }}"></span>
                        {{ $dBadge['label'] }}
                    </span>
                    <span class="text-white/30">|</span>
                    <span class="text-white/60">Health Score: <span class="font-semibold {{ $this->getHealthColor($dScore) }}">{{ number_format($dScore, 0) }}%</span></span>
                </div>

                <div class="grid grid-cols-2 gap-4">
                    <div class="bg-white/5 rounded-lg p-3 border border-white/[0.06]">
                        <div class="text-[10px] text-white/30 uppercase tracking-wide">Tenant ID</div>
                        <div class="text-sm text-white/80 font-medium">#{{ $detailTenant['id'] ?? '-' }}</div>
                    </div>
                    <div class="bg-white/5 rounded-lg p-3 border border-white/[0.06]">
                        <div class="text-[10px] text-white/30 uppercase tracking-wide">Type</div>
                        <div class="text-sm text-white/80 font-medium">{{ $this->getTypeLabel($detailTenant['type'] ?? 'other') }}</div>
                    </div>
                    <div class="bg-white/5 rounded-lg p-3 border border-white/[0.06]">
                        <div class="text-[10px] text-white/30 uppercase tracking-wide">Lifecycle</div>
                        <div class="text-sm text-white/80 font-medium">{{ ucfirst($detailTenant['status'] ?? 'inactive') }}</div>
                    </div>
                    <div class="bg-white/5 rounded-lg p-3 border border-white/[0.06]">
                        <div class="text-[10px] text-white/30 uppercase tracking-wide">Last Checked</div>
                        <div class="text-sm text-white/80 font-medium">{{ $this->formatLastChecked($detailTenant['last_checked'] ?? null) }}</div>
                    </div>
                </div>

                @if(!empty($detailTenant['live_health']))
                    <div>
                        <div class="text-[10px] text-white/30 uppercase tracking-wide mb-2">Live Health Data</div>
                        <pre class="text-xs overflow-auto max-h-[12rem] bg-gray-950 text-green-200 p-4 rounded-lg border border-white/[0.08]">{{ json_encode($detailTenant['live_health'], JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) }}</pre>
                    </div>
                @endif

                <div class="flex items-center gap-2 pt-2">
                    @if(($detailTenant['status'] ?? '') === 'active')
                        <x-filament::button size="sm" color="danger" wire:click="disableTenant({{ $detailTenant['id'] }}); closeDetail()" icon="heroicon-o-pause">
                            Disable
                        </x-filament::button>
                    @else
                        <x-filament::button size="sm" color="success" wire:click="enableTenant({{ $detailTenant['id'] }}); closeDetail()" icon="heroicon-o-play">
                            Enable
                        </x-filament::button>
                    @endif
                    <x-filament::button size="sm" wire:click="checkTenant({{ $detailTenant['id'] }}); closeDetail()" icon="heroicon-o-arrow-path">
                        Check Health
                    </x-filament::button>
                    <x-filament::button size="sm" color="gray" wire:click="closeDetail">
                        Close
                    </x-filament::button>
                </div>
            </div>
        @endif
    </x-filament::modal>
</x-filament-panels::page>

<x-filament-panels::page class="relative" wire:poll.60s="refreshData">
    {{-- Ambient Background --}}
    <div class="fixed inset-0 z-0 pointer-events-none w-full h-full overflow-hidden">
        <div class="absolute inset-0 bg-[#000000]"></div>
        <div class="absolute top-[-20%] left-[10%] w-[60vw] h-[60vw] bg-[#5e5ce6]/15 blur-[140px] rounded-[100%] mix-blend-screen opacity-50"></div>
        <div class="absolute bottom-[-10%] right-[-10%] w-[50vw] h-[50vw] bg-[#ff453a]/10 blur-[120px] rounded-[100%] mix-blend-screen opacity-30"></div>
    </div>

    <div class="relative z-10 space-y-6 max-w-[1400px] mx-auto">

        {{-- ── Header ──────────────────────────────────────────────────────── --}}
        <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
            <div class="flex items-center gap-4">
                <div class="w-11 h-11 rounded-2xl bg-gradient-to-br from-[#5e5ce6] to-[#ff453a] flex items-center justify-center shadow-lg shadow-[#5e5ce6]/20">
                    @svg('heroicon-o-heart', 'w-6 h-6 text-white')
                </div>
                <div>
                    <h1 class="text-lg font-semibold tracking-tight text-white/95">SanaaDoctor</h1>
                    <p class="text-[11px] text-white/35 tracking-wide font-medium">AI-Powered Operations Monitoring</p>
                </div>
            </div>
            <div class="flex items-center gap-2.5 flex-wrap">
                @php
                    $overallStatus = $summary['critical'] > 0 ? 'critical' : ($summary['degraded'] > 0 ? 'degraded' : 'healthy');
                    $statusColor = match($overallStatus) {
                        'healthy' => 'text-[#30d158] bg-[#30d158]/10 border-[#30d158]/20',
                        'degraded' => 'text-[#ff9f0a] bg-[#ff9f0a]/10 border-[#ff9f0a]/20',
                        'critical' => 'text-[#ff453a] bg-[#ff453a]/10 border-[#ff453a]/20',
                    };
                    $statusDot = match($overallStatus) {
                        'healthy' => 'bg-[#30d158]',
                        'degraded' => 'bg-[#ff9f0a]',
                        'critical' => 'bg-[#ff453a]',
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
                <x-filament::button size="sm" wire:click="refreshData" icon="heroicon-o-arrow-path">
                    Refresh
                </x-filament::button>
                <x-filament::button size="sm" wire:click="pollNow" wire:loading.attr="disabled" icon="heroicon-o-play">
                    <span wire:loading.remove wire:target="pollNow">Poll Now</span>
                    <span wire:loading wire:target="pollNow">Polling...</span>
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
                            placeholder="Search apps..."
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

                {{-- Filters --}}
                <div class="flex items-center gap-2 flex-wrap">
                    @php
                        $chips = [
                            'all' => 'All',
                            'healthy' => 'Healthy',
                            'degraded' => 'Degraded',
                            'critical' => 'Critical',
                            'unknown' => 'Not Polled',
                        ];
                        $chipColors = [
                            'all' => 'text-white/70 bg-white/5 border-white/10',
                            'healthy' => 'text-[#30d158] bg-[#30d158]/10 border-[#30d158]/20',
                            'degraded' => 'text-[#ff9f0a] bg-[#ff9f0a]/10 border-[#ff9f0a]/20',
                            'critical' => 'text-[#ff453a] bg-[#ff453a]/10 border-[#ff453a]/20',
                            'unknown' => 'text-white/40 bg-white/5 border-white/10',
                        ];
                        $activeChipColors = [
                            'all' => 'text-white bg-white/20 border-white/30',
                            'healthy' => 'text-[#30d158] bg-[#30d158]/20 border-[#30d158]/40',
                            'degraded' => 'text-[#ff9f0a] bg-[#ff9f0a]/20 border-[#ff9f0a]/40',
                            'critical' => 'text-[#ff453a] bg-[#ff453a]/20 border-[#ff453a]/40',
                            'unknown' => 'text-white/60 bg-white/15 border-white/25',
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

            {{-- Tenant Dropdown --}}
            <div class="mt-4 pt-4 border-t border-white/[0.06] flex flex-col sm:flex-row sm:items-center gap-3">
                <label class="text-sm text-white/50">Tenant filter:</label>
                <select wire:model.live="selectedTenant" class="px-3 py-2 text-sm bg-white/5 border border-white/10 rounded-lg text-white/80 focus:outline-none focus:ring-2 focus:ring-[#5e5ce6]/50">
                    @foreach ($this->tenants as $value => $label)
                        <option value="{{ $value }}">{{ $label }}</option>
                    @endforeach
                </select>
            </div>
        </div>

        {{-- ── Summary Metrics ─────────────────────────────────────────────── --}}
        <div class="grid grid-cols-2 md:grid-cols-5 gap-3">
            <x-metric-card
                label="Total"
                :value="(string) $summary['total']"
                icon="heroicon-m-server-stack"
                description="Monitored"
                color="primary"
                trend="Apps"
            />
            <x-metric-card
                label="Healthy"
                :value="(string) $summary['healthy']"
                icon="heroicon-m-check-circle"
                description="Running"
                color="success"
                trend="Online"
            />
            <x-metric-card
                label="Degraded"
                :value="(string) $summary['degraded']"
                icon="heroicon-m-exclamation-triangle"
                description="Needs attention"
                :color="$summary['degraded'] > 0 ? 'warning' : 'success'"
                :trend="$summary['degraded'] > 0 ? '-Warning' : 'Clear'"
            />
            <x-metric-card
                label="Critical"
                :value="(string) $summary['critical']"
                icon="heroicon-m-x-circle"
                description="Unreachable"
                :color="$summary['critical'] > 0 ? 'danger' : 'success'"
                :trend="$summary['critical'] > 0 ? '-Critical' : 'Clear'"
            />
            <x-metric-card
                label="Not Polled"
                :value="(string) $summary['unknown']"
                icon="heroicon-m-question-mark-circle"
                description="Awaiting check"
                :color="$summary['unknown'] > 0 ? 'warning' : 'success'"
                :trend="$summary['unknown'] > 0 ? '-Pending' : 'Clear'"
            />
        </div>

        {{-- ── App Groups ──────────────────────────────────────────────────── --}}
        @php $grouped = $this->getGroupedApps(); @endphp
        @foreach($grouped as $type => $groupApps)
            @php $gCounts = $this->getGroupCounts($groupApps); @endphp
            <div class="bg-white/[0.03] backdrop-blur-[40px] rounded-2xl p-5 border border-white/[0.06] shadow-[0_4px_24px_rgba(0,0,0,0.2)]">
                {{-- Group Header --}}
                <div class="flex items-center gap-3 mb-4 flex-wrap">
                    <div class="w-9 h-9 rounded-xl bg-gradient-to-br {{ $this->getAppTypeGradient($type) }} flex items-center justify-center shadow-lg">
                        @svg($this->getAppTypeIcon($type), 'w-5 h-5 text-white')
                    </div>
                    <div>
                        <h2 class="text-sm font-semibold text-white/90 tracking-tight">{{ $this->getTypeLabel($type) }}</h2>
                        <p class="text-[10px] text-white/35 font-medium">{{ count($groupApps) }} {{ count($groupApps) === 1 ? 'app' : 'apps' }}</p>
                    </div>
                    <div class="flex items-center gap-2 ml-auto">
                        @if($gCounts['healthy'] > 0)
                            <span class="px-2 py-0.5 rounded-full text-[10px] font-medium text-[#30d158] bg-[#30d158]/10 border border-[#30d158]/20">{{ $gCounts['healthy'] }} healthy</span>
                        @endif
                        @if($gCounts['degraded'] > 0)
                            <span class="px-2 py-0.5 rounded-full text-[10px] font-medium text-[#ff9f0a] bg-[#ff9f0a]/10 border border-[#ff9f0a]/20">{{ $gCounts['degraded'] }} degraded</span>
                        @endif
                        @if($gCounts['critical'] > 0)
                            <span class="px-2 py-0.5 rounded-full text-[10px] font-medium text-[#ff453a] bg-[#ff453a]/10 border border-[#ff453a]/20">{{ $gCounts['critical'] }} critical</span>
                        @endif
                        @if($gCounts['unknown'] > 0)
                            <span class="px-2 py-0.5 rounded-full text-[10px] font-medium text-white/40 bg-white/5 border border-white/10">{{ $gCounts['unknown'] }} pending</span>
                        @endif
                    </div>
                </div>

                {{-- App Cards Grid --}}
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    @foreach($groupApps as $app)
                        @php
                            $healthStatus = $app['status'] ?? 'unknown';
                            $badge = $this->getStatusBadge($healthStatus);
                            $healthScore = $app['score'] ?? null;
                            $healthStroke = $this->getHealthStrokeColor($healthScore);
                            $healthText = $this->getHealthTextColor($healthScore);
                            $lastChecked = $this->formatLastChecked($app['created_at'] ?? null);
                            $hasLog = $app['has_log'] ?? false;
                            $circumference = 2 * pi() * 14;
                            $dashOffset = $circumference - (($healthScore !== null ? $healthScore : 0) / 100 * $circumference);
                        @endphp
                        <div class="group bg-white/[0.02] border border-white/[0.06] rounded-xl p-4 hover:bg-white/[0.04] hover:border-white/[0.10] transition-all duration-200">
                            {{-- Header --}}
                            <div class="flex items-start justify-between mb-3">
                                <div class="flex-1 min-w-0">
                                    <h3 class="text-sm font-semibold text-white/85 truncate">{{ $app['name'] ?? 'Unknown' }}</h3>
                                    <p class="text-[10px] text-white/30 truncate mt-0.5">{{ $app['health_url'] ?? '' }}</p>
                                    @if($app['tenant'] ?? null)
                                        <p class="text-[10px] text-white/25 mt-1">Tenant: {{ $app['tenant'] }}</p>
                                    @endif
                                </div>
                                <div class="flex items-center gap-1.5 px-2 py-0.5 rounded-full border {{ $badge['color'] }} text-[10px] font-medium ml-2 shrink-0">
                                    <div class="relative flex items-center justify-center">
                                        @if($badge['pulse'])
                                            <div class="w-1.5 h-1.5 rounded-full {{ $badge['dot'] }} animate-ping absolute opacity-50"></div>
                                        @endif
                                        <div class="w-1.5 h-1.5 rounded-full {{ $badge['dot'] }}"></div>
                                    </div>
                                    {{ $badge['label'] }}
                                </div>
                            </div>

                            {{-- Health Ring --}}
                            <div class="flex items-center gap-3 mb-3">
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
                                        <span class="text-[10px] font-bold {{ $healthText }}">{{ $healthScore !== null ? number_format($healthScore, 0) : '-' }}</span>
                                    </div>
                                </div>
                                <div>
                                    <div class="text-[10px] text-white/25">health score</div>
                                    <div class="flex items-center gap-1.5">
                                        @svg('heroicon-o-clock', 'w-3 h-3 text-white/30')
                                        <span class="text-[10px] text-white/40">{{ $lastChecked }}</span>
                                    </div>
                                </div>
                            </div>

                            {{-- Action Buttons --}}
                            <div class="flex items-center gap-2 pt-2 border-t border-white/[0.05]">
                                @if($hasLog)
                                    <button
                                        wire:click="openDetail('{{ $app['id'] }}')"
                                        class="flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] font-medium bg-[#5e5ce6]/10 text-[#5e5ce6] hover:bg-[#5e5ce6]/20 border border-[#5e5ce6]/20 transition-colors cursor-pointer"
                                    >
                                        @svg('heroicon-o-eye', 'w-3 h-3')
                                        Details
                                    </button>
                                @else
                                    <span class="text-[10px] text-white/30 italic">Not polled yet</span>
                                @endif
                            </div>
                        </div>
                    @endforeach
                </div>
            </div>
        @endforeach

        {{-- ── Empty State ─────────────────────────────────────────────────── --}}
        @if(empty($grouped))
            <div class="bg-white/[0.03] backdrop-blur-[40px] rounded-2xl p-12 border border-white/[0.06] text-center">
                @svg('heroicon-o-heart', 'w-12 h-12 text-white/20 mx-auto mb-4')
                <h3 class="text-sm font-semibold text-white/60">
                    {{ empty($apps) ? 'No Apps Configured' : 'No apps match your filters' }}
                </h3>
                <p class="text-[11px] text-white/30 mt-1 max-w-sm mx-auto">
                    {{ empty($apps) ? 'Add apps to config/sanaa_apps.php to begin monitoring.' : 'Try adjusting your search or filters to see more results.' }}
                </p>
                @if(!empty($apps) && ($search !== '' || $statusFilter !== 'all'))
                    <x-filament::button size="sm" class="mt-4" wire:click="clearFilters">
                        Clear Filters
                    </x-filament::button>
                @endif
            </div>
        @endif
    </div>

    {{-- ── Detail Modal ────────────────────────────────────────────────── --}}
    <x-filament::modal wire:model="showDetailModal" width="3xl">
        <x-slot name="header">
            <h2 class="text-lg font-semibold text-white/95">Health Log Details</h2>
        </x-slot>

        @if ($selectedLog)
            <div class="space-y-4 text-sm">
                <div class="grid grid-cols-2 gap-4">
                    <div class="bg-white/5 rounded-lg p-3 border border-white/[0.06]">
                        <div class="text-[10px] text-white/30 uppercase tracking-wide">App</div>
                        <div class="text-sm text-white/80 font-medium">{{ $selectedLog['app'] ?? '-' }}</div>
                    </div>
                    <div class="bg-white/5 rounded-lg p-3 border border-white/[0.06]">
                        <div class="text-[10px] text-white/30 uppercase tracking-wide">Tenant</div>
                        <div class="text-sm text-white/80 font-medium">{{ $selectedLog['tenant'] ?? '-' }}</div>
                    </div>
                    <div class="bg-white/5 rounded-lg p-3 border border-white/[0.06]">
                        <div class="text-[10px] text-white/30 uppercase tracking-wide">Score</div>
                        <div class="text-sm text-white/80 font-medium">{{ $selectedLog['score'] ?? 0 }}/100</div>
                    </div>
                    <div class="bg-white/5 rounded-lg p-3 border border-white/[0.06]">
                        <div class="text-[10px] text-white/30 uppercase tracking-wide">Status</div>
                        <div class="text-sm text-white/80 font-medium uppercase">{{ $selectedLog['status'] ?? '-' }}</div>
                    </div>
                    <div class="bg-white/5 rounded-lg p-3 border border-white/[0.06]">
                        <div class="text-[10px] text-white/30 uppercase tracking-wide">Action Taken</div>
                        <div class="text-sm text-white/80 font-medium">{{ $selectedLog['action_taken'] ?? 'none' }}</div>
                    </div>
                    <div class="bg-white/5 rounded-lg p-3 border border-white/[0.06]">
                        <div class="text-[10px] text-white/30 uppercase tracking-wide">Checked At</div>
                        <div class="text-sm text-white/80 font-medium">{{ $selectedLog['created_at'] ?? '-' }}</div>
                    </div>
                </div>

                <div>
                    <div class="text-[10px] text-white/30 uppercase tracking-wide mb-2">Signals</div>
                    <pre class="text-xs overflow-auto max-h-[16rem] bg-gray-950 text-green-200 p-4 rounded-lg border border-white/[0.08]">{{ json_encode($selectedLog['signals'] ?? [], JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) }}</pre>
                </div>

                @if (!empty($selectedLog['groq_diagnosis']))
                    <div>
                        <div class="text-[10px] text-white/30 uppercase tracking-wide mb-2">Groq Diagnosis</div>
                        <div class="bg-white/5 p-3 rounded-lg border border-white/[0.06] text-white/80">{{ $selectedLog['groq_diagnosis'] }}</div>
                    </div>
                @endif

                @if (!empty($selectedLog['heal_response']))
                    <div>
                        <div class="text-[10px] text-white/30 uppercase tracking-wide mb-2">Heal Response</div>
                        <pre class="text-xs overflow-auto max-h-[16rem] bg-gray-950 text-green-200 p-4 rounded-lg border border-white/[0.08]">{{ json_encode($selectedLog['heal_response'], JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) }}</pre>
                    </div>
                @endif
            </div>
        @endif

        <x-slot name="footer">
            <x-filament::button wire:click="closeDetail" color="gray">Close</x-filament::button>
        </x-slot>
    </x-filament::modal>
</x-filament-panels::page>

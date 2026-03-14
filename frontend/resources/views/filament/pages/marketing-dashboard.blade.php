<x-filament-panels::page class="relative">
    {{-- Ambient Background --}}
    <div class="fixed inset-0 z-0 pointer-events-none w-full h-full overflow-hidden">
        <div class="absolute inset-0 bg-[#000000]"></div>
        <div class="absolute top-[-20%] left-[10%] w-[60vw] h-[60vw] bg-[#a855f7]/15 blur-[140px] rounded-[100%] mix-blend-screen opacity-50"></div>
        <div class="absolute bottom-[-10%] right-[-10%] w-[50vw] h-[50vw] bg-[#6366f1]/10 blur-[120px] rounded-[100%] mix-blend-screen opacity-40"></div>
    </div>

    <div class="relative z-10 space-y-6 max-w-[1400px] mx-auto">

        {{-- ── Header ──────────────────────────────────────────────────────── --}}
        <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div class="flex items-center gap-4">
                <div class="w-11 h-11 rounded-2xl bg-gradient-to-br from-[#a855f7] to-[#6366f1] flex items-center justify-center shadow-lg shadow-[#a855f7]/20">
                    @svg('heroicon-o-megaphone', 'w-6 h-6 text-white')
                </div>
                <div>
                    <h1 class="text-lg font-semibold tracking-tight text-white/95">Marketing Dashboard</h1>
                    <p class="text-[11px] text-white/35 tracking-wide font-medium">Campaigns · Social Media · Content Calendar</p>
                </div>
            </div>
            <div class="flex items-center gap-2.5 flex-wrap">
                <div class="flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/[0.05] border border-white/[0.08] backdrop-blur-md text-[11px] font-medium text-white/50 uppercase tracking-wide">
                    <span class="w-1.5 h-1.5 rounded-full bg-[#a855f7]"></span>
                    {{ $this->getActiveCampaigns() }} Active Campaigns
                </div>
                <x-filament::button size="sm" wire:click="refreshData" icon="heroicon-o-arrow-path">
                    Refresh
                </x-filament::button>
            </div>
        </div>

        {{-- ── Campaign Metrics ────────────────────────────────────────────── --}}
        <div>
            <p class="text-[10px] font-semibold tracking-[0.15em] text-white/25 uppercase mb-3">Campaign Metrics</p>
            <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
                <x-metric-card
                    label="Active Campaigns"
                    :value="(string) $this->getActiveCampaigns()"
                    icon="heroicon-m-megaphone"
                    description="Currently running"
                    color="primary"
                    :trend="$this->getActiveCampaigns() > 0 ? 'Active' : 'None'"
                />
                <x-metric-card
                    label="Total Sent"
                    :value="number_format($this->getTotalSent())"
                    icon="heroicon-m-paper-airplane"
                    description="Emails delivered"
                    color="success"
                    trend="Delivered"
                />
                <x-metric-card
                    label="Open Rate"
                    :value="number_format($this->getOpenRate(), 1) . '%'"
                    icon="heroicon-m-envelope-open"
                    description="Email opens"
                    :color="$this->getOpenRate() >= 25 ? 'success' : ($this->getOpenRate() >= 15 ? 'warning' : 'danger')"
                    :trend="$this->getOpenRate() >= 25 ? 'Healthy' : ($this->getOpenRate() >= 15 ? '-Average' : '-Low')"
                />
                <x-metric-card
                    label="Click Rate"
                    :value="number_format($this->getClickRate(), 1) . '%'"
                    icon="heroicon-m-cursor-arrow-rays"
                    description="Link clicks"
                    :color="$this->getClickRate() >= 10 ? 'success' : ($this->getClickRate() >= 5 ? 'info' : 'warning')"
                    :trend="$this->getClickRate() >= 10 ? 'Excellent' : ($this->getClickRate() >= 5 ? 'Good' : '-Below avg')"
                />
            </div>
        </div>

        {{-- ── Social Analytics ────────────────────────────────────────────── --}}
        <div class="bg-white/[0.03] backdrop-blur-[40px] rounded-2xl p-5 border border-white/[0.06] shadow-[0_4px_24px_rgba(0,0,0,0.2)]">
            <div class="flex items-center justify-between mb-4">
                <div class="flex items-center gap-3">
                    <div class="w-9 h-9 rounded-xl bg-gradient-to-br from-[#1DA1F2] to-[#0a84ff] flex items-center justify-center shadow-lg">
                        @svg('heroicon-o-chart-bar', 'w-5 h-5 text-white')
                    </div>
                    <div>
                        <h2 class="text-sm font-semibold text-white/90 tracking-tight">Social Analytics</h2>
                        <p class="text-[10px] text-white/35 font-medium">{{ $this->getTotalPosts() }} total posts across platforms</p>
                    </div>
                </div>
            </div>

            {{-- Platform Breakdown --}}
            @if(!empty($this->getPlatforms()))
                <div class="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
                    @foreach($this->getPlatforms() as $platform => $stats)
                        <div class="bg-white/[0.02] border border-white/[0.06] rounded-xl p-4 hover:bg-white/[0.04] hover:border-white/[0.10] transition-all duration-200">
                            <div class="flex items-center gap-3 mb-3">
                                <div class="w-8 h-8 rounded-lg bg-gradient-to-br {{ $this->getPlatformGradient($platform) }} flex items-center justify-center">
                                    @svg($this->getPlatformIcon($platform), 'w-4 h-4 text-white')
                                </div>
                                <span class="text-xs font-semibold text-white/80 capitalize">{{ $platform }}</span>
                            </div>
                            <div class="flex items-center gap-4">
                                <div>
                                    <span class="text-lg font-semibold text-white/90">{{ ($stats['published'] ?? 0) + ($stats['scheduled'] ?? 0) }}</span>
                                    <p class="text-[10px] text-white/30">Total</p>
                                </div>
                                <div>
                                    <span class="text-sm font-semibold text-[#30d158]">{{ $stats['published'] ?? 0 }}</span>
                                    <p class="text-[10px] text-white/30">Published</p>
                                </div>
                                <div>
                                    <span class="text-sm font-semibold text-[#0a84ff]">{{ $stats['scheduled'] ?? 0 }}</span>
                                    <p class="text-[10px] text-white/30">Scheduled</p>
                                </div>
                            </div>
                        </div>
                    @endforeach
                </div>
            @endif

            {{-- Recent Posts --}}
            @if(!empty($this->getRecentPosts()))
                <div>
                    <p class="text-[10px] font-semibold tracking-[0.15em] text-white/25 uppercase mb-2">Recent Posts</p>
                    <div class="space-y-2">
                        @foreach($this->getRecentPosts() as $post)
                            @php $badge = $this->getStatusBadge($post['status'] ?? 'draft'); @endphp
                            <div class="flex items-center gap-3 bg-white/[0.02] border border-white/[0.05] rounded-lg p-3 hover:bg-white/[0.04] transition-all duration-200">
                                <div class="w-7 h-7 rounded-lg bg-gradient-to-br {{ $this->getPlatformGradient($post['platform'] ?? '') }} flex items-center justify-center shrink-0">
                                    @svg($this->getPlatformIcon($post['platform'] ?? ''), 'w-3.5 h-3.5 text-white')
                                </div>
                                <div class="flex-1 min-w-0">
                                    <p class="text-xs text-white/70 truncate">{{ $post['content'] ?? '' }}</p>
                                    <p class="text-[10px] text-white/30 mt-0.5">{{ $this->formatScheduledTime($post['scheduled_time'] ?? null) }}</p>
                                </div>
                                <div class="flex items-center gap-1.5 px-2 py-0.5 rounded-full border {{ $badge['color'] }} text-[10px] font-medium shrink-0">
                                    <div class="w-1.5 h-1.5 rounded-full {{ $badge['dot'] }}"></div>
                                    {{ $badge['label'] }}
                                </div>
                            </div>
                        @endforeach
                    </div>
                </div>
            @endif

            {{-- Empty State --}}
            @if(empty($this->getPlatforms()) && empty($this->getRecentPosts()))
                <div class="text-center py-8">
                    @svg('heroicon-o-chart-bar', 'w-10 h-10 text-white/15 mx-auto mb-3')
                    <p class="text-xs text-white/40">No social media data available yet.</p>
                    <p class="text-[10px] text-white/25 mt-1">Create and schedule posts using the Social Media skill.</p>
                </div>
            @endif
        </div>

        {{-- ── Content Calendar ────────────────────────────────────────────── --}}
        <div class="bg-white/[0.03] backdrop-blur-[40px] rounded-2xl p-5 border border-white/[0.06] shadow-[0_4px_24px_rgba(0,0,0,0.2)]">
            <div class="flex items-center justify-between mb-4">
                <div class="flex items-center gap-3">
                    <div class="w-9 h-9 rounded-xl bg-gradient-to-br from-[#ff9f0a] to-[#f59e0b] flex items-center justify-center shadow-lg">
                        @svg('heroicon-o-calendar-days', 'w-5 h-5 text-white')
                    </div>
                    <div>
                        <h2 class="text-sm font-semibold text-white/90 tracking-tight">Content Calendar</h2>
                        <p class="text-[10px] text-white/35 font-medium">Upcoming scheduled posts and tasks</p>
                    </div>
                </div>
            </div>

            @if(!empty($this->getUpcomingItems()))
                <div class="space-y-2">
                    @foreach($this->getUpcomingItems() as $item)
                        @php $badge = $this->getStatusBadge($item['status'] ?? 'draft'); @endphp
                        <div class="flex items-center gap-3 bg-white/[0.02] border border-white/[0.05] rounded-lg p-3 hover:bg-white/[0.04] transition-all duration-200">
                            <div class="w-8 h-8 rounded-lg bg-gradient-to-br {{ $this->getPlatformGradient($item['platform'] ?? '') }} flex items-center justify-center shrink-0">
                                @svg($this->getPlatformIcon($item['platform'] ?? ''), 'w-4 h-4 text-white')
                            </div>
                            <div class="flex-1 min-w-0">
                                <p class="text-xs font-medium text-white/80">{{ $item['title'] ?? 'Untitled' }}</p>
                                <div class="flex items-center gap-2 mt-0.5">
                                    <span class="text-[10px] text-white/35 capitalize">{{ $item['type'] ?? '' }}</span>
                                    <span class="text-[10px] text-white/20">·</span>
                                    <span class="text-[10px] text-white/35">{{ $this->formatScheduledTime($item['scheduled_time'] ?? null) }}</span>
                                </div>
                            </div>
                            <div class="flex items-center gap-1.5 px-2 py-0.5 rounded-full border {{ $badge['color'] }} text-[10px] font-medium shrink-0">
                                <div class="w-1.5 h-1.5 rounded-full {{ $badge['dot'] }}"></div>
                                {{ $badge['label'] }}
                            </div>
                        </div>
                    @endforeach
                </div>
            @else
                <div class="text-center py-8">
                    @svg('heroicon-o-calendar-days', 'w-10 h-10 text-white/15 mx-auto mb-3')
                    <p class="text-xs text-white/40">No upcoming content scheduled.</p>
                    <p class="text-[10px] text-white/25 mt-1">Schedule posts and campaigns to see them here.</p>
                </div>
            @endif
        </div>

        {{-- ── Campaign Overview ───────────────────────────────────────────── --}}
        <div class="bg-white/[0.03] backdrop-blur-[40px] rounded-2xl p-5 border border-white/[0.06] shadow-[0_4px_24px_rgba(0,0,0,0.2)]">
            <div class="flex items-center gap-3 mb-4">
                <div class="w-9 h-9 rounded-xl bg-gradient-to-br from-[#6366f1] to-[#a855f7] flex items-center justify-center shadow-lg">
                    @svg('heroicon-o-envelope', 'w-5 h-5 text-white')
                </div>
                <div>
                    <h2 class="text-sm font-semibold text-white/90 tracking-tight">Email Campaign Overview</h2>
                    <p class="text-[10px] text-white/35 font-medium">{{ $this->getTotalCampaigns() }} total campaigns</p>
                </div>
            </div>

            <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div class="bg-white/[0.02] border border-white/[0.06] rounded-xl p-4 text-center">
                    <span class="text-2xl font-semibold text-[#30d158]">{{ $this->getSentCampaigns() }}</span>
                    <p class="text-[10px] text-white/35 mt-1">Sent</p>
                </div>
                <div class="bg-white/[0.02] border border-white/[0.06] rounded-xl p-4 text-center">
                    <span class="text-2xl font-semibold text-[#a855f7]">{{ $this->getActiveCampaigns() }}</span>
                    <p class="text-[10px] text-white/35 mt-1">Active</p>
                </div>
                <div class="bg-white/[0.02] border border-white/[0.06] rounded-xl p-4 text-center">
                    <span class="text-2xl font-semibold text-[#ff9f0a]">{{ $this->getDraftCampaigns() }}</span>
                    <p class="text-[10px] text-white/35 mt-1">Draft</p>
                </div>
                <div class="bg-white/[0.02] border border-white/[0.06] rounded-xl p-4 text-center">
                    <span class="text-2xl font-semibold text-white/60">{{ number_format($this->getBounceRate(), 1) }}%</span>
                    <p class="text-[10px] text-white/35 mt-1">Bounce Rate</p>
                </div>
            </div>
        </div>

    </div>
</x-filament-panels::page>

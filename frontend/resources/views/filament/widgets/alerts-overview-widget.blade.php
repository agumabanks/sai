<x-filament-widgets::widget>
    <div class="relative overflow-hidden bg-white/[0.04] dark:bg-[#1c1c1e]/40 backdrop-blur-[40px] backdrop-saturate-[180%] rounded-[32px] xl:rounded-[40px] p-6 lg:p-10 shadow-[0_8px_32px_rgba(0,0,0,0.3)] border border-white/[0.08]">
        
        <div class="relative z-10 space-y-8">
            {{-- Header --}}
            <div class="flex flex-col sm:flex-row sm:items-center justify-between pb-6 border-b border-white/[0.08] gap-4">
                <div class="flex items-center gap-4">
                    <div class="w-12 h-12 rounded-2xl bg-white/10 dark:bg-white/5 border border-white/10 flex items-center justify-center shadow-inner backdrop-blur-xl {{ $totalCount > 0 ? 'text-[#ff9f0a]' : 'text-[#30d158]' }}">
                        <x-heroicon-m-bell-alert class="w-6 h-6" />
                    </div>
                    <div>
                        <h3 class="text-xl font-medium tracking-tight text-white/95">Watchdog Alerts</h3>
                        <p class="text-[11px] font-medium tracking-wide text-white/50 uppercase mt-0.5">Automated Monitoring</p>
                    </div>
                </div>
                
                @if($totalCount > 0)
                    <div class="flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#ff9f0a]/10 border border-[#ff9f0a]/20">
                        <div class="w-1.5 h-1.5 rounded-full bg-[#ff9f0a] animate-pulse"></div>
                        <span class="text-[11px] font-medium text-[#ff9f0a] tracking-wide">{{ $totalCount }} Active</span>
                    </div>
                @else
                    <div class="flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/[0.05] border border-white/[0.08]">
                        <div class="w-1.5 h-1.5 rounded-full bg-[#30d158]"></div>
                        <span class="text-[11px] font-medium text-white/50 tracking-wide">All Clear</span>
                    </div>
                @endif
            </div>

            {{-- Severity Breakdown --}}
            @if($totalCount > 0)
                <div class="grid grid-cols-4 gap-3 lg:gap-4">
                    @foreach(['critical' => '#ff453a', 'high' => '#ff9f0a', 'warning' => '#ffcc00', 'info' => '#0a84ff'] as $level => $macColorCode)
                        @php
                            $count = $severityCounts[$level] ?? 0;
                        @endphp
                        <div class="flex flex-col items-center justify-center p-3 rounded-2xl bg-white/[0.03] border border-white/[0.05]">
                            <div class="text-[20px] leading-tight font-semibold" style="color: {{ $macColorCode }};">{{ $count }}</div>
                            <div class="text-[10px] font-semibold text-white/40 uppercase tracking-widest mt-1">{{ $level }}</div>
                        </div>
                    @endforeach
                </div>
            @endif

            {{-- Recent Alerts List --}}
            <div class="space-y-3 max-h-[320px] overflow-y-auto scrollbar-thin scrollbar-thumb-white/10 scrollbar-track-transparent pr-2">
                @forelse($alerts as $alert)
                    @php
                        $alertColorCode = match($alert['severity']) {
                            'critical' => '#ff453a',
                            'high' => '#ff9f0a',
                            'warning' => '#ffcc00',
                            default => '#0a84ff',
                        };
                    @endphp
                    <div class="flex items-start gap-4 p-4 rounded-3xl bg-white/[0.02] border border-white/[0.04] transition-colors hover:bg-white/[0.05] group">
                        <div class="w-2.5 h-2.5 rounded-full mt-1.5 shrink-0 shadow-[0_0_8px_rgba(255,255,255,0.2)]" style="background-color: {{ $alertColorCode }}; box-shadow: 0 0 10px {{ $alertColorCode }}80;"></div>
                        <div class="flex-1 min-w-0">
                            <p class="text-[13px] font-medium text-white/90 leading-relaxed">{{ $alert['message'] }}</p>
                            <div class="flex items-center gap-2 mt-2">
                                <span class="text-[10px] font-bold tracking-widest uppercase" style="color: {{ $alertColorCode }};">{{ $alert['severity'] }}</span>
                                <span class="text-white/20 text-[10px]">&bullet;</span>
                                <span class="text-[10px] text-white/50 font-medium tracking-wide">{{ $alert['time']->diffForHumans() }}</span>
                            </div>
                        </div>
                    </div>
                @empty
                    <div class="flex flex-col items-center justify-center py-12 px-6">
                        <div class="w-16 h-16 rounded-full bg-white/5 border border-white/10 flex items-center justify-center mb-6">
                            <x-heroicon-m-shield-check class="w-8 h-8 text-[#30d158] opacity-80" />
                        </div>
                        <p class="text-[15px] font-medium text-white/80 mb-2">No active anomalies</p>
                        <p class="text-[12px] text-white/40 tracking-wide">Continuous deep monitoring active taking place every 120s.</p>
                    </div>
                @endforelse
            </div>
        </div>
    </div>
</x-filament-widgets::widget>

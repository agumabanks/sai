<x-filament-widgets::widget class="h-full">
    <div class="relative overflow-hidden rounded-2xl bg-white/[0.04] backdrop-blur-[40px] p-6 shadow-[0_4px_24px_rgba(0,0,0,0.25)] border border-white/[0.08] h-full">
        <div class="relative z-10 space-y-5">

            {{-- Header --}}
            <div class="flex items-center justify-between">
                <div class="flex items-center gap-3">
                    <div class="w-9 h-9 rounded-xl flex items-center justify-center {{ $totalCount > 0 ? 'bg-[#ff9f0a]/15 border border-[#ff9f0a]/25' : 'bg-[#30d158]/15 border border-[#30d158]/25' }}">
                        <x-heroicon-m-bell-alert class="w-4 h-4 {{ $totalCount > 0 ? 'text-[#ff9f0a]' : 'text-[#30d158]' }}" />
                    </div>
                    <div>
                        <h3 class="text-sm font-semibold text-white/90 tracking-tight">Alerts</h3>
                        <p class="text-[10px] font-medium text-white/40 uppercase tracking-wider">
                            {{ $totalCount > 0 ? $totalCount . ' Active' : 'All Clear' }}
                        </p>
                    </div>
                </div>
                @if($totalCount > 0)
                    <div class="flex items-center gap-2">
                        @foreach(['critical' => '#ff453a', 'high' => '#ff9f0a', 'warning' => '#ffcc00', 'info' => '#0a84ff'] as $level => $color)
                            @if(($severityCounts[$level] ?? 0) > 0)
                                <div class="px-2 py-1 rounded-lg text-[10px] font-semibold" style="background: {{ $color }}15; color: {{ $color }}; border: 1px solid {{ $color }}30;">
                                    {{ $severityCounts[$level] }}
                                </div>
                            @endif
                        @endforeach
                    </div>
                @endif
            </div>

            {{-- Alerts List --}}
            <div class="space-y-2 max-h-[280px] overflow-y-auto pr-1" style="scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent;">
                @forelse($alerts as $alert)
                    @php
                        $alertColor = match($alert['severity']) {
                            'critical' => '#ff453a', 'high' => '#ff9f0a', 'warning' => '#ffcc00', default => '#0a84ff',
                        };
                    @endphp
                    <div class="flex items-start gap-3 py-2.5 px-3 rounded-xl bg-white/[0.02] border border-white/[0.04] hover:bg-white/[0.04] transition-colors">
                        <div class="w-2 h-2 rounded-full mt-1.5 shrink-0" style="background: {{ $alertColor }}; box-shadow: 0 0 8px {{ $alertColor }}60;"></div>
                        <div class="flex-1 min-w-0">
                            <p class="text-[12px] font-medium text-white/80 leading-relaxed">{{ $alert['message'] }}</p>
                            <div class="flex items-center gap-2 mt-1.5">
                                <span class="text-[10px] font-semibold uppercase" style="color: {{ $alertColor }};">{{ $alert['severity'] }}</span>
                                <span class="text-white/15 text-[10px]">&bull;</span>
                                <span class="text-[10px] text-white/40">{{ $alert['time']->diffForHumans() }}</span>
                            </div>
                        </div>
                    </div>
                @empty
                    <div class="flex flex-col items-center justify-center py-8">
                        <div class="w-12 h-12 rounded-full bg-white/5 border border-white/10 flex items-center justify-center mb-4">
                            <x-heroicon-m-shield-check class="w-6 h-6 text-[#30d158] opacity-80" />
                        </div>
                        <p class="text-[13px] font-medium text-white/70 mb-1">No active anomalies</p>
                        <p class="text-[11px] text-white/35">Monitoring every 120 seconds</p>
                    </div>
                @endforelse
            </div>

        </div>
    </div>
</x-filament-widgets::widget>

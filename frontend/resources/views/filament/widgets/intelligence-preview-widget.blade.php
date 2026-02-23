<x-filament-widgets::widget>
    <div class="glass-dark rounded-[32px] p-8 shadow-2xl overflow-hidden relative animate-fade-in">
        <div class="absolute -bottom-32 -right-32 w-64 h-64 bg-sanaa-purple/6 blur-[100px] rounded-full"></div>

        <div class="relative z-10 space-y-6">
            {{-- Header --}}
            <div class="flex items-center justify-between border-b border-white/5 pb-5">
                <div class="flex items-center gap-3">
                    <div class="w-10 h-10 rounded-2xl glass flex items-center justify-center text-sanaa-purple">
                        <x-heroicon-m-eye class="w-5 h-5" />
                    </div>
                    <div>
                        <h3 class="text-sm font-black text-white tracking-tight">Intelligence</h3>
                        <p class="text-[9px] font-bold text-gray-500 uppercase tracking-wider">Briefings & Signals</p>
                    </div>
                </div>
                <a href="{{ url('/intelligence-archive') }}" class="flex items-center gap-1 text-[10px] font-bold text-sanaa-indigo hover:text-sanaa-cyan transition-colors">
                    <span>View All</span>
                    <x-heroicon-m-arrow-right class="w-3 h-3" />
                </a>
            </div>

            {{-- Latest Strategic Signal --}}
            @if($latestSignal)
                <div class="p-4 rounded-2xl border border-sanaa-amber/20 bg-sanaa-amber/5">
                    <div class="flex items-start gap-3">
                        <div class="w-8 h-8 rounded-xl bg-sanaa-amber/10 flex items-center justify-center shrink-0 mt-0.5">
                            <x-heroicon-m-signal class="w-4 h-4 text-sanaa-amber" />
                        </div>
                        <div class="flex-1 min-w-0">
                            <div class="flex items-center gap-2 mb-1">
                                <span class="text-[8px] font-black text-sanaa-amber uppercase tracking-wider">Top Signal</span>
                                <span class="text-[8px] font-bold text-sanaa-amber/60">Score: {{ $latestSignal['score'] }}/10</span>
                            </div>
                            <p class="text-xs font-semibold text-white leading-snug">{{ $latestSignal['title'] }}</p>
                            <p class="text-[9px] text-gray-500 mt-1">{{ $latestSignal['time']->diffForHumans() }}</p>
                        </div>
                    </div>
                </div>
            @endif

            {{-- Latest Briefing --}}
            @if($latestBriefing)
                <div class="space-y-3">
                    <span class="text-[9px] font-bold text-gray-500 uppercase tracking-wider">Latest Briefing</span>
                    <a href="{{ url('/intelligence-archive') }}" class="block p-4 rounded-2xl glass border border-white/5 hover:border-sanaa-indigo/20 transition-all group cursor-pointer">
                        <div class="space-y-2">
                            <h4 class="text-xs font-bold text-white group-hover:text-sanaa-indigo transition-colors">{{ $latestBriefing['title'] }}</h4>
                            <div class="flex items-center gap-3 flex-wrap">
                                <div class="flex items-center gap-1">
                                    <x-heroicon-m-newspaper class="w-3 h-3 text-gray-500" />
                                    <span class="text-[9px] text-gray-400 font-medium">{{ $latestBriefing['articleCount'] }} articles</span>
                                </div>
                                @foreach($latestBriefing['topics'] as $topic)
                                    <span class="px-2 py-0.5 rounded-full bg-sanaa-indigo/10 border border-sanaa-indigo/20 text-[8px] font-bold text-sanaa-indigo uppercase tracking-wider">{{ $topic }}</span>
                                @endforeach
                                <div class="flex items-center gap-1">
                                    <x-heroicon-m-clock class="w-3 h-3 text-gray-500" />
                                    <span class="text-[9px] text-gray-400 font-medium">{{ $latestBriefing['time']->diffForHumans() }}</span>
                                </div>
                            </div>
                        </div>
                    </a>
                </div>
            @endif

            {{-- Stats Row --}}
            <div class="grid grid-cols-2 gap-3 pt-2 border-t border-white/5">
                <div class="text-center p-3 rounded-xl glass border border-white/5">
                    <div class="text-lg font-black text-white">{{ $briefingCount }}</div>
                    <div class="text-[8px] font-bold text-gray-500 uppercase tracking-wider">Recent Briefings</div>
                </div>
                <div class="text-center p-3 rounded-xl glass border border-white/5">
                    <div class="text-lg font-black text-sanaa-amber">{{ $latestSignal['score'] ?? '-' }}</div>
                    <div class="text-[8px] font-bold text-gray-500 uppercase tracking-wider">Signal Score</div>
                </div>
            </div>

            {{-- No data state --}}
            @if(!$latestBriefing && !$latestSignal)
                <div class="text-center py-8">
                    <x-heroicon-m-newspaper class="w-8 h-8 text-sanaa-purple mx-auto mb-2 opacity-50" />
                    <p class="text-xs text-gray-500 font-medium">No intelligence yet</p>
                    <p class="text-[9px] text-gray-600 mt-1">Generate a briefing from the Control Center</p>
                </div>
            @endif
        </div>
    </div>
</x-filament-widgets::widget>

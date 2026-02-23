<x-filament-widgets::widget>
    <div class="glass-dark rounded-[2.5rem] p-8 shadow-2xl overflow-hidden relative animate-fade-in">
        {{-- Background Accent --}}
        <div class="absolute -top-24 -left-24 w-48 h-48 bg-sanaa-cyan/10 blur-[80px] rounded-full"></div>
        
        <div class="relative z-10 space-y-6">
            {{-- Header --}}
            <div class="flex items-center justify-between border-b border-white/5 pb-5">
                <div class="flex items-center gap-3">
                    <div class="w-10 h-10 rounded-2xl glass flex items-center justify-center text-sanaa-cyan">
                        <x-heroicon-m-clock class="w-5 h-5" />
                    </div>
                    <div>
                        <h3 class="text-sm font-black text-white tracking-tight">System Activity</h3>
                        <p class="text-[9px] font-bold text-gray-500 uppercase tracking-wider">Recent Operations</p>
                    </div>
                </div>
                <button wire:click="refreshActivities" class="p-2 rounded-xl glass hover:bg-white/10 transition group">
                    <x-heroicon-m-arrow-path class="w-4 h-4 text-gray-400 group-hover:text-white transition group-hover:rotate-180 duration-500" />
                </button>
            </div>

            {{-- Timeline --}}
            <div class="space-y-0 relative">
                {{-- Timeline Line --}}
                <div class="absolute left-[15px] top-6 bottom-6 w-px bg-gradient-to-b from-sanaa-cyan/50 via-sanaa-purple/30 to-transparent"></div>
                
                @foreach($activities as $index => $activity)
                    <div class="relative pl-12 pb-8 group animate-slide-in-up" style="animation-delay: {{ $index * 100 }}ms">
                        {{-- Timeline Dot --}}
                        <div class="absolute left-0 top-1 w-8 h-8 rounded-xl glass flex items-center justify-center 
                            {{ $activity['status'] === 'success' ? 'text-sanaa-emerald border-sanaa-emerald/20' : '' }}
                            {{ $activity['status'] === 'info' ? 'text-sanaa-indigo border-sanaa-indigo/20' : '' }}
                            {{ $activity['status'] === 'warning' ? 'text-sanaa-amber border-sanaa-amber/20' : '' }}
                            {{ $activity['status'] === 'error' ? 'text-red-500 border-red-500/20' : '' }}
                            group-hover:scale-110 transition-transform duration-300">
                            <x-dynamic-component :component="$activity['icon']" class="w-4 h-4" />
                        </div>

                        {{-- Activity Card --}}
                        <div class="glass rounded-2xl p-4 border border-white/5 group-hover:border-white/10 transition-all cursor-pointer">
                            <div class="space-y-2">
                                <div class="flex items-start justify-between gap-3">
                                    <div class="flex-1 space-y-1">
                                        <h4 class="text-xs font-bold text-white group-hover:text-sanaa-indigo transition-colors">
                                            {{ $activity['title'] }}
                                        </h4>
                                        <p class="text-[10px] text-gray-400 leading-relaxed">
                                            {{ $activity['description'] }}
                                        </p>
                                    </div>
                                    <div class="shrink-0 px-2 py-1 rounded-lg 
                                        {{ $activity['status'] === 'success' ? 'bg-sanaa-emerald/10 border border-sanaa-emerald/20' : '' }}
                                        {{ $activity['status'] === 'info' ? 'bg-sanaa-indigo/10 border border-sanaa-indigo/20' : '' }}
                                        {{ $activity['status'] === 'warning' ? 'bg-sanaa-amber/10 border border-sanaa-amber/20' : '' }}
                                        {{ $activity['status'] === 'error' ? 'bg-red-500/10 border border-red-500/20' : '' }}">
                                        <span class="text-[8px] font-black uppercase tracking-wider
                                            {{ $activity['status'] === 'success' ? 'text-sanaa-emerald' : '' }}
                                            {{ $activity['status'] === 'info' ? 'text-sanaa-indigo' : '' }}
                                            {{ $activity['status'] === 'warning' ? 'text-sanaa-amber' : '' }}
                                            {{ $activity['status'] === 'error' ? 'text-red-500' : '' }}">
                                            {{ $activity['status'] }}
                                        </span>
                                    </div>
                                </div>
                                <div class="flex items-center gap-2 text-[9px] text-gray-600 font-medium">
                                    <x-heroicon-m-clock class="w-3 h-3" />
                                    <span>{{ $activity['time']->diffForHumans() }}</span>
                                </div>
                            </div>
                        </div>
                    </div>
                @endforeach
            </div>

            {{-- View All Link --}}
            <div class="pt-4 border-t border-white/5">
                <a href="#" class="flex items-center justify-center gap-2 text-xs font-bold text-sanaa-indigo hover:text-sanaa-cyan transition-colors group">
                    <span>View Complete Activity Log</span>
                    <x-heroicon-m-arrow-right class="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                </a>
            </div>
        </div>
    </div>
</x-filament-widgets::widget>

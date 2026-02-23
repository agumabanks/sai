<x-filament-panels::page>
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 p-4">
        @forelse($signals as $signal)
            @php
                $color = $this->getSignalColor($signal['classification'] ?? 'market');
                $icon = $this->getSignalIcon($signal['classification'] ?? 'market');
                
                // Apple-inspired colors for accents
                $accentColor = match($color) {
                    'danger' => 'text-[#ff453a]',
                    'success' => 'text-[#30d158]',
                    'info' => 'text-[#0a84ff]',
                    'warning' => 'text-[#ff9f0a]',
                    default => 'text-[#5e5ce6]'
                };
            @endphp
            
            <div class="flex flex-col relative overflow-hidden rounded-3xl bg-white/5 dark:bg-[#1c1c1e]/60 backdrop-blur-3xl backdrop-saturate-150 border border-black/5 dark:border-white/5 transition-transform duration-300 hover:scale-[1.02] shadow-sm">
                <div class="p-6 flex-1 flex flex-col">
                    {{-- Header: Classification & Time --}}
                    <div class="flex items-center justify-between mb-4">
                        <div class="flex items-center gap-2">
                            <x-filament::icon :icon="$icon" class="h-4 w-4 {{ $accentColor }}" />
                            <span class="text-[11px] font-semibold tracking-wide text-zinc-500 dark:text-zinc-400 uppercase">
                                {{ $signal['classification'] ?? 'Signal' }}
                            </span>
                        </div>
                        <span class="text-[11px] text-zinc-400 dark:text-zinc-500">
                            {{ \Carbon\Carbon::parse($signal['created_at'])->diffForHumans(null, true) }}
                        </span>
                    </div>

                    {{-- Title --}}
                    <h3 class="text-lg font-medium tracking-tight text-zinc-900 dark:text-white leading-snug mb-2">
                        {{ $signal['title'] }}
                    </h3>

                    <div class="flex items-center gap-2 mb-4">
                         <span class="text-[11px] font-semibold {{ $accentColor }}">Score {{ $signal['score'] ?? '5' }}/10</span>
                    </div>

                    {{-- Summary (Minimal) --}}
                    <p class="text-sm text-zinc-600 dark:text-zinc-400 line-clamp-3 leading-relaxed mb-6 flex-1">
                        {{ strip_tags($signal['summary']) }}
                    </p>

                    {{-- Impact & Actions --}}
                    <div class="pt-4 border-t border-black/5 dark:border-white/5 mt-auto">
                         <h4 class="text-[10px] font-semibold text-zinc-400 dark:text-zinc-500 uppercase tracking-wide mb-2">Impact Analysis</h4>
                         <p class="text-xs text-zinc-700 dark:text-zinc-300 mb-4">
                             {{ $signal['business_impact'] ?? 'Analysis pending...' }}
                         </p>

                        <div class="flex items-center justify-between">
                            <div class="flex flex-wrap gap-1.5">
                                @foreach(array_slice($signal['tags'] ?? [], 0, 2) as $tag)
                                    <span class="text-[11px] px-2 py-1 rounded-full bg-zinc-100 dark:bg-white/5 text-zinc-500 dark:text-zinc-400">
                                        {{ $tag }}
                                    </span>
                                @endforeach
                            </div>
                            
                            @if($signal['link'])
                                <a href="{{ $signal['link'] }}" target="_blank" class="h-8 w-8 rounded-full flex items-center justify-center bg-zinc-100 dark:bg-white/10 hover:bg-zinc-200 dark:hover:bg-white/20 transition-colors text-zinc-600 dark:text-white">
                                    <x-filament::icon icon="heroicon-m-arrow-top-right-on-square" class="h-4 w-4" />
                                </a>
                            @endif
                        </div>
                    </div>
                </div>
            </div>
        @empty
            <div class="col-span-full py-24 flex flex-col items-center justify-center text-center">
                <div class="h-16 w-16 rounded-full bg-white dark:bg-[#1c1c1e] border border-black/5 dark:border-white/5 flex items-center justify-center mb-6">
                    <x-filament::icon icon="heroicon-o-radar" class="h-8 w-8 text-zinc-400 dark:text-zinc-500" />
                </div>
                <h3 class="text-xl font-medium tracking-tight text-zinc-900 dark:text-white mb-2">No signals on radar</h3>
                <p class="text-sm text-zinc-500 mb-8 max-w-sm">
                    The strategic landscape is currently quiet. Run an extraction scan to aggregate the latest market data.
                </p>
                <div>
                    {{ ($this->getHeaderActions()[1]) }}
                </div>
            </div>
        @endforelse
    </div>
</x-filament-panels::page>

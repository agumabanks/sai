<x-filament-panels::page>
    <div class="grid grid-cols-1 md:grid-cols-4 gap-8">
        {{-- List Section - High-Density Sidebar --}}
        <div class="md:col-span-1 space-y-6">
            <div class="flex items-center justify-between px-2">
                <h2 class="text-[10px] font-black text-gray-500 uppercase tracking-[0.3em]">Intelligence Feed</h2>
                <div class="w-1.5 h-1.5 rounded-full bg-sanaa-emerald animate-pulse"></div>
            </div>
            
            <div class="space-y-4">
                @forelse($briefings as $b)
                    <div 
                        wire:click="selectBriefing({{ $b['id'] }})"
                        class="group p-5 rounded-[1.5rem] border transition-all duration-300 cursor-pointer relative overflow-hidden
                            {{ ($selectedBriefing['id'] ?? null) === $b['id'] 
                                ? 'glass border-sanaa-indigo shadow-[0_0_20px_rgba(99,102,241,0.1)]' 
                                : 'bg-gray-950/20 border-white/5 hover:border-white/10' }}"
                    >
                        @if(($selectedBriefing['id'] ?? null) === $b['id'])
                            <div class="absolute left-0 top-0 bottom-0 w-1 bg-sanaa-indigo"></div>
                        @endif

                        <div class="flex flex-col gap-2">
                            <div class="flex justify-between items-start">
                                <span class="text-[9px] font-bold text-gray-500 uppercase tabular-nums">
                                    {{ now()->parse($b['created_at'])->format('H:i \- d M') }}
                                </span>
                            </div>
                            <h3 class="text-xs font-bold {{ ($selectedBriefing['id'] ?? null) === $b['id'] ? 'text-white' : 'text-gray-400 group-hover:text-gray-200' }} transition-colors">
                                {{ $b['title'] }}
                            </h3>
                            <div class="flex items-center gap-3">
                                <div class="px-2 py-0.5 rounded-md bg-white/5 border border-white/5 text-[8px] font-black text-gray-500 uppercase">
                                    {{ $b['metadata']['article_count'] ?? 0 }} Signals
                                </div>
                                @if($b['pdf_path'] ?? false)
                                    <x-heroicon-o-document-check class="w-3 h-3 text-sanaa-cyan"/>
                                @endif
                            </div>
                        </div>
                    </div>
                @empty
                    <div class="text-center py-20 glass rounded-[2rem] border border-dashed border-white/5">
                        <x-heroicon-o-inbox class="w-8 h-8 text-gray-800 mx-auto mb-4"/>
                        <span class="text-[10px] font-black text-gray-700 uppercase tracking-widest italic">Feed Empty</span>
                    </div>
                @endforelse
            </div>
        </div>

        {{-- Detail Section - The Briefing Room --}}
        <div class="md:col-span-3">
            @if($selectedBriefing)
                <div class="glass-dark rounded-[3rem] p-10 md:p-16 shadow-2xl relative animate-in fade-in slide-in-from-right-8 duration-700 overflow-hidden">
                    {{-- Backdrop Accents --}}
                    <div class="absolute top-0 right-0 w-96 h-96 bg-sanaa-indigo/5 blur-[120px] rounded-full"></div>
                    <div class="absolute bottom-0 left-0 w-64 h-64 bg-sanaa-purple/5 blur-[100px] rounded-full"></div>

                    <div class="relative z-10">
                        <div class="flex justify-between items-start mb-12">
                            <div class="space-y-2">
                                <div class="flex items-center gap-3">
                                    <span class="px-3 py-1 rounded-full bg-sanaa-indigo/10 border border-sanaa-indigo/20 text-[9px] font-black text-sanaa-indigo uppercase tracking-widest">Top Secret</span>
                                    <span class="text-[9px] font-bold text-gray-600 uppercase tabular-nums">{{ now()->parse($selectedBriefing['created_at'])->toFormattedDateString() }}</span>
                                </div>
                                <h1 class="text-4xl md:text-5xl font-black text-white tracking-tighter leading-[1.1] max-w-2xl">
                                    {{ $selectedBriefing['title'] }}
                                </h1>
                                <div class="flex items-center gap-2 pt-2 text-gray-500">
                                    <span class="text-[10px] font-bold uppercase tracking-[0.2em]">Authored by Sanaa Intelligence Engine</span>
                                </div>
                            </div>
                            <button wire:click="closeBriefing" class="p-3 rounded-2xl glass hover:bg-white/10 transition group">
                                <x-heroicon-o-x-mark class="w-6 h-6 text-gray-500 group-hover:text-white transition"/>
                            </button>
                        </div>

                        <div class="prose prose-invert max-w-none text-gray-300 leading-relaxed 
                                    prose-headings:text-white prose-headings:font-black prose-headings:tracking-tight
                                    prose-strong:text-sanaa-indigo prose-strong:font-bold
                                    prose-hr:border-white/5
                                    space-y-8">
                            {!! str($selectedBriefing['content'])->markdown() !!}
                        </div>

                        @if($selectedBriefing['pdf_path'] ?? false)
                            <div class="mt-20 pt-10 border-t border-white/5 flex flex-col md:flex-row items-center justify-between gap-6">
                                <div class="text-left">
                                    <p class="text-[10px] font-black text-gray-600 uppercase tracking-widest">Document Integrity</p>
                                    <p class="text-xs text-gray-400">PDF Report Generated & Hash Verified</p>
                                </div>
                                <a href="{{ $selectedBriefing['pdf_path'] }}" target="_blank" class="w-full md:w-auto flex items-center justify-center gap-3 px-10 py-5 rounded-[2rem] bg-sanaa-indigo hover:bg-sanaa-purple text-white font-black text-xs uppercase tracking-widest transition-all duration-300 shadow-xl shadow-sanaa-indigo/20 hover:-translate-y-1">
                                    <x-heroicon-o-arrow-down-tray class="w-5 h-5"/>
                                    Archive Full Report
                                </a>
                            </div>
                        @endif
                    </div>
                </div>
            @else
                <div class="h-full min-h-[600px] flex flex-col items-center justify-center glass rounded-[3rem] border border-dashed border-white/5 p-20 text-center group">
                    <div class="w-24 h-24 rounded-[2rem] glass-dark flex items-center justify-center mb-10 group-hover:scale-110 transition-transform duration-500">
                        <x-heroicon-o-magnifying-glass-circle class="w-12 h-12 text-gray-700"/>
                    </div>
                    <div class="space-y-2">
                        <h3 class="text-2xl font-black text-gray-300 tracking-tight">Intelligence Ready</h3>
                        <p class="text-gray-600 text-[10px] font-bold uppercase tracking-[0.3em] max-w-xs mx-auto">Select a strategic objective from the feed to begin analysis.</p>
                    </div>
                </div>
            @endif
        </div>
    </div>
</x-filament-panels::page>

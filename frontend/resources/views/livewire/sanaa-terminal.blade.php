<div class="glass-dark rounded-[2rem] p-6 shadow-2xl h-[550px] flex flex-col relative overflow-hidden group">
    {{-- Decorative Background Gradients --}}
    <div class="absolute -top-32 -left-32 w-64 h-64 bg-sanaa-indigo/5 blur-[80px] rounded-full pointer-events-none"></div>
    <div class="absolute -bottom-32 -right-32 w-64 h-64 bg-sanaa-cyan/5 blur-[80px] rounded-full pointer-events-none"></div>

    {{-- Chat Header --}}
    <div class="flex items-center justify-between mb-6 pb-4 border-b border-white/5 relative z-10">
        <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-2xl bg-sanaa-indigo/10 flex items-center justify-center border border-sanaa-indigo/20">
                <x-heroicon-m-sparkles class="w-5 h-5 text-sanaa-indigo"/>
            </div>
            <div>
                <h3 class="text-[10px] font-black text-gray-500 uppercase tracking-[0.2em] mb-0.5">Neural Link</h3>
                <div class="flex items-center gap-1.5">
                    <div class="w-1 h-1 rounded-full bg-sanaa-emerald animate-pulse"></div>
                    <span class="text-[9px] font-bold text-gray-300 uppercase tracking-widest">Sanaa Intelligence v4.0</span>
                </div>
            </div>
        </div>
        <div class="px-3 py-1 rounded-full glass text-[9px] font-bold text-gray-500 uppercase tracking-tighter">
            Bridge: Stable
        </div>
    </div>

    {{-- Chat History --}}
    <div class="flex-1 overflow-y-auto mb-6 space-y-6 pr-2 custom-scrollbar relative z-10" id="terminal-history">
        <div class="flex flex-col items-center py-8 text-center opacity-40">
            <div class="w-px h-12 bg-gradient-to-b from-transparent via-white/10 to-white/10 mb-4"></div>
            <p class="text-[9px] font-black text-gray-600 uppercase tracking-[0.3em]">Communication Initialized</p>
        </div>

        @foreach($history as $index => $entry)
            <div 
                class="flex {{ $entry['type'] === 'user' ? 'justify-end' : 'justify-start' }} animate-in fade-in slide-in-from-bottom-2 duration-500"
                style="animation-delay: {{ $index * 50 }}ms"
            >
                <div class="max-w-[85%] relative group/msg">
                    <div class="flex flex-col {{ $entry['type'] === 'user' ? 'items-end' : 'items-start' }} gap-1 mb-1">
                        <span class="text-[9px] font-black tracking-widest uppercase {{ $entry['type'] === 'user' ? 'text-gray-500' : 'text-sanaa-indigo' }}">
                            {{ $entry['type'] === 'user' ? 'YOU' : 'SANAA AI' }}
                        </span>
                    </div>

                    <div class="rounded-3xl px-5 py-3.5 shadow-xl transition-all duration-300 
                        {{ $entry['type'] === 'user' 
                            ? 'bg-gradient-to-br from-sanaa-indigo to-sanaa-purple text-white rounded-tr-none' 
                            : 'glass-dark border border-white/10 text-gray-200 rounded-tl-none hover:border-sanaa-indigo/30' }}">
                        
                        <div class="prose prose-invert prose-xs max-w-none prose-p:leading-relaxed prose-pre:bg-black/40 prose-pre:border prose-pre:border-white/5">
                            {!! str($entry['text'])->markdown() !!}
                        </div>
                        
                        <div class="flex items-center justify-end gap-2 mt-2 opacity-0 group-hover/msg:opacity-100 transition-opacity">
                            <span class="text-[8px] font-bold text-gray-500 uppercase tabular-nums">
                                {{ $entry['time'] }}
                            </span>
                        </div>
                    </div>
                </div>
            </div>
        @endforeach
    </div>

    {{-- Input Area --}}
    <div class="relative z-10">
        <form wire:submit.prevent="send" class="relative group/input">
            <div class="absolute inset-0 bg-sanaa-indigo/5 rounded-[1.5rem] blur-xl group-focus-within/input:bg-sanaa-indigo/10 transition-all duration-500"></div>
            
            <input 
                type="text" 
                wire:model="command"
                @if($isLoading) disabled @endif
                class="relative w-full glass rounded-[1.5rem] pl-6 pr-14 py-4 text-xs text-white placeholder-gray-600 focus:ring-0 focus:border-sanaa-indigo/50 transition-all shadow-2xl @if($isLoading) opacity-70 @endif"
                placeholder="@if($isLoading) Processing... @else Synchronize command... @endif"
                autofocus
            >
            
            <button 
                type="submit" 
                @if($isLoading) disabled @endif
                class="absolute right-2 top-1/2 -translate-y-1/2 w-10 h-10 rounded-2xl bg-sanaa-indigo flex items-center justify-center text-white shadow-lg shadow-sanaa-indigo/20 hover:scale-110 hover:bg-sanaa-purple transition-all active:scale-95 group/btn @if($isLoading) opacity-50 cursor-not-allowed @endif"
            >
                @if($isLoading)
                    <x-heroicon-m-arrow-path class="w-5 h-5 animate-spin"/>
                @else
                    <x-heroicon-m-bolt class="w-5 h-5 group-hover/btn:animate-pulse"/>
                @endif
            </button>
        </form>
    </div>

    <script>
        document.addEventListener('livewire:initialized', () => {
            Livewire.on('command-sent', () => {
                setTimeout(() => {
                    const history = document.getElementById('terminal-history');
                    history.scrollTo({
                        top: history.scrollHeight,
                        behavior: 'smooth'
                    });
                }, 50);
            });
        });
    </script>

    <style>
        .custom-scrollbar::-webkit-scrollbar { width: 3px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.03); border-radius: 10px; }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.08); }
        
        .prose-xs { font-size: 0.75rem; line-height: 1.6; }
        .prose-xs p { margin-top: 0.5em; margin-bottom: 0.5em; }
    </style>
</div>

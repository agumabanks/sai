<x-filament-widgets::widget>
    <div class="glass-dark rounded-[32px] p-8 shadow-2xl overflow-hidden relative animate-fade-in">
        <div class="absolute -top-32 -right-32 w-64 h-64 bg-emerald-500/6 blur-[100px] rounded-full"></div>

        <div class="relative z-10 space-y-6">
            {{-- Header --}}
            <div class="flex items-center justify-between border-b border-white/5 pb-5">
                <div class="flex items-center gap-3">
                    <div class="w-10 h-10 rounded-xl bg-emerald-500/10 flex items-center justify-center text-emerald-500">
                        <svg class="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/>
                        </svg>
                    </div>
                    <div>
                        <h3 class="text-[15px] font-black text-white tracking-[-0.01em]">WhatsApp</h3>
                        <p class="text-[10px] font-bold text-gray-500 uppercase tracking-[0.12em] mt-0.5">Cloud API</p>
                    </div>
                </div>

                <div class="flex items-center gap-2">
                    @if($status['healthy'] ?? false)
                        <div class="flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/20">
                            <div class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></div>
                            <span class="text-[10px] font-bold text-emerald-500 uppercase tracking-[0.1em]">Live</span>
                        </div>
                    @else
                        <div class="flex items-center gap-2 px-3 py-1.5 rounded-full bg-red-500/10 border border-red-500/20">
                            <div class="w-2 h-2 rounded-full bg-red-500"></div>
                            <span class="text-[10px] font-bold text-red-500 uppercase tracking-[0.1em]">Offline</span>
                        </div>
                    @endif
                    <a href="/whats-app-dashboard" class="p-2 rounded-xl glass hover:glass-light transition group">
                        <x-heroicon-m-arrow-top-right-on-square class="w-4 h-4 text-gray-500 group-hover:text-white transition" />
                    </a>
                </div>
            </div>

            {{-- Quick Status Row --}}
            <div class="grid grid-cols-3 gap-4">
                <div class="p-3 rounded-xl glass border border-white/5 text-center">
                    <p class="text-[9px] font-bold text-gray-500 uppercase tracking-widest">Service</p>
                    <p class="text-sm font-black {{ ($status['running'] ?? false) ? 'text-emerald-400' : 'text-red-400' }} mt-1">
                        {{ ($status['running'] ?? false) ? 'Running' : 'Down' }}
                    </p>
                </div>
                <div class="p-3 rounded-xl glass border border-white/5 text-center">
                    <p class="text-[9px] font-bold text-gray-500 uppercase tracking-widest">Vendor</p>
                    <p class="text-sm font-black {{ !empty($status['vendor_uid'] ?? '') ? 'text-white' : 'text-amber-400' }} mt-1">
                        {{ !empty($status['vendor_uid'] ?? '') ? 'Set' : 'Needed' }}
                    </p>
                </div>
                <div class="p-3 rounded-xl glass border border-white/5 text-center">
                    <p class="text-[9px] font-bold text-gray-500 uppercase tracking-widest">API</p>
                    <p class="text-sm font-black {{ ($status['has_api_token'] ?? false) ? 'text-white' : 'text-amber-400' }} mt-1">
                        {{ ($status['has_api_token'] ?? false) ? 'Active' : 'Needed' }}
                    </p>
                </div>
            </div>

            {{-- Quick Send (collapsed by default) --}}
            <div x-data="{ open: false }">
                <button @click="open = !open" class="w-full flex items-center justify-between p-3 rounded-xl glass border border-white/5 hover:border-emerald-500/20 transition">
                    <div class="flex items-center gap-2">
                        <x-heroicon-m-paper-airplane class="w-4 h-4 text-emerald-500" />
                        <span class="text-xs font-bold text-gray-300">Quick Send</span>
                    </div>
                    <x-heroicon-m-chevron-down class="w-4 h-4 text-gray-500 transition-transform" x-bind:class="open ? 'rotate-180' : ''" />
                </button>

                <div x-show="open" x-transition class="mt-3 space-y-3">
                    <input type="text" wire:model="quickPhone" placeholder="256700123456"
                           class="w-full px-3 py-2.5 rounded-xl glass border border-white/5 focus:border-emerald-500/30 bg-transparent text-white text-xs font-medium placeholder-gray-600 outline-none transition" />
                    <input type="text" wire:model="quickMessage" placeholder="Type a message..."
                           class="w-full px-3 py-2.5 rounded-xl glass border border-white/5 focus:border-emerald-500/30 bg-transparent text-white text-xs font-medium placeholder-gray-600 outline-none transition" />
                    <button wire:click="quickSend"
                            class="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-600 text-white text-[10px] font-black uppercase tracking-widest transition-all">
                        <x-heroicon-m-paper-airplane class="w-3 h-3" />
                        Send
                    </button>
                </div>
            </div>
        </div>
    </div>
</x-filament-widgets::widget>

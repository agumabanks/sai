<div class="relative" x-data="{ open: @entangle('isOpen') }">
    {{-- Trigger Button --}}
    <button
        @click="open = !open"
        class="relative p-2 rounded-lg text-gray-400 hover:text-white hover:bg-white/5 transition-all outline-none focus:outline-none"
    >
        <x-heroicon-m-squares-2x2 class="w-6 h-6" />
    </button>

    {{-- Backdrop --}}
    <div
        x-show="open"
        @click="open = false"
        x-transition:enter="transition ease-out duration-100"
        x-transition:enter-start="opacity-0"
        x-transition:enter-end="opacity-100"
        x-transition:leave="transition ease-in duration-75"
        x-transition:leave-start="opacity-100"
        x-transition:leave-end="opacity-0"
        class="fixed inset-0 z-40 bg-transparent"
        style="display: none;"
    ></div>

    {{-- Dropdown Panel --}}
    <div
        x-show="open"
        x-transition:enter="transition ease-out duration-200"
        x-transition:enter-start="opacity-0 scale-95 translate-y-2"
        x-transition:enter-end="opacity-100 scale-100 translate-y-0"
        x-transition:leave="transition ease-in duration-75"
        x-transition:leave-start="opacity-100 scale-100 translate-y-0"
        x-transition:leave-end="opacity-0 scale-95 translate-y-2"
        x-transition:leave-end="opacity-0 scale-95 translate-y-2"
        class="absolute right-0 top-full mt-2 w-[340px] z-[999] origin-top-right bg-gray-900 rounded-2xl shadow-xl ring-1 ring-white/10"
        style="display: none;"
    >
        <div class="glass-dark rounded-2xl overflow-hidden h-full">
            {{-- Header --}}
            <div class="px-5 py-4 border-b border-white/5 text-center">
                <h3 class="text-sm font-medium text-gray-400">Sanaa Apps</h3>
            </div>

            {{-- Grid --}}
            <div class="grid grid-cols-3 gap-6 p-6">
                {{-- Dashboard --}}
                <a href="#" class="group flex flex-col items-center gap-3">
                    <div class="w-12 h-12 rounded-full bg-[#3B82F6] flex items-center justify-center shadow-lg shadow-blue-900/20 group-hover:scale-110 transition-transform duration-300">
                        <x-heroicon-m-home class="w-6 h-6 text-white" />
                    </div>
                    <span class="text-[11px] font-medium text-gray-400 group-hover:text-white transition-colors">Dashboard</span>
                </a>

                {{-- Institutions --}}
                <a href="#" class="group flex flex-col items-center gap-3">
                    <div class="w-12 h-12 rounded-full bg-[#EF4444] flex items-center justify-center shadow-lg shadow-red-900/20 group-hover:scale-110 transition-transform duration-300">
                        <x-heroicon-m-building-office-2 class="w-6 h-6 text-white" />
                    </div>
                    <span class="text-[11px] font-medium text-gray-400 group-hover:text-white transition-colors">Institutions</span>
                </a>

                {{-- Finance --}}
                <a href="#" class="group flex flex-col items-center gap-3">
                    <div class="w-12 h-12 rounded-full bg-[#22C55E] flex items-center justify-center shadow-lg shadow-green-900/20 group-hover:scale-110 transition-transform duration-300">
                        <x-heroicon-m-currency-dollar class="w-6 h-6 text-white" />
                    </div>
                    <span class="text-[11px] font-medium text-gray-400 group-hover:text-white transition-colors">Finance</span>
                </a>

                {{-- Loans & Credit --}}
                <a href="#" class="group flex flex-col items-center gap-3">
                    <div class="w-12 h-12 rounded-full bg-[#EAB308] flex items-center justify-center shadow-lg shadow-yellow-900/20 group-hover:scale-110 transition-transform duration-300">
                        <x-heroicon-m-credit-card class="w-6 h-6 text-white" />
                    </div>
                    <span class="text-[11px] font-medium text-gray-400 group-hover:text-white transition-colors text-center leading-tight">Loans & Credit</span>
                </a>

                {{-- Core Business --}}
                <a href="#" class="group flex flex-col items-center gap-3">
                    <div class="w-12 h-12 rounded-full bg-[#EC4899] flex items-center justify-center shadow-lg shadow-pink-900/20 group-hover:scale-110 transition-transform duration-300">
                        <x-heroicon-m-briefcase class="w-6 h-6 text-white" />
                    </div>
                    <span class="text-[11px] font-medium text-gray-400 group-hover:text-white transition-colors">Core Business</span>
                </a>

                {{-- System (Active) --}}
                <button wire:click="openModal('brain')" class="group flex flex-col items-center gap-3 relative">
                    <div class="absolute inset-0 bg-[#4F46E5]/20 blur-xl rounded-full"></div>
                    <div class="relative w-12 h-12 rounded-full bg-[#8B5CF6] flex items-center justify-center ring-2 ring-white/20 shadow-lg shadow-purple-900/30 group-hover:scale-110 transition-transform duration-300">
                        <x-heroicon-m-cog-6-tooth class="w-6 h-6 text-white" />
                    </div>
                    <span class="text-[11px] font-bold text-white">System</span>
                </button>
            </div>

            {{-- Footer / Meta --}}
            <div class="px-5 py-3 bg-white/5 border-t border-white/5 flex items-center justify-between">
                <div class="flex items-center gap-2">
                    <div class="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></div>
                    <span class="text-[10px] font-medium text-gray-400">4 Registered venues</span>
                </div>
                <x-heroicon-m-building-storefront class="w-4 h-4 text-blue-400" />
            </div>
        </div>
    </div>
    {{-- ═══ CENTERED MODAL OVERLAY ═══ --}}
    @if($isOpen && $activeModal)
        <div class="fixed inset-0 z-[60] flex items-center justify-center p-4">
            {{-- Modal Backdrop --}}
            <div 
                class="absolute inset-0 bg-sanaa-obsidian/80 backdrop-blur-sm transition-opacity" 
                wire:click="closeModal"
            ></div>

            {{-- Modal Content --}}
            <div class="relative w-full max-w-sm glass-dark rounded-3xl p-6 shadow-2xl animate-modal-in overflow-hidden">
                <div class="absolute -top-32 -right-32 w-64 h-64 bg-sanaa-indigo/20 blur-[80px] rounded-full pointer-events-none"></div>
                
                <div class="relative z-10">
                    {{-- Modal Header --}}
                    <div class="flex items-center justify-between mb-6">
                        <h4 class="text-sm font-black text-white uppercase tracking-wider">
                            {{ match($activeModal) { 'brain' => 'System Status', default => 'App Details' } }}
                        </h4>
                        <button wire:click="closeModal" class="p-2 rounded-xl hover:bg-white/10 text-gray-500 hover:text-white transition">
                            <x-heroicon-m-x-mark class="w-5 h-5"/>
                        </button>
                    </div>

                    {{-- Brain/System Modal --}}
                    @if($activeModal === 'brain')
                        <div class="space-y-4">
                            {{-- Active Provider Card --}}
                            <div class="p-4 rounded-2xl bg-gradient-to-br from-sanaa-indigo/10 to-sanaa-purple/5 border border-sanaa-indigo/20">
                                <div class="flex items-start justify-between mb-2">
                                    <div class="flex items-center gap-2">
                                        <x-heroicon-m-cpu-chip class="w-5 h-5 text-sanaa-indigo"/>
                                        <span class="text-xs font-bold text-sanaa-indigo uppercase tracking-wider">Active Brain</span>
                                    </div>
                                    <div class="flex items-center gap-1.5 px-2 py-1 rounded-md bg-sanaa-emerald/10 border border-sanaa-emerald/20">
                                        <div class="w-1.5 h-1.5 rounded-full bg-sanaa-emerald animate-pulse"></div>
                                        <span class="text-[9px] font-black text-sanaa-emerald uppercase">Online</span>
                                    </div>
                                </div>
                                <div class="mt-2">
                                    <p class="text-lg font-black text-white">{{ $modalData['provider'] ?? 'LOCAL' }}</p>
                                    <p class="text-xs text-gray-500 font-medium mt-0.5">{{ $modalData['model'] ?? 'Unknown Model' }}</p>
                                </div>
                            </div>

                            {{-- Provider Switcher --}}
                            <div class="grid grid-cols-3 gap-3">
                                @foreach(($modalData['providers'] ?? ['LOCAL','GROQ','OPENROUTER']) as $p)
                                    <button 
                                        wire:click="triggerAction('switch brain to {{ strtolower($p) }}', 'Switch to {{ $p }}')" 
                                        class="p-3 rounded-xl flex flex-col items-center gap-2 transition-all border {{ ($modalData['provider'] ?? '') === $p ? 'bg-sanaa-indigo border-sanaa-indigo text-white shadow-lg shadow-sanaa-indigo/25' : 'glass border-white/5 hover:border-white/20 text-gray-400 hover:text-white' }}"
                                    >
                                        @if($p === 'LOCAL') <x-heroicon-m-cpu-chip class="w-5 h-5"/>
                                        @elseif($p === 'GROQ') <x-heroicon-m-bolt class="w-5 h-5"/>
                                        @else <x-heroicon-m-cloud class="w-5 h-5"/>
                                        @endif
                                        <span class="text-[9px] font-bold uppercase tracking-wider">{{ $p }}</span>
                                    </button>
                                @endforeach
                            </div>

                            {{-- Stats Row --}}
                            <div class="grid grid-cols-2 gap-3">
                                <div class="p-3 rounded-xl glass border border-white/5">
                                    <span class="text-[10px] text-gray-500 font-bold uppercase block mb-1">Uptime</span>
                                    <span class="text-sm text-white font-bold">{{ $modalData['uptime'] ?? 'N/A' }}</span>
                                </div>
                                <div class="p-3 rounded-xl glass border border-white/5">
                                    <span class="text-[10px] text-gray-500 font-bold uppercase block mb-1">Latency</span>
                                    <span class="text-sm text-sanaa-emerald font-bold">12ms</span>
                                </div>
                            </div>
                        </div>
                    @endif
                </div>
            </div>
        </div>
    @endif
</div>

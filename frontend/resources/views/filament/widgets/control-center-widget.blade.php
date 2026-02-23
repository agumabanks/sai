<x-filament-widgets::widget>
    <div class="relative overflow-hidden bg-white/[0.04] dark:bg-[#1c1c1e]/40 backdrop-blur-[40px] backdrop-saturate-[180%] rounded-[32px] xl:rounded-[40px] p-6 shadow-[0_8px_32px_rgba(0,0,0,0.3)] border border-white/[0.08]">
        
        <div class="relative z-10 flex flex-col gap-4">
            {{-- Top section: 2 columns --}}
            <div class="grid grid-cols-1 sm:grid-cols-[1.1fr_1fr] gap-3">
                {{-- Left Square: Connectivity block --}}
                <div class="bg-white/[0.06] border border-white/[0.08] rounded-[20px] p-4 flex flex-col gap-3 shadow-sm hover:bg-white/[0.08] transition-colors">
                    {{-- Network / Wi-Fi --}}
                    <div class="flex items-center gap-3">
                        <div class="w-[34px] h-[34px] shrink-0 rounded-full bg-[#0a84ff] flex items-center justify-center text-white shadow-[0_0_12px_rgba(10,132,255,0.4)]">
                            <x-heroicon-s-wifi class="w-[18px] h-[18px]" />
                        </div>
                        <div class="leading-tight flex-1">
                            <div class="text-[13px] font-semibold text-white/95">Network Link</div>
                            <div class="text-[11px] text-white/50 font-medium">Sanaa-Connect-5G</div>
                        </div>
                    </div>
                    
                    {{-- Bluetooth / Devices --}}
                    <div class="flex items-center gap-3">
                        <div class="w-[34px] h-[34px] shrink-0 rounded-full bg-[#0a84ff] flex items-center justify-center text-white shadow-[0_0_12px_rgba(10,132,255,0.4)]">
                            <svg class="w-[18px] h-[18px] fill-current" viewBox="0 0 24 24"><path d="M17.71,7.71L12,2V22L17.71,16.29L13.41,12L17.71,7.71M12,5.83L14.47,8.31L12,10.78V5.83M12,18.17L14.47,15.69L12,13.22V18.17Z" /></svg>
                        </div>
                        <div class="leading-tight flex-1">
                            <div class="text-[13px] font-semibold text-white/95">Local Edge Nodes</div>
                            <div class="text-[11px] text-white/50 font-medium">3 Devices Linked</div>
                        </div>
                    </div>

                    {{-- AirDrop / Neural Link --}}
                    <div class="flex items-center gap-3">
                        <div class="w-[34px] h-[34px] shrink-0 rounded-full bg-[#0a84ff] flex items-center justify-center text-white shadow-[0_0_12px_rgba(10,132,255,0.4)]">
                            <x-heroicon-s-signal class="w-[18px] h-[18px]" />
                        </div>
                        <div class="leading-tight flex-1">
                            <div class="text-[13px] font-semibold text-white/95">Neural Link V4</div>
                            <div class="text-[11px] text-white/50 font-medium">Brain Synced</div>
                        </div>
                    </div>
                </div>

                {{-- Right Top: 3 blocks --}}
                <div class="flex flex-col gap-3">
                    {{-- Focus / Sleep -> Autonomous Healer --}}
                    <button wire:click="toggleHealer" class="bg-white/[0.06] border border-white/[0.08] rounded-[20px] p-3.5 flex items-center gap-3 shadow-sm hover:bg-white/[0.08] transition-colors focus:outline-none">
                        <div class="w-[34px] h-[34px] shrink-0 rounded-full bg-[#5e5ce6] flex items-center justify-center text-white shadow-[0_0_12px_rgba(94,92,230,0.4)]">
                            <x-heroicon-s-moon class="w-[18px] h-[18px]" />
                        </div>
                        <div class="leading-tight text-left">
                            <div class="text-[13px] font-semibold text-white/95">Autonomous Healer</div>
                            <div class="text-[11px] text-white/50 font-medium">On</div>
                        </div>
                    </button>

                    {{-- 2 small squares --}}
                    <div class="grid grid-cols-2 gap-3 flex-1 min-h-0">
                        {{-- Active Brain --}}
                        <div class="bg-white/[0.06] border border-white/[0.08] rounded-[20px] p-3 flex flex-col items-center justify-center gap-2 cursor-pointer hover:bg-white/[0.1] transition-colors shadow-sm">
                            <div class="w-8 h-8 rounded-full bg-white/10 flex items-center justify-center text-white">
                                <x-heroicon-s-cpu-chip class="w-[18px] h-[18px]" />
                            </div>
                            <div class="text-[11px] font-medium text-white/80 text-center leading-tight">Brain<br/>Provider</div>
                        </div>
                        {{-- Intelligence Mode --}}
                        <div class="bg-white/[0.06] border border-white/[0.08] rounded-[20px] p-3 flex flex-col items-center justify-center gap-2 cursor-pointer hover:bg-white/[0.1] transition-colors shadow-sm">
                            <div class="w-8 h-8 rounded-full bg-white/10 flex items-center justify-center text-white">
                                <x-heroicon-s-sparkles class="w-[18px] h-[18px]" />
                            </div>
                            <div class="text-[11px] font-medium text-white/80 text-center leading-tight">Intelligence<br/>Mode</div>
                        </div>
                    </div>
                </div>
            </div>

            {{-- Slider 1: Display Equivalent --}}
            <div class="w-full h-[38px] bg-white/[0.06] border border-white/[0.08] rounded-[14px] relative overflow-hidden shadow-sm">
                <div class="absolute top-0 left-0 bottom-0 bg-white/80 w-[70%] rounded-[14px]"></div>
                <div class="absolute left-3 top-0 bottom-0 flex items-center mix-blend-difference">
                    <x-heroicon-s-sun class="w-[16px] h-[16px] text-white/60" />
                </div>
            </div>

            {{-- Slider 2: Sound Equivalent --}}
            <div class="w-full h-[38px] bg-white/[0.06] border border-white/[0.08] rounded-[14px] relative overflow-hidden shadow-sm">
                <div class="absolute top-0 left-0 bottom-0 bg-white/80 w-[45%] rounded-[14px]"></div>
                <div class="absolute left-3 top-0 bottom-0 flex items-center mix-blend-difference">
                    <x-heroicon-s-speaker-wave class="w-[16px] h-[16px] text-white/60" />
                </div>
            </div>

            {{-- Now Playing Equivalent --}}
            <div class="bg-white/[0.06] border border-white/[0.08] rounded-[20px] p-3.5 flex items-center justify-between shadow-sm hover:bg-white/[0.08] transition-colors cursor-pointer">
                <div class="flex items-center gap-3">
                    <div class="w-[42px] h-[42px] rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-[0_2px_10px_rgba(0,0,0,0.2)]">
                        <x-sanaa-logo class="w-5 h-5 text-white/90" />
                    </div>
                    <div class="leading-tight">
                        <div class="text-[13px] font-semibold text-white/95">Analyzing System Pulse</div>
                        <div class="text-[11px] text-white/50 font-medium mt-0.5">Sanaa Strategic Command</div>
                    </div>
                </div>
                <div class="flex items-center gap-4 text-white/70">
                    <x-heroicon-s-play class="w-[22px] h-[22px] hover:text-white transition-colors" />
                    <x-heroicon-s-forward class="w-[20px] h-[20px] opacity-40 hover:opacity-100 transition-colors" />
                </div>
            </div>
            
            {{-- Extra Bottom Actions --}}
            <div class="flex items-center gap-4 px-1 pb-1">
                <button wire:click="triggerScan" class="w-[34px] h-[34px] rounded-full bg-white/[0.08] border border-white/[0.1] flex items-center justify-center hover:bg-white/[0.15] transition-colors cursor-pointer shadow-sm group">
                    <x-heroicon-s-shield-check class="w-[16px] h-[16px] text-white/80 group-hover:text-white" />
                </button>
                <button wire:click="triggerBriefing" class="w-[34px] h-[34px] rounded-full bg-white/[0.08] border border-white/[0.1] flex items-center justify-center hover:bg-white/[0.15] transition-colors cursor-pointer shadow-sm group">
                    <x-heroicon-s-newspaper class="w-[16px] h-[16px] text-white/80 group-hover:text-white" />
                </button>
            </div>
            
        </div>
    </div>
</x-filament-widgets::widget>

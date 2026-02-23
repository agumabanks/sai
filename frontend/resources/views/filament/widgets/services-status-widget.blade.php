<x-filament-widgets::widget>
    <div class="relative overflow-hidden bg-white/[0.04] dark:bg-[#1c1c1e]/40 backdrop-blur-[40px] backdrop-saturate-[180%] rounded-[32px] xl:rounded-[40px] p-6 lg:p-8 shadow-[0_8px_32px_rgba(0,0,0,0.3)] border border-white/[0.08] flex flex-col">
        
        <div class="relative z-10 flex flex-col flex-1">
            
            {{-- Header with Toggle --}}
            <div class="flex items-center justify-between pb-3">
                <div class="flex flex-col">
                    <h2 class="text-[22px] font-semibold tracking-tight text-white/95">Local Devices</h2>
                </div>
                {{-- Apple styled toggle --}}
                <div class="w-[50px] h-[30px] rounded-full bg-[#30d158] relative shadow-[inset_0_2px_4px_rgba(0,0,0,0.2)] cursor-pointer">
                    <div class="absolute top-[2px] right-[2px] w-[26px] h-[26px] bg-white rounded-full shadow-[0_2px_5px_rgba(0,0,0,0.3)] border border-black/5"></div>
                </div>
            </div>

            {{-- Description text --}}
            <div class="border-b border-white/[0.08] pb-5 mb-5">
                <p class="text-[13px] text-white/60 leading-relaxed font-medium">
                    Connect to edge nodes, local brain clusters, and external data sources. <a href="#" class="text-[#0a84ff] hover:underline">Learn more...</a>
                </p>
                <p class="text-[13px] text-white/60 leading-relaxed mt-4 font-medium">
                    This Intelligence Core is discoverable as "ai.sanaa.co" while Local Devices is open.
                </p>
            </div>

            {{-- My Devices Section --}}
            <div class="flex flex-col flex-1">
                <h3 class="text-[13px] font-bold text-white/80 mb-3 px-1">My Devices</h3>
                
                {{-- Devices List (Container mimicking Apple Settings grouped list) --}}
                <div class="bg-white/5 border border-white/[0.08] rounded-[16px] overflow-hidden flex flex-col">
                    
                    {{-- Device 1 --}}
                    <div class="flex items-center justify-between p-3 border-b border-white/[0.05] hover:bg-white/[0.04] transition-colors cursor-pointer group">
                        <div class="flex items-center gap-4">
                            <x-heroicon-s-server-stack class="w-6 h-6 text-white/80 pl-1" />
                            <div class="leading-tight">
                                <div class="text-[14px] font-medium text-white/95">Sanaa Mainframe Cluster</div>
                                <div class="text-[12px] text-white/50">Connected</div>
                            </div>
                        </div>
                        <div class="w-6 h-6 rounded-full border border-white/20 flex items-center justify-center text-white/50 hover:bg-white/10 hover:text-white transition-colors">
                            <span class="text-[12px] font-serif italic font-bold">i</span>
                        </div>
                    </div>

                    {{-- Device 2 --}}
                    <div class="flex items-center justify-between p-3 border-b border-white/[0.05] hover:bg-white/[0.04] transition-colors cursor-pointer group">
                        <div class="flex items-center gap-4">
                            <x-heroicon-s-cpu-chip class="w-6 h-6 text-white/80 pl-1" />
                            <div class="leading-tight">
                                <div class="text-[14px] font-medium text-white/95">Local NPU Node (Groq)</div>
                                <div class="text-[12px] text-white/50">Connected</div>
                            </div>
                        </div>
                        <div class="w-6 h-6 rounded-full border border-white/20 flex items-center justify-center text-white/50 hover:bg-white/10 hover:text-white transition-colors">
                            <span class="text-[12px] font-serif italic font-bold">i</span>
                        </div>
                    </div>

                    {{-- Device 3 --}}
                    <div class="flex items-center justify-between p-3 hover:bg-white/[0.04] transition-colors cursor-pointer">
                        <div class="flex items-center gap-4">
                            <x-heroicon-s-circle-stack class="w-6 h-6 text-white/80 pl-1" />
                            <div class="leading-tight">
                                <div class="text-[14px] font-medium text-white/95">Vector DB Replica</div>
                                <div class="text-[12px] text-[#ff9f0a]">Syncing...</div>
                            </div>
                        </div>
                        <div class="w-6 h-6 rounded-full border border-white/20 flex items-center justify-center text-white/50 hover:bg-white/10 hover:text-white transition-colors">
                            <span class="text-[12px] font-serif italic font-bold">i</span>
                        </div>
                    </div>
                </div>
            </div>

            {{-- Nearby Devices Section --}}
            <div class="mt-6 flex flex-col">
                <div class="flex items-center justify-between mb-3 px-1">
                    <h3 class="text-[13px] font-bold text-white/80">Nearby Devices</h3>
                    <x-heroicon-o-arrow-path class="w-4 h-4 text-white/50 animate-spin" />
                </div>
                
                <div class="bg-white/[0.02] border border-white/[0.04] rounded-[12px] p-4 flex items-center justify-center">
                    <span class="text-[13px] text-white/40 font-medium">Searching...</span>
                </div>
            </div>
            
        </div>
    </div>
</x-filament-widgets::widget>

<x-filament-widgets::widget class="h-full">
    <div class="relative overflow-hidden rounded-2xl bg-white/[0.04] backdrop-blur-[40px] p-6 shadow-[0_4px_24px_rgba(0,0,0,0.25)] border border-white/[0.08] h-full flex flex-col">
        <div class="relative z-10 space-y-5 flex-1 flex flex-col">

            <div class="flex items-center justify-between gap-3">
                <div class="flex items-center gap-3">
                    <div class="w-9 h-9 rounded-xl bg-[#5e5ce6]/15 border border-[#5e5ce6]/25 flex items-center justify-center">
                        <x-heroicon-m-command-line class="w-4 h-4 text-[#5e5ce6]" />
                    </div>
                    <div>
                        <h3 class="text-sm font-semibold text-white/90 tracking-tight">Control Center</h3>
                        <p class="text-[10px] font-medium text-white/40 uppercase tracking-wider">System toggles & actions</p>
                    </div>
                </div>
                <div class="flex items-center gap-2 text-[10px] text-white/45">
                    <span>CPU {{ $metrics['cpu'] ?? 0 }}%</span>
                    <span>·</span>
                    <span>RAM {{ $metrics['memory'] ?? 0 }}%</span>
                    <span>·</span>
                    <span>{{ $metrics['alerts'] ?? 0 }} alerts</span>
                </div>
            </div>

            <div class="space-y-2">
                <p class="text-[10px] font-semibold text-white/40 uppercase tracking-widest">Active Brain</p>
                <div class="flex flex-wrap items-center gap-2">
                    <button
                        wire:click="switchProvider('groq')"
                        class="px-3 py-1.5 rounded-xl text-[11px] font-semibold tracking-wide transition-all duration-200 bg-[#5e5ce6]/20 border border-[#5e5ce6]/40 text-[#a5a3ff] shadow-[0_0_12px_rgba(94,92,230,0.15)]"
                    >
                        {{ strtoupper($currentProvider) }}
                    </button>
                    <span class="px-2.5 py-1 rounded-full border border-[#30d158]/20 bg-[#30d158]/10 text-[10px] font-bold uppercase tracking-wider text-[#30d158]">
                        Online
                    </span>
                </div>
            </div>

            @if(!empty($quickLaunch))
                <div class="space-y-2">
                    <p class="text-[10px] font-semibold text-white/40 uppercase tracking-widest">Shortcuts</p>
                    <div class="flex flex-wrap gap-2">
                        @foreach($quickLaunch as $shortcut)
                            <a
                                href="{{ ($shortcut['external'] ?? false) ? ($shortcut['url'] ?? '#') : ($shortcut['url'] ?? url('/')) }}"
                                class="px-2.5 py-1 rounded-full border border-white/10 bg-white/[0.04] text-[10px] font-semibold text-white/70 hover:text-white/95 hover:bg-white/[0.08] transition"
                                @if($shortcut['external'] ?? false) target="_blank" rel="noopener" @endif
                            >
                                {{ $shortcut['label'] }}
                            </a>
                        @endforeach
                    </div>
                </div>
            @endif

            <div class="grid grid-cols-2 gap-3">
                @foreach(($controlCenter['modules'] ?? []) as $module)
                    @if(($module['action'] ?? null) === 'scan')
                        <button wire:click="triggerScan" class="flex items-center gap-3 p-3.5 rounded-xl bg-white/[0.04] border border-white/[0.06] hover:bg-white/[0.08] hover:border-white/[0.12] transition-all group text-left">
                            <div class="w-8 h-8 rounded-lg bg-[#30d158]/10 border border-[#30d158]/20 flex items-center justify-center">
                                <x-heroicon-m-shield-check class="w-4 h-4 text-[#30d158]" />
                            </div>
                            <div>
                                <div class="text-[12px] font-semibold text-white/80 group-hover:text-white/95">{{ $module['label'] }}</div>
                                <div class="text-[10px] text-white/35">Audit platform</div>
                            </div>
                        </button>
                    @elseif(($module['action'] ?? null) === 'briefing')
                        <button wire:click="triggerBriefing" class="flex items-center gap-3 p-3.5 rounded-xl bg-white/[0.04] border border-white/[0.06] hover:bg-white/[0.08] hover:border-white/[0.12] transition-all group text-left">
                            <div class="w-8 h-8 rounded-lg bg-[#0a84ff]/10 border border-[#0a84ff]/20 flex items-center justify-center">
                                <x-heroicon-m-newspaper class="w-4 h-4 text-[#0a84ff]" />
                            </div>
                            <div>
                                <div class="text-[12px] font-semibold text-white/80 group-hover:text-white/95">{{ $module['label'] }}</div>
                                <div class="text-[10px] text-white/35">Generate report</div>
                            </div>
                        </button>
                    @elseif(!empty($module['url']))
                        <a href="{{ $module['url'] }}" class="flex items-center gap-3 p-3.5 rounded-xl bg-white/[0.04] border border-white/[0.06] hover:bg-white/[0.08] hover:border-white/[0.12] transition-all group">
                            <div class="w-8 h-8 rounded-lg bg-[#a855f7]/10 border border-[#a855f7]/20 flex items-center justify-center">
                                <x-heroicon-m-squares-2x2 class="w-4 h-4 text-[#a855f7]" />
                            </div>
                            <div>
                                <div class="text-[12px] font-semibold text-white/80 group-hover:text-white/95">{{ $module['label'] }}</div>
                                <div class="text-[10px] text-white/35">Open module</div>
                            </div>
                        </a>
                    @endif
                @endforeach
            </div>

            <div class="mt-auto pt-2 flex items-center gap-2">
                <a href="{{ url('/') }}" target="_blank" rel="noopener" class="flex-1 text-center px-3 py-2 rounded-xl border border-white/10 bg-white/[0.03] text-[11px] font-semibold text-white/70 hover:text-white/95 hover:bg-white/[0.07] transition">
                    Open Sanaa OS
                </a>
                <a href="{{ route('filament.admin.pages.ai-brain-settings') }}" class="flex-1 text-center px-3 py-2 rounded-xl border border-white/10 bg-white/[0.03] text-[11px] font-semibold text-white/70 hover:text-white/95 hover:bg-white/[0.07] transition">
                    Settings
                </a>
            </div>

        </div>
    </div>
</x-filament-widgets::widget>
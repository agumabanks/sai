<x-filament-widgets::widget class="fi-wi-brain-insights">

    <div class="p-4 space-y-3">

        {{-- Header --}}
        <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
                <x-heroicon-o-cpu-chip class="w-5 h-5 text-[#0a84ff]" />
                <span class="text-sm font-semibold text-white">SanaaBrain Intelligence</span>
            </div>
            <button wire:click="refresh"
                    class="text-xs text-white/30 hover:text-white/60 transition flex items-center gap-1">
                <x-heroicon-o-arrow-path class="w-3 h-3" wire:loading.class="animate-spin" wire:target="refresh" />
                Refresh
            </button>
        </div>

        @if ($error)
            <p class="text-xs text-[#ff453a]">{{ $error }}</p>
        @else

        {{-- 4 Stat Cards --}}
        <div class="grid grid-cols-2 gap-3">

            {{-- Memories Stored --}}
            <div class="p-3 rounded-xl bg-white/3 border border-white/8">
                <p class="text-2xl font-bold text-white">{{ number_format($totalMemories) }}</p>
                <p class="text-xs text-white/40 mt-0.5">Memories Stored</p>
                <div class="mt-1 flex items-center gap-1">
                    <x-heroicon-o-cpu-chip class="w-3 h-3 text-[#0a84ff]" />
                    <span class="text-xs text-[#0a84ff]">Active brain</span>
                </div>
            </div>

            {{-- Auto-Learned Today --}}
            <div class="p-3 rounded-xl bg-white/3 border border-white/8">
                <p class="text-2xl font-bold {{ $learnedToday > 0 ? 'text-[#30d158]' : 'text-white/40' }}">
                    {{ $learnedToday }}
                </p>
                <p class="text-xs text-white/40 mt-0.5">Auto-Learned Today</p>
                @if ($lastLearnedAt)
                    <p class="text-xs text-white/25 mt-1">Last: {{ $lastLearnedAt }}</p>
                @else
                    <p class="text-xs text-white/25 mt-1">No learning yet</p>
                @endif
            </div>

            {{-- LLM Cost Today --}}
            <div class="p-3 rounded-xl bg-white/3 border border-white/8">
                <p class="text-2xl font-bold {{ $llmCostToday > 0.10 ? 'text-[#ff9f0a]' : 'text-white' }}">
                    ${{ number_format($llmCostToday, 4) }}
                </p>
                <p class="text-xs text-white/40 mt-0.5">LLM Cost (Today)</p>
                <div class="mt-1 flex items-center gap-1">
                    <x-heroicon-o-banknotes class="w-3 h-3 text-white/30" />
                    <span class="text-xs text-white/25">USD</span>
                </div>
            </div>

            {{-- Active Issues --}}
            <div class="p-3 rounded-xl bg-white/3 border border-white/8">
                <p class="text-2xl font-bold {{ $activeIssues > 0 ? 'text-[#ff453a]' : 'text-[#30d158]' }}">
                    {{ $activeIssues }}
                </p>
                <p class="text-xs text-white/40 mt-0.5">Active Issues</p>
                <div class="mt-1 flex items-center gap-1">
                    @if ($activeIssues > 0)
                        <x-heroicon-o-exclamation-triangle class="w-3 h-3 text-[#ff453a]" />
                        <span class="text-xs text-[#ff453a]">Health &lt; 70</span>
                    @else
                        <x-heroicon-o-check-circle class="w-3 h-3 text-[#30d158]" />
                        <span class="text-xs text-[#30d158]">All healthy</span>
                    @endif
                </div>
            </div>

        </div>

        {{-- Quick link --}}
        <a href="{{ route('filament.admin.pages.sanaa-brain') }}"
           class="flex items-center justify-center gap-1.5 w-full py-1.5 rounded-lg bg-[#0a84ff]/10 hover:bg-[#0a84ff]/20 border border-[#0a84ff]/20 text-[#0a84ff] text-xs font-medium transition">
            <x-heroicon-o-arrow-right class="w-3.5 h-3.5" />
            Open SanaaBrain
        </a>

        @endif

    </div>

</x-filament-widgets::widget>

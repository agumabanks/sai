<x-filament-panels::page class="relative">
    <div class="relative z-10 space-y-5 max-w-[1280px] mx-auto">

        {{-- ── Header ──────────────────────────────────────────────────────── --}}
        <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div class="flex items-center gap-4">
                <div class="w-11 h-11 rounded-2xl bg-gradient-to-br from-[#06b6d4] to-[#a855f7] flex items-center justify-center shadow-lg shadow-[#06b6d4]/20">
                    @svg('heroicon-o-light-bulb', 'w-6 h-6 text-white')
                </div>
                <div>
                    <h1 class="text-lg font-semibold tracking-tight text-white/95">Memory Viewer</h1>
                    <p class="text-[11px] text-white/35 tracking-wide font-medium">Memories · Learning Logs · Promoted Learnings</p>
                </div>
            </div>
            <div class="flex items-center gap-2.5 flex-wrap">
                <div class="flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/[0.05] border border-white/[0.08] backdrop-blur-md text-[11px] font-medium text-white/50 uppercase tracking-wide">
                    <span class="w-1.5 h-1.5 rounded-full bg-[#06b6d4]"></span>
                    {{ $this->getMemoryCount() }} Memories
                </div>
                @if($this->getPromotedCount() > 0)
                    <div class="flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#30d158]/10 border border-[#30d158]/20 backdrop-blur-md text-[11px] font-medium text-[#30d158] uppercase tracking-wide">
                        <span class="w-1.5 h-1.5 rounded-full bg-[#30d158]"></span>
                        {{ $this->getPromotedCount() }} Promoted
                    </div>
                @endif
                <x-filament::button size="sm" wire:click="refreshData" icon="heroicon-o-arrow-path">
                    Refresh
                </x-filament::button>
            </div>
        </div>

        {{-- ── Tab Navigation ──────────────────────────────────────────────── --}}
        <div class="w-full overflow-x-auto rounded-xl border border-white/[0.06] bg-white/[0.03] p-1 backdrop-blur-md sm:w-fit">
            <div class="flex min-w-max items-center gap-1">
            <button wire:click="switchTab('memories')"
                    class="px-4 py-2 rounded-lg text-xs font-medium transition-all duration-200 {{ $activeTab === 'memories' ? 'bg-[#06b6d4]/20 text-[#06b6d4] border border-[#06b6d4]/30' : 'text-white/40 hover:text-white/60 hover:bg-white/[0.04] border border-transparent' }}">
                @svg('heroicon-o-circle-stack', 'w-3.5 h-3.5 inline mr-1.5')
                Memories
            </button>
            <button wire:click="switchTab('learning-logs')"
                    class="px-4 py-2 rounded-lg text-xs font-medium transition-all duration-200 {{ $activeTab === 'learning-logs' ? 'bg-[#a855f7]/20 text-[#a855f7] border border-[#a855f7]/30' : 'text-white/40 hover:text-white/60 hover:bg-white/[0.04] border border-transparent' }}">
                @svg('heroicon-o-academic-cap', 'w-3.5 h-3.5 inline mr-1.5')
                Learning Logs
            </button>
            <button wire:click="switchTab('promoted')"
                    class="px-4 py-2 rounded-lg text-xs font-medium transition-all duration-200 {{ $activeTab === 'promoted' ? 'bg-[#30d158]/20 text-[#30d158] border border-[#30d158]/30' : 'text-white/40 hover:text-white/60 hover:bg-white/[0.04] border border-transparent' }}">
                @svg('heroicon-o-star', 'w-3.5 h-3.5 inline mr-1.5')
                Promoted
                @if($this->getPromotedCount() > 0)
                    <span class="ml-1.5 px-1.5 py-0.5 rounded-full bg-[#30d158]/20 text-[10px] font-semibold text-[#30d158]">{{ $this->getPromotedCount() }}</span>
                @endif
            </button>
            </div>
        </div>

        {{-- ── Memories Tab ────────────────────────────────────────────────── --}}
        @if($activeTab === 'memories')
            {{-- Search & Filter Bar --}}
            <div class="flex flex-col gap-3 md:flex-row">
                <div class="flex-1 relative">
                    <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                        @svg('heroicon-o-magnifying-glass', 'w-4 h-4 text-white/30')
                    </div>
                    <input type="text" wire:model.live.debounce.500ms="searchQuery"
                           placeholder="Search memories by content..."
                           class="w-full pl-10 pr-4 py-2.5 rounded-xl bg-white/[0.03] border border-white/[0.08] text-xs text-white/80 placeholder-white/30 focus:border-[#06b6d4]/40 focus:ring-1 focus:ring-[#06b6d4]/20 focus:outline-none transition-all backdrop-blur-md" />
                </div>
                <select wire:model.live="categoryFilter"
                        class="w-full px-4 py-2.5 rounded-xl bg-white/[0.03] border border-white/[0.08] text-xs text-white/60 focus:border-[#06b6d4]/40 focus:ring-1 focus:ring-[#06b6d4]/20 focus:outline-none transition-all backdrop-blur-md appearance-none cursor-pointer md:w-48">
                    <option value="">All Categories</option>
                    <option value="fact">Facts</option>
                    <option value="procedure">Procedures</option>
                    <option value="preference">Preferences</option>
                    <option value="observation">Observations</option>
                </select>
                @if($searchQuery || $categoryFilter)
                    <button wire:click="clearFilters" class="px-3 py-2.5 rounded-xl bg-white/[0.03] border border-white/[0.08] text-xs text-white/40 hover:text-white/60 hover:bg-white/[0.06] transition-all">
                        @svg('heroicon-o-x-mark', 'w-4 h-4')
                    </button>
                @endif
            </div>

            {{-- Memories List --}}
            @if(!empty($this->getMemories()))
                <div class="space-y-2">
                    @foreach($this->getMemories() as $memory)
                        @php
                            $confBadge = $this->getConfidenceBadge((float) ($memory['confidence'] ?? 0.5));
                            $catBadge = $this->getCategoryBadge($memory['category'] ?? '');
                        @endphp
                        <div class="bg-white/[0.03] backdrop-blur-[24px] rounded-xl p-4 border border-white/[0.06] hover:bg-white/[0.05] hover:border-white/[0.10] transition-all duration-200 group">
                            <div class="flex items-start gap-3">
                                <div class="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 border {{ $catBadge['color'] }}">
                                    @svg($catBadge['icon'], 'w-4 h-4')
                                </div>
                                <div class="flex-1 min-w-0">
                                    <p class="text-xs text-white/75 leading-relaxed">{{ $this->truncateText($memory['content'] ?? '', 300) }}</p>
                                    <div class="flex items-center gap-3 mt-2 flex-wrap">
                                        <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[10px] font-medium {{ $catBadge['color'] }}">
                                            {{ ucfirst($memory['category'] ?? 'unknown') }}
                                        </span>
                                        <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[10px] font-medium {{ $confBadge['color'] }}">
                                            {{ number_format(($memory['confidence'] ?? 0.5) * 100, 0) }}% · {{ $confBadge['label'] }}
                                        </span>
                                        @if(!empty($memory['source']))
                                            <span class="text-[10px] text-white/25">
                                                @svg('heroicon-o-arrow-top-right-on-square', 'w-3 h-3 inline') {{ $memory['source'] }}
                                            </span>
                                        @endif
                                        @if(!empty($memory['verified']))
                                            <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-[#30d158]/10 border border-[#30d158]/20 text-[10px] font-medium text-[#30d158]">
                                                @svg('heroicon-o-shield-check', 'w-3 h-3') Verified
                                            </span>
                                        @endif
                                        <span class="text-[10px] text-white/20">{{ $this->formatTimestamp($memory['created_at'] ?? null) }}</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    @endforeach
                </div>
            @else
                <div class="bg-white/[0.03] backdrop-blur-[40px] rounded-2xl p-8 border border-white/[0.06] text-center">
                    @svg('heroicon-o-circle-stack', 'w-12 h-12 text-white/15 mx-auto mb-3')
                    <p class="text-xs text-white/40">
                        @if($searchQuery)
                            No memories found matching "{{ $searchQuery }}"
                        @else
                            No memories stored yet.
                        @endif
                    </p>
                    <p class="text-[10px] text-white/25 mt-1">Memories are created as the AI learns from conversations and tasks.</p>
                </div>
            @endif
        @endif

        {{-- ── Learning Logs Tab ───────────────────────────────────────────── --}}
        @if($activeTab === 'learning-logs')
            {{-- Type Filter --}}
            <div class="flex items-center gap-2">
                <select wire:model.live="logTypeFilter"
                        class="px-4 py-2.5 rounded-xl bg-white/[0.03] border border-white/[0.08] text-xs text-white/60 focus:border-[#a855f7]/40 focus:ring-1 focus:ring-[#a855f7]/20 focus:outline-none transition-all backdrop-blur-md appearance-none cursor-pointer">
                    <option value="">All Types</option>
                    <option value="LEARNINGS">Learnings</option>
                    <option value="ERRORS">Errors</option>
                    <option value="FEATURE_REQUESTS">Feature Requests</option>
                </select>
                @if($logTypeFilter)
                    <button wire:click="clearFilters" class="px-3 py-2.5 rounded-xl bg-white/[0.03] border border-white/[0.08] text-xs text-white/40 hover:text-white/60 hover:bg-white/[0.06] transition-all">
                        @svg('heroicon-o-x-mark', 'w-4 h-4')
                    </button>
                @endif
            </div>

            {{-- Learning Logs List --}}
            @if(!empty($this->getLearningEntries()))
                <div class="space-y-2">
                    @foreach($this->getLearningEntries() as $entry)
                        @php $typeBadge = $this->getLogTypeBadge($entry['log_type'] ?? ''); @endphp
                        <div class="bg-white/[0.03] backdrop-blur-[24px] rounded-xl p-4 border border-white/[0.06] hover:bg-white/[0.05] hover:border-white/[0.10] transition-all duration-200 {{ !empty($entry['promoted']) ? 'border-l-2 border-l-[#30d158]/50' : '' }}">
                            <div class="flex items-start gap-3">
                                <div class="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 border {{ $typeBadge['color'] }}">
                                    @svg($typeBadge['icon'], 'w-4 h-4')
                                </div>
                                <div class="flex-1 min-w-0">
                                    <p class="text-xs text-white/75 leading-relaxed">{{ $this->truncateText($entry['content'] ?? '', 300) }}</p>
                                    <div class="flex items-center gap-3 mt-2 flex-wrap">
                                        <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[10px] font-medium {{ $typeBadge['color'] }}">
                                            @svg($typeBadge['icon'], 'w-3 h-3') {{ $typeBadge['label'] }}
                                        </span>
                                        @php $confBadge = $this->getConfidenceBadge((float) ($entry['confidence'] ?? 0.5)); @endphp
                                        <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[10px] font-medium {{ $confBadge['color'] }}">
                                            {{ number_format(($entry['confidence'] ?? 0.5) * 100, 0) }}%
                                        </span>
                                        @if(!empty($entry['category']))
                                            <span class="text-[10px] text-white/30 px-2 py-0.5 rounded-full bg-white/[0.03] border border-white/[0.06]">
                                                {{ $entry['category'] }}
                                            </span>
                                        @endif
                                        @if(!empty($entry['source']))
                                            <span class="text-[10px] text-white/25">via {{ $entry['source'] }}</span>
                                        @endif
                                        @if(!empty($entry['promoted']))
                                            <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-[#30d158]/10 border border-[#30d158]/20 text-[10px] font-medium text-[#30d158]">
                                                @svg('heroicon-o-star', 'w-3 h-3') Promoted
                                            </span>
                                        @endif
                                        <span class="text-[10px] text-white/20">{{ $this->formatTimestamp($entry['timestamp'] ?? null) }}</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    @endforeach
                </div>
            @else
                <div class="bg-white/[0.03] backdrop-blur-[40px] rounded-2xl p-8 border border-white/[0.06] text-center">
                    @svg('heroicon-o-academic-cap', 'w-12 h-12 text-white/15 mx-auto mb-3')
                    <p class="text-xs text-white/40">No learning log entries yet.</p>
                    <p class="text-[10px] text-white/25 mt-1">The AI creates learning entries from conversations, reflections, and errors.</p>
                </div>
            @endif
        @endif

        {{-- ── Promoted Learnings Tab ──────────────────────────────────────── --}}
        @if($activeTab === 'promoted')
            <div class="bg-white/[0.03] backdrop-blur-[40px] rounded-2xl p-5 border border-white/[0.06] shadow-[0_4px_24px_rgba(0,0,0,0.2)]">
                <div class="flex items-center gap-3 mb-4">
                    <div class="w-9 h-9 rounded-xl bg-gradient-to-br from-[#30d158] to-[#10b981] flex items-center justify-center shadow-lg shadow-[#30d158]/20">
                        @svg('heroicon-o-star', 'w-5 h-5 text-white')
                    </div>
                    <div>
                        <h2 class="text-sm font-semibold text-white/90 tracking-tight">Promoted Learnings</h2>
                        <p class="text-[10px] text-white/35 font-medium">Patterns detected 3+ times and promoted to system context</p>
                    </div>
                </div>

                @if(!empty($this->getPromotedEntries()))
                    <div class="space-y-3">
                        @foreach($this->getPromotedEntries() as $entry)
                            @php $typeBadge = $this->getLogTypeBadge($entry['log_type'] ?? ''); @endphp
                            <div class="bg-[#30d158]/[0.04] border border-[#30d158]/20 rounded-xl p-4 hover:bg-[#30d158]/[0.06] transition-all duration-200">
                                <div class="flex items-start gap-3">
                                    <div class="w-8 h-8 rounded-lg bg-[#30d158]/10 border border-[#30d158]/20 flex items-center justify-center shrink-0">
                                        @svg('heroicon-o-star', 'w-4 h-4 text-[#30d158]')
                                    </div>
                                    <div class="flex-1 min-w-0">
                                        <p class="text-xs text-white/80 leading-relaxed">{{ $entry['content'] ?? '' }}</p>
                                        <div class="flex items-center gap-3 mt-2 flex-wrap">
                                            <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[10px] font-medium {{ $typeBadge['color'] }}">
                                                @svg($typeBadge['icon'], 'w-3 h-3') {{ $typeBadge['label'] }}
                                            </span>
                                            @php $confBadge = $this->getConfidenceBadge((float) ($entry['confidence'] ?? 0.5)); @endphp
                                            <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[10px] font-medium {{ $confBadge['color'] }}">
                                                {{ number_format(($entry['confidence'] ?? 0.5) * 100, 0) }}%
                                            </span>
                                            @if(!empty($entry['category']))
                                                <span class="text-[10px] text-white/30 px-2 py-0.5 rounded-full bg-white/[0.03] border border-white/[0.06]">
                                                    {{ $entry['category'] }}
                                                </span>
                                            @endif
                                            @if(!empty($entry['promotion_timestamp']))
                                                <span class="text-[10px] text-[#30d158]/60">
                                                    @svg('heroicon-o-arrow-trending-up', 'w-3 h-3 inline') Promoted {{ $this->formatTimestamp($entry['promotion_timestamp']) }}
                                                </span>
                                            @endif
                                        </div>
                                    </div>
                                </div>
                            </div>
                        @endforeach
                    </div>
                @else
                    <div class="text-center py-8">
                        @svg('heroicon-o-star', 'w-10 h-10 text-white/15 mx-auto mb-3')
                        <p class="text-xs text-white/40">No promoted learnings yet.</p>
                        <p class="text-[10px] text-white/25 mt-1">Patterns that appear 3+ times are automatically promoted to system context.</p>
                    </div>
                @endif
            </div>
        @endif

    </div>
</x-filament-panels::page>

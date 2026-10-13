<x-filament-panels::page>

{{-- ════════════════════════════════════════════════════════
     SanaaBrain — Persistent Memory Interface
     ════════════════════════════════════════════════════════ --}}

<div class="space-y-6" x-data>

    {{-- ── Header ──────────────────────────────────────────────── --}}
    <div class="flex items-center justify-between">
        <div class="flex items-center gap-3">
            <div class="p-2 rounded-xl bg-[#0a84ff]/10 border border-[#0a84ff]/20">
                <x-heroicon-o-cpu-chip class="w-6 h-6 text-[#0a84ff]" />
            </div>
            <div>
                <h2 class="text-xl font-bold text-white">SanaaBrain</h2>
                <p class="text-sm text-white/40">Persistent memory — {{ $memoriesTotal }} records stored</p>
            </div>
        </div>
        <button wire:click="loadAllMemories"
                class="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 text-white/70 hover:text-white text-sm transition">
            <x-heroicon-o-arrow-path class="w-4 h-4" wire:loading.class="animate-spin" wire:target="loadAllMemories" />
            Refresh
        </button>
    </div>

    {{-- ── Section tabs ─────────────────────────────────────────── --}}
    <div class="flex gap-1 p-1 rounded-xl bg-white/5 border border-white/10 w-fit flex-wrap">
        @foreach ([
            ['key' => 'all',      'label' => 'All Memories',    'icon' => 'heroicon-o-rectangle-stack'],
            ['key' => 'add',      'label' => 'Add Memory',       'icon' => 'heroicon-o-plus-circle'],
            ['key' => 'search',   'label' => 'Search',           'icon' => 'heroicon-o-magnifying-glass'],
            ['key' => 'briefing', 'label' => 'Project Briefing', 'icon' => 'heroicon-o-document-text'],
            ['key' => 'session',  'label' => 'Save Session',     'icon' => 'heroicon-o-bookmark'],
            ['key' => 'smart',    'label' => 'Smart Briefing',   'icon' => 'heroicon-o-sparkles'],
            ['key' => 'insights', 'label' => 'Auto-Insights',    'icon' => 'heroicon-o-light-bulb'],
            ['key' => 'learn',    'label' => 'Learn Now',        'icon' => 'heroicon-o-academic-cap'],
            ['key' => 'habits',   'label' => 'Habit Intel',      'icon' => 'heroicon-o-chart-bar'],
        ] as $tab)
            <button wire:click="switchSection('{{ $tab['key'] }}')"
                    class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition
                           {{ $activeSection === $tab['key']
                               ? 'bg-[#0a84ff] text-white shadow'
                               : 'text-white/50 hover:text-white hover:bg-white/5' }}">
                <x-dynamic-component :component="$tab['icon']" class="w-4 h-4" />
                {{ $tab['label'] }}
            </button>
        @endforeach
    </div>

    {{-- ══════════════════════════════════════════════════════════
         SECTION: ALL MEMORIES
         ══════════════════════════════════════════════════════════ --}}
    @if ($activeSection === 'all')
    <div class="space-y-4">

        {{-- Filters --}}
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
                <label class="block text-xs text-white/50 mb-1">Filter by Project</label>
                <input wire:model.live="filterProject"
                       placeholder="e.g. farzone, soko, antigravity"
                       class="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-white/30 focus:outline-none focus:border-[#0a84ff]/50" />
            </div>
            <div>
                <label class="block text-xs text-white/50 mb-1">Filter by Category</label>
                <select wire:model.live="filterCategory"
                        class="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-[#0a84ff]/50">
                    <option value="">All categories</option>
                    <option value="fact">Fact</option>
                    <option value="procedure">Procedure</option>
                    <option value="preference">Preference</option>
                    <option value="observation">Observation</option>
                    <option value="session_log">Session Log</option>
                    <option value="general">General</option>
                </select>
            </div>
        </div>

        @if ($filterProject)
        <div class="flex justify-end">
            <button wire:click="clearProject"
                    wire:confirm="Delete ALL memories for project '{{ $filterProject }}'? This cannot be undone."
                    class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#ff453a]/10 hover:bg-[#ff453a]/20 border border-[#ff453a]/20 text-[#ff453a] text-xs font-medium transition">
                <x-heroicon-o-trash class="w-3.5 h-3.5" />
                Clear all for "{{ $filterProject }}"
            </button>
        </div>
        @endif

        {{-- Memory cards --}}
        @if (count($memoriesAll) === 0)
            <div class="text-center py-16 text-white/30">
                <x-heroicon-o-cpu-chip class="w-12 h-12 mx-auto mb-3 opacity-30" />
                <p class="text-sm">No memories found. Add one below.</p>
            </div>
        @else
            <div class="space-y-2">
                @foreach ($memoriesAll as $mem)
                    @php
                        $badge = $this->getCategoryBadge($mem['category'] ?? 'general');
                        $proj  = $mem['metadata']['project'] ?? ($mem['project'] ?? null);
                    @endphp
                    <div class="flex items-start gap-3 p-3 rounded-xl bg-white/3 hover:bg-white/5 border border-white/8 transition group">
                        <div class="flex-1 min-w-0">
                            <div class="flex items-center gap-2 mb-1 flex-wrap">
                                <span class="text-xs px-2 py-0.5 rounded-full border font-medium {{ $badge['color'] }}">
                                    {{ $badge['label'] }}
                                </span>
                                @if ($proj)
                                    <span class="text-xs px-2 py-0.5 rounded-full bg-[#0a84ff]/10 border border-[#0a84ff]/20 text-[#0a84ff]">
                                        {{ $proj }}
                                    </span>
                                @endif
                                @if (isset($mem['confidence']))
                                    <span class="text-xs text-white/30">{{ round($mem['confidence'] * 100) }}% conf</span>
                                @endif
                                @if (isset($mem['access_count']) && $mem['access_count'] > 0)
                                    <span class="text-xs text-white/20">{{ $mem['access_count'] }}× accessed</span>
                                @endif
                            </div>
                            <p class="text-sm text-white/80 leading-relaxed">{{ $this->truncate($mem['content'] ?? '', 220) }}</p>
                            <p class="text-xs text-white/25 mt-1">{{ $this->formatTimestamp($mem['created_at'] ?? null) }}</p>
                        </div>
                        <button wire:click="deleteMemory({{ $mem['id'] }})"
                                wire:confirm="Delete this memory?"
                                class="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg hover:bg-[#ff453a]/10 text-[#ff453a]/50 hover:text-[#ff453a] transition">
                            <x-heroicon-o-trash class="w-4 h-4" />
                        </button>
                    </div>
                @endforeach
            </div>
            <p class="text-xs text-white/25 text-right">Showing {{ count($memoriesAll) }} of {{ $memoriesTotal }} total</p>
        @endif
    </div>
    @endif

    {{-- ══════════════════════════════════════════════════════════
         SECTION: ADD MEMORY
         ══════════════════════════════════════════════════════════ --}}
    @if ($activeSection === 'add')
    <div class="max-w-2xl space-y-4">
        <div class="p-4 rounded-xl bg-white/3 border border-white/10 space-y-4">
            <h3 class="text-sm font-semibold text-white/70 uppercase tracking-wider">Add New Memory</h3>

            <div>
                <label class="block text-xs text-white/50 mb-1">Content <span class="text-[#ff453a]">*</span></label>
                <textarea wire:model="addContent" rows="4"
                          placeholder="Describe what the AI should remember…"
                          class="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-white/30 focus:outline-none focus:border-[#0a84ff]/50 resize-none"></textarea>
            </div>

            <div class="grid grid-cols-2 gap-3">
                <div>
                    <label class="block text-xs text-white/50 mb-1">Category</label>
                    <select wire:model="addCategory"
                            class="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-[#0a84ff]/50">
                        <option value="general">General</option>
                        <option value="fact">Fact</option>
                        <option value="procedure">Procedure</option>
                        <option value="preference">Preference</option>
                        <option value="observation">Observation</option>
                    </select>
                </div>
                <div>
                    <label class="block text-xs text-white/50 mb-1">Project (optional)</label>
                    <input wire:model="addProject"
                           placeholder="e.g. farzone, soko"
                           class="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-white/30 focus:outline-none focus:border-[#0a84ff]/50" />
                </div>
            </div>

            <div>
                <label class="block text-xs text-white/50 mb-1">Confidence: {{ $addConfidence }}</label>
                <input wire:model.live="addConfidence" type="range" min="0" max="1" step="0.1"
                       class="w-full accent-[#0a84ff]" />
                <div class="flex justify-between text-xs text-white/25 mt-1">
                    <span>0 — Low</span>
                    <span>1 — High</span>
                </div>
            </div>

            <button wire:click="submitAddMemory"
                    wire:loading.attr="disabled"
                    class="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-[#0a84ff] hover:bg-[#0a84ff]/80 text-white text-sm font-medium transition disabled:opacity-50">
                <x-heroicon-o-plus-circle class="w-4 h-4" wire:loading.remove wire:target="submitAddMemory" />
                <x-heroicon-o-arrow-path class="w-4 h-4 animate-spin hidden" wire:loading.class.remove="hidden" wire:target="submitAddMemory" />
                Save Memory
            </button>
        </div>
    </div>
    @endif

    {{-- ══════════════════════════════════════════════════════════
         SECTION: SEARCH
         ══════════════════════════════════════════════════════════ --}}
    @if ($activeSection === 'search')
    <div class="space-y-4">
        <div class="p-4 rounded-xl bg-white/3 border border-white/10 space-y-3">
            <h3 class="text-sm font-semibold text-white/70 uppercase tracking-wider">Semantic Search</h3>

            <div class="flex gap-2">
                <input wire:model="searchQuery"
                       wire:keydown.enter="submitSearch"
                       placeholder="What do you want to recall?"
                       class="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-white/30 focus:outline-none focus:border-[#0a84ff]/50" />
                <input wire:model="searchProject"
                       placeholder="Project filter"
                       class="w-36 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-white/30 focus:outline-none focus:border-[#0a84ff]/50" />
                <button wire:click="submitSearch"
                        class="px-4 py-2 rounded-lg bg-[#0a84ff] hover:bg-[#0a84ff]/80 text-white text-sm font-medium transition">
                    Search
                </button>
                @if (count($searchResults) > 0)
                <button wire:click="clearSearch"
                        class="px-3 py-2 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 text-white/50 text-sm transition">
                    Clear
                </button>
                @endif
            </div>
        </div>

        @if (count($searchResults) > 0)
            <div class="space-y-2">
                @foreach ($searchResults as $mem)
                    @php
                        $badge = $this->getCategoryBadge($mem['category'] ?? 'general');
                        $proj  = $mem['metadata']['project'] ?? ($mem['project'] ?? null);
                        $sim   = isset($mem['similarity']) ? round($mem['similarity'] * 100, 1) . '%' : null;
                    @endphp
                    <div class="p-3 rounded-xl bg-white/3 hover:bg-white/5 border border-white/8 transition">
                        <div class="flex items-center gap-2 mb-1 flex-wrap">
                            <span class="text-xs px-2 py-0.5 rounded-full border font-medium {{ $badge['color'] }}">{{ $badge['label'] }}</span>
                            @if ($proj)
                                <span class="text-xs px-2 py-0.5 rounded-full bg-[#0a84ff]/10 border border-[#0a84ff]/20 text-[#0a84ff]">{{ $proj }}</span>
                            @endif
                            @if ($sim)
                                <span class="text-xs text-[#30d158]/70">{{ $sim }} match</span>
                            @endif
                        </div>
                        <p class="text-sm text-white/80 leading-relaxed">{{ $mem['content'] ?? '' }}</p>
                        <p class="text-xs text-white/25 mt-1">{{ $this->formatTimestamp($mem['created_at'] ?? null) }}</p>
                    </div>
                @endforeach
            </div>
        @elseif ($searchQuery !== '')
            <div class="text-center py-12 text-white/30">
                <x-heroicon-o-magnifying-glass class="w-10 h-10 mx-auto mb-2 opacity-30" />
                <p class="text-sm">No results. Try a different query.</p>
            </div>
        @endif
    </div>
    @endif

    {{-- ══════════════════════════════════════════════════════════
         SECTION: PROJECT BRIEFING
         ══════════════════════════════════════════════════════════ --}}
    @if ($activeSection === 'briefing')
    <div class="space-y-4">
        <div class="p-4 rounded-xl bg-white/3 border border-white/10 space-y-3">
            <h3 class="text-sm font-semibold text-white/70 uppercase tracking-wider">Project Briefing</h3>
            <div class="flex gap-2">
                <input wire:model="briefingProject"
                       wire:keydown.enter="loadBriefing"
                       placeholder="Project name (e.g. farzone, soko)"
                       class="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-white/30 focus:outline-none focus:border-[#0a84ff]/50" />
                <button wire:click="loadBriefing"
                        class="px-4 py-2 rounded-lg bg-[#0a84ff] hover:bg-[#0a84ff]/80 text-white text-sm font-medium transition">
                    Generate
                </button>
            </div>
        </div>

        @if (!empty($briefingData['briefing']))
            <div class="p-4 rounded-xl bg-white/3 border border-white/10">
                <div class="flex items-center justify-between mb-3">
                    <h4 class="text-sm font-semibold text-white">
                        {{ $briefingData['project'] ?? $briefingProject }}
                        <span class="text-white/30 font-normal text-xs ml-2">
                            ({{ $briefingData['count'] ?? 0 }} memories)
                        </span>
                    </h4>
                </div>
                <div class="prose prose-invert prose-sm max-w-none text-white/80 text-sm leading-relaxed whitespace-pre-wrap">{{ $briefingData['briefing'] }}</div>
            </div>
        @elseif (!empty($briefingData['error']))
            <div class="p-3 rounded-lg bg-[#ff453a]/10 border border-[#ff453a]/20 text-[#ff453a] text-sm">
                {{ $briefingData['error'] }}
            </div>
        @endif
    </div>
    @endif

    {{-- ══════════════════════════════════════════════════════════
         SECTION: SAVE SESSION
         ══════════════════════════════════════════════════════════ --}}
    @if ($activeSection === 'session')
    <div class="max-w-2xl space-y-4">
        <div class="p-4 rounded-xl bg-white/3 border border-white/10 space-y-4">
            <h3 class="text-sm font-semibold text-white/70 uppercase tracking-wider">Save Session Log</h3>
            <p class="text-xs text-white/40">Saves a session transcript as a searchable memory entry (category: session_log).</p>

            <div>
                <label class="block text-xs text-white/50 mb-1">Session Content <span class="text-[#ff453a]">*</span></label>
                <textarea wire:model="sessionContent" rows="5"
                          placeholder="Paste session transcript or notes…"
                          class="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-white/30 focus:outline-none focus:border-[#0a84ff]/50 resize-none"></textarea>
            </div>

            <div class="grid grid-cols-2 gap-3">
                <div>
                    <label class="block text-xs text-white/50 mb-1">Session ID</label>
                    <input wire:model="sessionId"
                           placeholder="admin:sanaa-brain"
                           class="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-white/30 focus:outline-none focus:border-[#0a84ff]/50" />
                </div>
                <div>
                    <label class="block text-xs text-white/50 mb-1">Project (optional)</label>
                    <input wire:model="sessionProject"
                           placeholder="e.g. farzone"
                           class="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-white/30 focus:outline-none focus:border-[#0a84ff]/50" />
                </div>
            </div>

            <button wire:click="submitSaveSession"
                    wire:loading.attr="disabled"
                    class="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-[#64d2ff]/20 hover:bg-[#64d2ff]/30 border border-[#64d2ff]/20 text-[#64d2ff] text-sm font-medium transition disabled:opacity-50">
                <x-heroicon-o-bookmark class="w-4 h-4" wire:loading.remove wire:target="submitSaveSession" />
                <x-heroicon-o-arrow-path class="w-4 h-4 animate-spin hidden" wire:loading.class.remove="hidden" wire:target="submitSaveSession" />
                Save Session
            </button>
        </div>
    </div>
    @endif

    {{-- ══════════════════════════════════════════════════════════
         SECTION: SMART BRIEFING (Phase 2)
         ══════════════════════════════════════════════════════════ --}}
    @if ($activeSection === 'smart')
    <div class="space-y-4">
        <div class="p-4 rounded-xl bg-white/3 border border-white/10 space-y-3">
            <div class="flex items-center gap-2">
                <x-heroicon-o-sparkles class="w-4 h-4 text-[#bf5af2]" />
                <h3 class="text-sm font-semibold text-white/70 uppercase tracking-wider">Smart Briefing</h3>
            </div>
            <p class="text-xs text-white/40">
                AI-generated multi-section briefing combining project memory, health patterns, work habits, client intel, and auto-learned insights.
            </p>
            <div class="flex gap-2">
                <input wire:model="smartBriefingProject"
                       wire:keydown.enter="loadSmartBriefing"
                       placeholder="Project name (e.g. farzone, soko, antigravity)"
                       class="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-white/30 focus:outline-none focus:border-[#bf5af2]/50" />
                <button wire:click="loadSmartBriefing"
                        wire:loading.attr="disabled"
                        class="flex items-center gap-2 px-4 py-2 rounded-lg bg-[#bf5af2]/20 hover:bg-[#bf5af2]/30 border border-[#bf5af2]/20 text-[#bf5af2] text-sm font-medium transition disabled:opacity-50">
                    <x-heroicon-o-sparkles class="w-4 h-4" wire:loading.remove wire:target="loadSmartBriefing" />
                    <x-heroicon-o-arrow-path class="w-4 h-4 animate-spin hidden" wire:loading.class.remove="hidden" wire:target="loadSmartBriefing" />
                    Generate Smart Briefing
                </button>
            </div>
        </div>

        @if (!empty($smartBriefingData['smart_briefing']))
            <div class="p-4 rounded-xl bg-white/3 border border-white/10 space-y-3"
                 x-data="{ copied: false }">
                {{-- Header row --}}
                <div class="flex items-center justify-between">
                    <div class="flex items-center gap-2 flex-wrap">
                        <h4 class="text-sm font-semibold text-white">
                            {{ $smartBriefingData['project'] ?? $smartBriefingProject }}
                        </h4>
                        @if (!empty($smartBriefingData['sections_included']))
                            @foreach ($smartBriefingData['sections_included'] as $sec)
                                <span class="text-xs px-2 py-0.5 rounded-full bg-[#bf5af2]/10 border border-[#bf5af2]/20 text-[#bf5af2]">
                                    {{ $sec }}
                                </span>
                            @endforeach
                        @endif
                    </div>
                    {{-- Copy to clipboard --}}
                    <button @click="
                            navigator.clipboard.writeText($refs.briefingText.innerText);
                            copied = true;
                            setTimeout(() => copied = false, 2000);
                        "
                        class="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 text-white/50 hover:text-white text-xs transition">
                        <template x-if="!copied">
                            <x-heroicon-o-clipboard-document class="w-3.5 h-3.5" />
                        </template>
                        <template x-if="copied">
                            <x-heroicon-o-check class="w-3.5 h-3.5 text-[#30d158]" />
                        </template>
                        <span x-text="copied ? 'Copied!' : 'Copy'"></span>
                    </button>
                </div>

                {{-- Briefing text --}}
                <div x-ref="briefingText"
                     class="prose prose-invert prose-sm max-w-none text-white/80 text-sm leading-relaxed whitespace-pre-wrap font-mono bg-white/2 rounded-lg p-3 border border-white/5 max-h-[28rem] overflow-y-auto">{{ $smartBriefingData['smart_briefing'] }}</div>

                @if (!empty($smartBriefingData['generated_at']))
                    <p class="text-xs text-white/25">Generated {{ $this->formatTimestamp($smartBriefingData['generated_at']) }}</p>
                @endif
            </div>
        @elseif (!empty($smartBriefingData['error']))
            <div class="p-3 rounded-lg bg-[#ff453a]/10 border border-[#ff453a]/20 text-[#ff453a] text-sm">
                {{ $smartBriefingData['error'] }}
            </div>
        @endif
    </div>
    @endif

    {{-- ══════════════════════════════════════════════════════════
         SECTION: AUTO-LEARNED INSIGHTS (Phase 2)
         ══════════════════════════════════════════════════════════ --}}
    @if ($activeSection === 'insights')
    <div class="space-y-4">

        {{-- Controls --}}
        <div class="flex flex-wrap items-center gap-3">
            <div class="flex items-center gap-2">
                <x-heroicon-o-light-bulb class="w-4 h-4 text-[#ff9f0a]" />
                <span class="text-sm font-semibold text-white/70 uppercase tracking-wider">Auto-Learned Insights</span>
            </div>
            <div class="flex-1"></div>
            <select wire:model.live="insightsCategoryFilter"
                    class="bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-[#ff9f0a]/50">
                <option value="">All categories</option>
                <option value="system_health">System Health</option>
                <option value="skill_intelligence">Skill Intelligence</option>
                <option value="client_intelligence">Client Intelligence</option>
                <option value="resource_usage">Resource Usage</option>
                <option value="work_pattern">Work Pattern</option>
                <option value="recurring_issues">Recurring Issues</option>
                <option value="habit_intelligence">Habit Intelligence</option>
            </select>
            <input wire:model.live="insightsProjectFilter"
                   placeholder="Filter by project"
                   class="w-40 bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 text-sm text-white placeholder-white/30 focus:outline-none focus:border-[#ff9f0a]/50" />
            <button wire:click="loadInsights"
                    class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#ff9f0a]/10 hover:bg-[#ff9f0a]/20 border border-[#ff9f0a]/20 text-[#ff9f0a] text-sm font-medium transition">
                <x-heroicon-o-arrow-path class="w-3.5 h-3.5" wire:loading.class="animate-spin" wire:target="loadInsights" />
                Refresh
            </button>
        </div>

        @if (empty($insightsData) || empty($insightsData['items']))
            <div class="text-center py-14 text-white/30">
                <x-heroicon-o-light-bulb class="w-10 h-10 mx-auto mb-3 opacity-30" />
                <p class="text-sm">No auto-learned insights yet.</p>
                <p class="text-xs mt-1 text-white/20">Switch to <strong class="text-white/40">Learn Now</strong> tab to trigger a learning cycle.</p>
            </div>
        @else
            @php $items = $insightsData['items'] ?? []; @endphp
            <div class="overflow-hidden rounded-xl border border-white/10">
                <table class="w-full text-sm">
                    <thead>
                        <tr class="bg-white/5 border-b border-white/10">
                            <th class="text-left px-4 py-2.5 text-xs text-white/40 font-medium w-36">Category</th>
                            <th class="text-left px-4 py-2.5 text-xs text-white/40 font-medium">Insight</th>
                            <th class="text-left px-4 py-2.5 text-xs text-white/40 font-medium w-32 hidden md:table-cell">Source</th>
                            <th class="text-left px-4 py-2.5 text-xs text-white/40 font-medium w-36 hidden md:table-cell">Stored</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-white/5">
                        @foreach ($items as $item)
                            @php
                                $cat = $item['category'] ?? 'general';
                                $badge = $this->getInsightsCategoryBadge($cat);
                                $proj  = $item['metadata']['project'] ?? ($item['project'] ?? null);
                                $src   = $item['source'] ?? '';
                                $srcShort = str_replace('autolearn_', '', $src);
                            @endphp
                            <tr class="hover:bg-white/3 transition">
                                <td class="px-4 py-3 align-top">
                                    <span class="text-xs px-2 py-0.5 rounded-full border font-medium {{ $badge['color'] }}">
                                        {{ $badge['label'] }}
                                    </span>
                                    @if ($proj)
                                        <span class="block text-xs text-[#0a84ff] mt-1">{{ $proj }}</span>
                                    @endif
                                </td>
                                <td class="px-4 py-3 align-top">
                                    <p class="text-white/80 leading-relaxed">{{ $this->truncate($item['content'] ?? '', 200) }}</p>
                                </td>
                                <td class="px-4 py-3 align-top hidden md:table-cell">
                                    <span class="text-xs text-white/30 font-mono">{{ $srcShort ?: '—' }}</span>
                                </td>
                                <td class="px-4 py-3 align-top hidden md:table-cell">
                                    <span class="text-xs text-white/25">{{ $this->formatTimestamp($item['created_at'] ?? null) }}</span>
                                </td>
                            </tr>
                        @endforeach
                    </tbody>
                </table>
            </div>
            <p class="text-xs text-white/25 text-right">
                {{ count($items) }} of {{ $insightsData['total'] ?? count($items) }} insights
            </p>
        @endif
    </div>
    @endif

    {{-- ══════════════════════════════════════════════════════════
         SECTION: TRIGGER LEARNING NOW (Phase 2)
         ══════════════════════════════════════════════════════════ --}}
    @if ($activeSection === 'learn')
    <div class="max-w-2xl space-y-4">

        {{-- Description card --}}
        <div class="p-4 rounded-xl bg-white/3 border border-white/10 space-y-4">
            <div class="flex items-center gap-2">
                <x-heroicon-o-academic-cap class="w-5 h-5 text-[#30d158]" />
                <h3 class="text-sm font-semibold text-white/70 uppercase tracking-wider">Trigger Learning Now</h3>
            </div>
            <p class="text-sm text-white/60 leading-relaxed">
                Force SanaaBrain to scan the last <strong class="text-white/80">24 hours</strong> of system data and store new insights.
                This runs 6 learning methods in parallel:
            </p>
            <ul class="text-xs text-white/40 space-y-1 list-disc list-inside">
                <li>Health logs — tenant issues &amp; alert spikes</li>
                <li>Skill runs — usage patterns &amp; failure rates</li>
                <li>Client activity — tenant engagement &amp; churn signals</li>
                <li>LLM usage — cost tracking &amp; provider spend</li>
                <li>Conversation patterns — topic clustering &amp; work summaries</li>
                <li>Watchdog alerts — recurring infrastructure issues</li>
            </ul>
            <p class="text-xs text-white/30">
                ⏱ Typical run time: 15–45 seconds. Results appear below.
            </p>

            <button wire:click="triggerLearnNow"
                    wire:loading.attr="disabled"
                    @if ($learnNowRunning) disabled @endif
                    class="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-[#30d158]/15 hover:bg-[#30d158]/25 border border-[#30d158]/25 text-[#30d158] text-sm font-semibold transition disabled:opacity-50 disabled:cursor-wait">
                <x-heroicon-o-academic-cap class="w-5 h-5" wire:loading.remove wire:target="triggerLearnNow" />
                <x-heroicon-o-arrow-path class="w-5 h-5 animate-spin hidden" wire:loading.class.remove="hidden" wire:target="triggerLearnNow" />
                <span wire:loading.remove wire:target="triggerLearnNow">
                    {{ $learnNowRunning ? 'Learning in progress…' : 'Learn Now' }}
                </span>
                <span class="hidden" wire:loading.class.remove="hidden" wire:target="triggerLearnNow">
                    Learning… please wait
                </span>
            </button>
        </div>

        {{-- Result card --}}
        @if (!empty($learnNowResult))
            @if (isset($learnNowResult['memories_created']))
                <div class="p-4 rounded-xl bg-[#30d158]/10 border border-[#30d158]/20 space-y-3">
                    <div class="flex items-center gap-2">
                        <x-heroicon-o-check-circle class="w-5 h-5 text-[#30d158]" />
                        <span class="text-sm font-semibold text-[#30d158]">Learning Complete</span>
                    </div>
                    <div class="grid grid-cols-3 gap-3">
                        <div class="p-3 rounded-lg bg-white/5 text-center">
                            <p class="text-2xl font-bold text-white">{{ $learnNowResult['methods_run'] ?? 0 }}</p>
                            <p class="text-xs text-white/40 mt-0.5">Methods Run</p>
                        </div>
                        <div class="p-3 rounded-lg bg-white/5 text-center">
                            <p class="text-2xl font-bold text-[#30d158]">{{ $learnNowResult['memories_created'] ?? 0 }}</p>
                            <p class="text-xs text-white/40 mt-0.5">New Memories</p>
                        </div>
                        <div class="p-3 rounded-lg bg-white/5 text-center">
                            <p class="text-2xl font-bold {{ count($learnNowResult['errors'] ?? []) > 0 ? 'text-[#ff9f0a]' : 'text-white' }}">
                                {{ count($learnNowResult['errors'] ?? []) }}
                            </p>
                            <p class="text-xs text-white/40 mt-0.5">Errors</p>
                        </div>
                    </div>
                    @if (!empty($learnNowResult['errors']))
                        <div class="space-y-1">
                            @foreach ($learnNowResult['errors'] as $err)
                                <p class="text-xs text-[#ff9f0a] font-mono bg-[#ff9f0a]/5 rounded px-2 py-1">{{ $err }}</p>
                            @endforeach
                        </div>
                    @endif
                    <p class="text-xs text-white/30">
                        Switch to <strong class="text-white/50">Auto-Insights</strong> tab to browse newly stored insights.
                    </p>
                </div>
            @elseif (isset($learnNowResult['error']))
                <div class="p-4 rounded-xl bg-[#ff453a]/10 border border-[#ff453a]/20 space-y-2">
                    <div class="flex items-center gap-2">
                        <x-heroicon-o-exclamation-triangle class="w-5 h-5 text-[#ff453a]" />
                        <span class="text-sm font-semibold text-[#ff453a]">Learning Failed</span>
                    </div>
                    <p class="text-sm text-[#ff453a]/80">{{ $learnNowResult['error'] }}</p>
                </div>
            @else
                <div class="p-3 rounded-xl bg-white/3 border border-white/10">
                    <pre class="text-xs text-white/50 whitespace-pre-wrap font-mono">{{ json_encode($learnNowResult, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE) }}</pre>
                </div>
            @endif
        @endif
    </div>
    @endif

    {{-- ══════════════════════════════════════════════════════════
         SECTION: HABIT INTELLIGENCE (Phase 2)
         ══════════════════════════════════════════════════════════ --}}
    @if ($activeSection === 'habits')
    <div class="space-y-4">

        {{-- Header + refresh --}}
        <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
                <x-heroicon-o-chart-bar class="w-5 h-5 text-[#64d2ff]" />
                <h3 class="text-sm font-semibold text-white/70 uppercase tracking-wider">Habit Intelligence</h3>
            </div>
            <button wire:click="loadHabits"
                    class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#64d2ff]/10 hover:bg-[#64d2ff]/20 border border-[#64d2ff]/20 text-[#64d2ff] text-sm font-medium transition">
                <x-heroicon-o-arrow-path class="w-3.5 h-3.5" wire:loading.class="animate-spin" wire:target="loadHabits" />
                Refresh
            </button>
        </div>

        @if (empty($habitsData))
            <div class="text-center py-14 text-white/30">
                <x-heroicon-o-chart-bar class="w-10 h-10 mx-auto mb-3 opacity-30" />
                <p class="text-sm">No habit data yet.</p>
                <p class="text-xs mt-1 text-white/20">
                    Weekly habit summaries are auto-generated every Monday at 06:00 UTC.<br>
                    You can also trigger one manually via <strong class="text-white/40">Learn Now</strong>.
                </p>
            </div>
        @else
            {{-- Latest habit — full display --}}
            @php $latestHabit = $habitsData[0] ?? null; @endphp
            @if ($latestHabit)
                <div class="p-4 rounded-xl bg-[#64d2ff]/5 border border-[#64d2ff]/15 space-y-3">
                    <div class="flex items-center gap-2 flex-wrap">
                        <span class="text-xs px-2 py-0.5 rounded-full bg-[#64d2ff]/15 border border-[#64d2ff]/25 text-[#64d2ff] font-medium">
                            Latest Weekly Summary
                        </span>
                        @if (!empty($latestHabit['metadata']['project']))
                            <span class="text-xs px-2 py-0.5 rounded-full bg-[#0a84ff]/10 border border-[#0a84ff]/20 text-[#0a84ff]">
                                {{ $latestHabit['metadata']['project'] }}
                            </span>
                        @endif
                        <span class="text-xs text-white/30 ml-auto">
                            {{ $this->formatTimestamp($latestHabit['created_at'] ?? null) }}
                        </span>
                    </div>
                    <div class="text-sm text-white/80 leading-relaxed whitespace-pre-wrap">{{ $latestHabit['content'] ?? '' }}</div>
                    @if (!empty($latestHabit['confidence']))
                        <p class="text-xs text-white/25">Confidence: {{ round(($latestHabit['confidence'] ?? 1) * 100) }}%</p>
                    @endif
                </div>
            @endif

            {{-- Previous 3 summaries — compact cards --}}
            @if (count($habitsData) > 1)
                <div>
                    <p class="text-xs text-white/40 mb-2 uppercase tracking-wider">Previous Summaries</p>
                    <div class="space-y-2">
                        @foreach (array_slice($habitsData, 1, 3) as $habit)
                            <div class="p-3 rounded-xl bg-white/3 hover:bg-white/5 border border-white/8 transition"
                                 x-data="{ expanded: false }">
                                <div class="flex items-start gap-2 cursor-pointer" @click="expanded = !expanded">
                                    <div class="flex-1 min-w-0">
                                        <p class="text-sm text-white/70 leading-snug"
                                           :class="expanded ? '' : 'line-clamp-2'">{{ $habit['content'] ?? '' }}</p>
                                    </div>
                                    <div class="flex items-center gap-2 shrink-0 mt-0.5">
                                        <span class="text-xs text-white/25">{{ $this->formatTimestamp($habit['created_at'] ?? null) }}</span>
                                        <x-heroicon-o-chevron-down class="w-3.5 h-3.5 text-white/30 transition-transform"
                                                                    ::class="expanded ? 'rotate-180' : ''" />
                                    </div>
                                </div>
                            </div>
                        @endforeach
                    </div>
                </div>
            @endif
        @endif
    </div>
    @endif

</div>

</x-filament-panels::page>

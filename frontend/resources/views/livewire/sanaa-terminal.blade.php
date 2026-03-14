<div
    x-data="sanaaTerminal(@js($commandHistory), @js($skillSuggestions))"
    x-init="init()"
    class="glass-dark rounded-[2rem] p-6 shadow-2xl h-[620px] flex flex-col relative overflow-hidden group"
    @if($pendingCommandId) wire:poll.3s="pollCommand" @endif
>
    {{-- Decorative Background Gradients --}}
    <div class="absolute -top-32 -left-32 w-64 h-64 bg-sanaa-indigo/5 blur-[80px] rounded-full pointer-events-none"></div>
    <div class="absolute -bottom-32 -right-32 w-64 h-64 bg-sanaa-cyan/5 blur-[80px] rounded-full pointer-events-none"></div>

    {{-- Chat Header --}}
    <div class="flex items-center justify-between mb-5 pb-4 border-b border-white/[0.05] relative z-10">
        <div class="flex items-center gap-3">
            <div class="w-9 h-9 rounded-xl bg-sanaa-indigo/10 flex items-center justify-center border border-sanaa-indigo/20">
                <x-heroicon-m-sparkles class="w-4 h-4 text-sanaa-indigo"/>
            </div>
            <div>
                <h3 class="text-[10px] font-black text-white/30 uppercase tracking-[0.2em] mb-0.5">Sanaa Neural Link</h3>
                <div class="flex items-center gap-1.5">
                    <div class="w-1 h-1 rounded-full bg-sanaa-emerald animate-pulse"></div>
                    <span class="text-[9px] font-bold text-white/50 uppercase tracking-widest">Groq + Local ML</span>
                </div>
            </div>
        </div>
        <div class="flex items-center gap-2">
            <div class="px-2.5 py-1 rounded-full glass text-[9px] font-bold text-white/30 uppercase tracking-tight">
                Bridge: Stable
            </div>
            @if(!empty($history))
                <button
                    wire:click="clearHistory"
                    title="Clear chat"
                    class="w-7 h-7 rounded-lg flex items-center justify-center text-white/20 hover:text-white/50 hover:bg-white/5 transition-all duration-150"
                >
                    <x-heroicon-m-trash class="w-3.5 h-3.5"/>
                </button>
            @endif
        </div>
    </div>

    {{-- Chat History --}}
    <div class="flex-1 overflow-y-auto mb-5 space-y-5 pr-1 relative z-10 chat-scroll" id="terminal-history">
        <div class="flex flex-col items-center py-6 text-center opacity-30">
            <div class="w-px h-10 bg-gradient-to-b from-transparent via-white/10 to-white/10 mb-3"></div>
            <p class="text-[9px] font-black text-white/40 uppercase tracking-[0.3em]">Communication Initialized</p>
        </div>

        @foreach($history as $index => $entry)
            <div
                class="flex {{ $entry['type'] === 'user' ? 'justify-end' : 'justify-start' }} animate-in fade-in slide-in-from-bottom-2 duration-400"
                style="animation-delay: {{ min($index * 40, 200) }}ms"
            >
                <div class="max-w-[85%] relative group/msg">
                    <div class="flex flex-col {{ $entry['type'] === 'user' ? 'items-end' : 'items-start' }} gap-1 mb-1">
                        <span class="text-[9px] font-black tracking-widest uppercase {{ $entry['type'] === 'user' ? 'text-white/25' : 'text-sanaa-indigo/70' }}">
                            {{ $entry['type'] === 'user' ? 'YOU' : 'SANAA AI' }}
                        </span>
                    </div>

                    <div class="rounded-3xl px-5 py-3 shadow-xl transition-all duration-200
                        {{ $entry['type'] === 'user'
                            ? 'bg-gradient-to-br from-sanaa-indigo to-sanaa-purple text-white rounded-tr-none'
                            : 'glass-dark border border-white/[0.07] text-white/75 rounded-tl-none hover:border-sanaa-indigo/25' }}">

                        <div class="terminal-content prose prose-invert prose-xs max-w-none prose-p:leading-relaxed prose-pre:bg-black/40 prose-pre:border prose-pre:border-white/5">
                            {!! str($entry['text'])->markdown() !!}
                        </div>

                        <div class="flex items-center justify-end gap-2 mt-1.5 opacity-0 group-hover/msg:opacity-100 transition-opacity">
                            <span class="text-[8px] font-bold text-white/25 uppercase tabular-nums">
                                {{ $entry['time'] }}
                            </span>
                        </div>
                    </div>
                </div>
            </div>
        @endforeach

        {{-- Loading indicator --}}
        @if($isLoading)
            <div class="flex justify-start">
                <div class="glass-dark border border-white/[0.07] rounded-3xl rounded-tl-none px-5 py-3">
                    <div class="flex items-center gap-1.5">
                        <span class="w-1.5 h-1.5 rounded-full bg-sanaa-indigo/60 animate-bounce" style="animation-delay:0ms"></span>
                        <span class="w-1.5 h-1.5 rounded-full bg-sanaa-indigo/60 animate-bounce" style="animation-delay:120ms"></span>
                        <span class="w-1.5 h-1.5 rounded-full bg-sanaa-indigo/60 animate-bounce" style="animation-delay:240ms"></span>
                    </div>
                </div>
            </div>
        @endif
    </div>

    {{-- Input Area with Autocomplete --}}
    <div class="relative z-10">
        {{-- Skill Suggestions Dropdown --}}
        <template x-if="showSuggestions && filteredSuggestions.length > 0">
            <div class="absolute bottom-full left-0 right-0 mb-2 glass-dark border border-white/10 rounded-2xl overflow-hidden shadow-2xl max-h-48 overflow-y-auto chat-scroll z-50">
                <template x-for="(suggestion, idx) in filteredSuggestions" :key="suggestion.name">
                    <button
                        type="button"
                        @click="applySuggestion(suggestion.name)"
                        @mouseenter="selectedSuggestionIndex = idx"
                        :class="idx === selectedSuggestionIndex ? 'bg-sanaa-indigo/20 border-l-2 border-sanaa-indigo' : 'border-l-2 border-transparent'"
                        class="w-full flex items-center gap-3 px-4 py-2 text-left hover:bg-white/5 transition-all"
                    >
                        <x-heroicon-m-bolt class="w-3.5 h-3.5 text-sanaa-indigo/60 flex-shrink-0"/>
                        <div class="flex-1 min-w-0">
                            <span class="text-[12px] text-white/80 font-medium" x-text="suggestion.name"></span>
                        </div>
                        <span class="text-[9px] text-white/30 uppercase tracking-wider px-1.5 py-0.5 rounded-full glass" x-text="suggestion.category"></span>
                    </button>
                </template>
            </div>
        </template>

        <form wire:submit.prevent="send" @submit="onSubmit" class="relative group/input">
            <div class="absolute inset-0 bg-sanaa-indigo/5 rounded-[1.5rem] blur-xl group-focus-within/input:bg-sanaa-indigo/10 transition-all duration-500"></div>

            <input
                type="text"
                wire:model="command"
                x-ref="commandInput"
                @keydown.up.prevent="navigateHistory('up')"
                @keydown.down.prevent="navigateHistory('down')"
                @keydown.escape="closeSuggestions()"
                @keydown.tab.prevent="acceptSuggestion()"
                @input.debounce.150ms="onInputChange($event.target.value)"
                @if($isLoading) disabled @endif
                class="relative w-full glass bg-white/5 border border-white/10 rounded-[1.5rem] pl-5 pr-14 py-3.5 text-[13px] text-white placeholder-white/20 focus:outline-none focus:ring-0 focus:ring-transparent focus:border-sanaa-indigo/50 transition-all shadow-2xl @if($isLoading) opacity-60 @endif"
                placeholder="@if($isLoading) Processing... @else Type a command or ask anything... try 'help' @endif"
                autofocus
                autocomplete="off"
            >

            <button
                type="submit"
                @if($isLoading) disabled @endif
                class="absolute right-2 top-1/2 -translate-y-1/2 w-9 h-9 rounded-xl bg-sanaa-indigo flex items-center justify-center text-white shadow-lg shadow-sanaa-indigo/20 hover:scale-105 hover:bg-sanaa-purple transition-all active:scale-95 group/btn @if($isLoading) opacity-40 cursor-not-allowed @endif"
            >
                @if($isLoading)
                    <x-heroicon-m-arrow-path class="w-4 h-4 animate-spin"/>
                @else
                    <x-heroicon-m-bolt class="w-4 h-4"/>
                @endif
            </button>
        </form>
    </div>

    <script>
        function sanaaTerminal(initialHistory, initialSuggestions) {
            return {
                // Command history for up/down navigation
                cmdHistory: [],
                historyIndex: -1,
                currentDraft: '',

                // Skill autocomplete
                allSkills: initialSuggestions || [],
                showSuggestions: false,
                filteredSuggestions: [],
                selectedSuggestionIndex: 0,

                // localStorage key
                storageKey: 'sanaa_terminal_history',

                init() {
                    // Restore command history from localStorage
                    try {
                        const stored = localStorage.getItem(this.storageKey);
                        if (stored) {
                            const parsed = JSON.parse(stored);
                            if (Array.isArray(parsed)) {
                                this.cmdHistory = parsed;
                                // Sync with Livewire
                                @this.set('commandHistory', this.cmdHistory);
                            }
                        }
                    } catch (e) {
                        console.warn('Failed to restore terminal history:', e);
                    }

                    // Merge any server-side history
                    if (Array.isArray(initialHistory) && initialHistory.length > 0) {
                        const existing = new Set(this.cmdHistory);
                        initialHistory.forEach(cmd => {
                            if (!existing.has(cmd)) {
                                this.cmdHistory.push(cmd);
                            }
                        });
                    }

                    // Load skill suggestions if empty
                    if (this.allSkills.length === 0) {
                        @this.call('getSkillNames');
                    }

                    // Scroll to bottom on new messages
                    const scrollToBottom = () => {
                        const el = document.getElementById('terminal-history');
                        if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
                    };
                    Livewire.on('command-sent', () => setTimeout(scrollToBottom, 60));

                    // Watch for Livewire skill suggestions updates
                    this.$watch('$wire.skillSuggestions', (val) => {
                        if (Array.isArray(val)) this.allSkills = val;
                    });

                    // Make collapsible JSON sections interactive
                    this.$nextTick(() => this.enhanceOutput());

                    // Re-enhance after Livewire morphs the DOM
                    Livewire.hook('morph.updated', ({el}) => {
                        this.$nextTick(() => this.enhanceOutput());
                    });
                },

                onSubmit() {
                    const input = this.$refs.commandInput;
                    const cmd = (input ? input.value : '').trim();
                    if (!cmd) return;

                    // Add to local history
                    this.cmdHistory.push(cmd);
                    this.historyIndex = -1;
                    this.currentDraft = '';

                    // Persist to localStorage (keep last 200)
                    try {
                        const toStore = this.cmdHistory.slice(-200);
                        localStorage.setItem(this.storageKey, JSON.stringify(toStore));
                    } catch (e) {
                        console.warn('Failed to save terminal history:', e);
                    }

                    this.closeSuggestions();
                },

                navigateHistory(direction) {
                    if (this.showSuggestions && this.filteredSuggestions.length > 0) {
                        // Navigate suggestions instead
                        if (direction === 'up') {
                            this.selectedSuggestionIndex = Math.max(0, this.selectedSuggestionIndex - 1);
                        } else {
                            this.selectedSuggestionIndex = Math.min(this.filteredSuggestions.length - 1, this.selectedSuggestionIndex + 1);
                        }
                        return;
                    }

                    const history = this.cmdHistory;
                    if (history.length === 0) return;

                    if (direction === 'up') {
                        if (this.historyIndex === -1) {
                            this.currentDraft = this.$refs.commandInput.value;
                            this.historyIndex = history.length - 1;
                        } else if (this.historyIndex > 0) {
                            this.historyIndex--;
                        }
                        @this.set('command', history[this.historyIndex]);
                    } else {
                        if (this.historyIndex === -1) return;
                        if (this.historyIndex < history.length - 1) {
                            this.historyIndex++;
                            @this.set('command', history[this.historyIndex]);
                        } else {
                            this.historyIndex = -1;
                            @this.set('command', this.currentDraft);
                        }
                    }
                },

                onInputChange(value) {
                    const lower = value.toLowerCase().trim();

                    // Show skill suggestions when typing 'run skill ' prefix
                    if (lower.startsWith('run skill ') || lower.startsWith('skill ')) {
                        const prefix = lower.startsWith('run skill ') ? 'run skill ' : 'skill ';
                        const partial = lower.slice(prefix.length).trim();

                        if (partial.length === 0) {
                            this.filteredSuggestions = this.allSkills.slice(0, 15);
                        } else {
                            this.filteredSuggestions = this.allSkills.filter(s =>
                                s.name.toLowerCase().includes(partial)
                            ).slice(0, 10);
                        }

                        this.showSuggestions = this.filteredSuggestions.length > 0;
                        this.selectedSuggestionIndex = 0;
                    } else {
                        this.closeSuggestions();
                    }
                },

                applySuggestion(name) {
                    const current = this.$refs.commandInput.value.toLowerCase().trim();
                    const prefix = current.startsWith('run skill') ? 'run skill ' : 'skill ';
                    @this.set('command', prefix + name);
                    this.closeSuggestions();
                    this.$refs.commandInput.focus();
                },

                acceptSuggestion() {
                    if (this.showSuggestions && this.filteredSuggestions.length > 0) {
                        const selected = this.filteredSuggestions[this.selectedSuggestionIndex];
                        if (selected) {
                            this.applySuggestion(selected.name);
                        }
                    }
                },

                closeSuggestions() {
                    this.showSuggestions = false;
                    this.filteredSuggestions = [];
                    this.selectedSuggestionIndex = 0;
                },

                enhanceOutput() {
                    // Make JSON code blocks collapsible
                    document.querySelectorAll('.terminal-content pre code').forEach(codeEl => {
                        const pre = codeEl.parentElement;
                        if (!pre || pre.dataset.enhanced) return;
                        pre.dataset.enhanced = 'true';

                        const text = codeEl.textContent.trim();
                        // Only enhance JSON blocks that are fairly large
                        if (text.length < 100) return;

                        try {
                            JSON.parse(text);
                        } catch (e) {
                            return; // Not JSON, skip
                        }

                        // Wrap in collapsible
                        const wrapper = document.createElement('details');
                        wrapper.className = 'json-collapsible group/json';
                        wrapper.open = text.length < 500;

                        const summary = document.createElement('summary');
                        summary.className = 'cursor-pointer text-[10px] text-sanaa-indigo/70 hover:text-sanaa-indigo uppercase tracking-wider font-bold py-1 select-none';
                        summary.textContent = wrapper.open ? '▾ JSON Data' : '▸ JSON Data (click to expand)';

                        wrapper.addEventListener('toggle', () => {
                            summary.textContent = wrapper.open ? '▾ JSON Data' : '▸ JSON Data (click to expand)';
                        });

                        pre.parentNode.insertBefore(wrapper, pre);
                        wrapper.appendChild(summary);
                        wrapper.appendChild(pre);
                    });

                    // Enhance tables
                    document.querySelectorAll('.terminal-content table').forEach(table => {
                        if (table.dataset.enhanced) return;
                        table.dataset.enhanced = 'true';
                        table.classList.add('terminal-table');
                    });
                }
            };
        }
    </script>

    <style>
        .chat-scroll::-webkit-scrollbar { width: 3px; }
        .chat-scroll::-webkit-scrollbar-track { background: transparent; }
        .chat-scroll::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.12); border-radius: 99px; }
        .chat-scroll::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.22); }

        .prose-xs { font-size: 0.75rem; line-height: 1.65; }
        .prose-xs p { margin-top: 0.4em; margin-bottom: 0.4em; }
        .prose-xs pre { font-size: 0.7rem; }

        /* Rich table rendering */
        .terminal-content table.terminal-table,
        .terminal-content table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.7rem;
            margin: 0.5rem 0;
        }
        .terminal-content table th {
            text-align: left;
            padding: 0.35rem 0.5rem;
            border-bottom: 1px solid rgba(255,255,255,0.1);
            color: rgba(255,255,255,0.5);
            font-weight: 700;
            font-size: 0.65rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        .terminal-content table td {
            padding: 0.3rem 0.5rem;
            border-bottom: 1px solid rgba(255,255,255,0.04);
            color: rgba(255,255,255,0.65);
        }
        .terminal-content table tr:hover td {
            background: rgba(255,255,255,0.03);
        }

        /* Syntax highlighting for code blocks */
        .terminal-content pre {
            background: rgba(0,0,0,0.4) !important;
            border: 1px solid rgba(255,255,255,0.05) !important;
            border-radius: 0.75rem;
            padding: 0.75rem 1rem;
            overflow-x: auto;
            max-height: 300px;
            overflow-y: auto;
        }
        .terminal-content pre code {
            font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
            font-size: 0.7rem;
            line-height: 1.5;
            color: rgba(255,255,255,0.7);
        }

        /* JSON collapsible sections */
        .json-collapsible summary {
            list-style: none;
        }
        .json-collapsible summary::-webkit-details-marker {
            display: none;
        }
        .json-collapsible[open] pre {
            animation: fadeIn 0.15s ease;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(-4px); }
            to { opacity: 1; transform: translateY(0); }
        }

        /* Inline code styling */
        .terminal-content code:not(pre code) {
            background: rgba(99,102,241,0.15);
            color: rgba(165,180,252,0.9);
            padding: 0.1em 0.35em;
            border-radius: 0.3rem;
            font-size: 0.85em;
            font-family: 'JetBrains Mono', 'Fira Code', monospace;
        }
    </style>
</div>

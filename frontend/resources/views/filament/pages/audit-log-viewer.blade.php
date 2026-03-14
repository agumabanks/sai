<x-filament-panels::page class="relative">
    {{-- Ambient Background --}}
    <div class="fixed inset-0 z-0 pointer-events-none w-full h-full overflow-hidden">
        <div class="absolute inset-0 bg-[#000000]"></div>
        <div class="absolute top-[-20%] left-[10%] w-[60vw] h-[60vw] bg-[#6366f1]/15 blur-[140px] rounded-[100%] mix-blend-screen opacity-50"></div>
        <div class="absolute bottom-[-10%] right-[-10%] w-[50vw] h-[50vw] bg-[#06b6d4]/10 blur-[120px] rounded-[100%] mix-blend-screen opacity-40"></div>
    </div>

    <div class="relative z-10 space-y-6 max-w-[1400px] mx-auto">

        {{-- ── Header ──────────────────────────────────────────────────────── --}}
        <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div class="flex items-center gap-4">
                <div class="w-11 h-11 rounded-2xl bg-gradient-to-br from-[#6366f1] to-[#06b6d4] flex items-center justify-center shadow-lg shadow-[#6366f1]/20">
                    @svg('heroicon-o-clipboard-document-list', 'w-6 h-6 text-white')
                </div>
                <div>
                    <h1 class="text-lg font-semibold tracking-tight text-white/95">Audit Log</h1>
                    <p class="text-[11px] text-white/35 tracking-wide font-medium">{{ number_format($this->getTotal()) }} Total Entries</p>
                </div>
            </div>
            <div class="flex items-center gap-2.5 flex-wrap">
                <div class="flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/[0.05] border border-white/[0.08] backdrop-blur-md text-[11px] font-medium text-white/50 uppercase tracking-wide">
                    <span class="w-1.5 h-1.5 rounded-full bg-[#6366f1]"></span>
                    Page {{ $currentPage }} of {{ $this->getTotalPages() ?: 1 }}
                </div>
                <x-filament::button size="sm" wire:click="refreshData" icon="heroicon-o-arrow-path">
                    Refresh
                </x-filament::button>
            </div>
        </div>

        {{-- ── Filters ─────────────────────────────────────────────────────── --}}
        <div class="rounded-2xl bg-white/[0.03] border border-white/[0.06] backdrop-blur-md p-5">
            <p class="text-[10px] font-semibold tracking-[0.15em] text-white/25 uppercase mb-4">Filters</p>
            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3">
                {{-- Date From --}}
                <div>
                    <label class="block text-[10px] font-medium text-white/40 uppercase tracking-wider mb-1">From Date</label>
                    <input type="datetime-local" wire:model.defer="filterDateFrom"
                        class="w-full px-3 py-2 rounded-lg bg-white/[0.05] border border-white/[0.08] text-white/80 text-xs placeholder-white/20 focus:border-[#6366f1]/50 focus:outline-none focus:ring-1 focus:ring-[#6366f1]/30" />
                </div>
                {{-- Date To --}}
                <div>
                    <label class="block text-[10px] font-medium text-white/40 uppercase tracking-wider mb-1">To Date</label>
                    <input type="datetime-local" wire:model.defer="filterDateTo"
                        class="w-full px-3 py-2 rounded-lg bg-white/[0.05] border border-white/[0.08] text-white/80 text-xs placeholder-white/20 focus:border-[#6366f1]/50 focus:outline-none focus:ring-1 focus:ring-[#6366f1]/30" />
                </div>
                {{-- Action (HTTP Method) --}}
                <div>
                    <label class="block text-[10px] font-medium text-white/40 uppercase tracking-wider mb-1">Method</label>
                    <select wire:model.defer="filterAction"
                        class="w-full px-3 py-2 rounded-lg bg-white/[0.05] border border-white/[0.08] text-white/80 text-xs focus:border-[#6366f1]/50 focus:outline-none focus:ring-1 focus:ring-[#6366f1]/30">
                        <option value="">All Methods</option>
                        <option value="GET">GET</option>
                        <option value="POST">POST</option>
                        <option value="PUT">PUT</option>
                        <option value="PATCH">PATCH</option>
                        <option value="DELETE">DELETE</option>
                    </select>
                </div>
                {{-- Actor --}}
                <div>
                    <label class="block text-[10px] font-medium text-white/40 uppercase tracking-wider mb-1">User / IP</label>
                    <input type="text" wire:model.defer="filterActor" placeholder="e.g. admin@sanaa.co"
                        class="w-full px-3 py-2 rounded-lg bg-white/[0.05] border border-white/[0.08] text-white/80 text-xs placeholder-white/20 focus:border-[#6366f1]/50 focus:outline-none focus:ring-1 focus:ring-[#6366f1]/30" />
                </div>
                {{-- Path --}}
                <div>
                    <label class="block text-[10px] font-medium text-white/40 uppercase tracking-wider mb-1">Path</label>
                    <input type="text" wire:model.defer="filterPath" placeholder="e.g. /api/skills"
                        class="w-full px-3 py-2 rounded-lg bg-white/[0.05] border border-white/[0.08] text-white/80 text-xs placeholder-white/20 focus:border-[#6366f1]/50 focus:outline-none focus:ring-1 focus:ring-[#6366f1]/30" />
                </div>
                {{-- Buttons --}}
                <div class="flex items-end gap-2">
                    <x-filament::button size="sm" wire:click="applyFilters" icon="heroicon-o-funnel" class="flex-1">
                        Filter
                    </x-filament::button>
                    <x-filament::button size="sm" wire:click="clearFilters" color="gray" icon="heroicon-o-x-mark">
                        Clear
                    </x-filament::button>
                </div>
            </div>
        </div>

        {{-- ── Audit Log Table ─────────────────────────────────────────────── --}}
        <div class="rounded-2xl bg-white/[0.03] border border-white/[0.06] backdrop-blur-md overflow-hidden">
            <div class="overflow-x-auto">
                <table class="w-full text-xs">
                    <thead>
                        <tr class="border-b border-white/[0.06]">
                            <th class="px-4 py-3 text-left text-[10px] font-semibold tracking-[0.12em] text-white/30 uppercase">Timestamp</th>
                            <th class="px-4 py-3 text-left text-[10px] font-semibold tracking-[0.12em] text-white/30 uppercase">Method</th>
                            <th class="px-4 py-3 text-left text-[10px] font-semibold tracking-[0.12em] text-white/30 uppercase">Path</th>
                            <th class="px-4 py-3 text-left text-[10px] font-semibold tracking-[0.12em] text-white/30 uppercase">Actor</th>
                            <th class="px-4 py-3 text-left text-[10px] font-semibold tracking-[0.12em] text-white/30 uppercase">IP</th>
                            <th class="px-4 py-3 text-center text-[10px] font-semibold tracking-[0.12em] text-white/30 uppercase">Status</th>
                            <th class="px-4 py-3 text-right text-[10px] font-semibold tracking-[0.12em] text-white/30 uppercase">Time</th>
                            <th class="px-4 py-3 text-center text-[10px] font-semibold tracking-[0.12em] text-white/30 uppercase"></th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-white/[0.04]">
                        @forelse ($this->getEntries() as $entry)
                            <tr class="hover:bg-white/[0.02] transition-colors duration-150 cursor-pointer"
                                wire:click="viewEntry({{ $entry['id'] ?? 0 }})">
                                <td class="px-4 py-3 text-white/60 whitespace-nowrap">
                                    {{ $this->formatTimestamp($entry['timestamp'] ?? null) }}
                                </td>
                                <td class="px-4 py-3">
                                    <span class="inline-flex px-2 py-0.5 rounded text-[10px] font-bold tracking-wider border {{ $this->getMethodBadge($this->getMethod($entry['action'] ?? '')) }}">
                                        {{ $this->getMethod($entry['action'] ?? '') }}
                                    </span>
                                </td>
                                <td class="px-4 py-3 text-white/70 font-mono text-[11px] max-w-[250px] truncate">
                                    {{ $this->getPath($entry['action'] ?? '') }}
                                </td>
                                <td class="px-4 py-3 text-white/50 max-w-[180px] truncate">
                                    {{ $entry['actor'] ?? '—' }}
                                </td>
                                <td class="px-4 py-3 text-white/40 font-mono text-[11px]">
                                    {{ $entry['ip_address'] ?? '—' }}
                                </td>
                                <td class="px-4 py-3 text-center">
                                    @php $badge = $this->getSuccessBadge($entry['success'] ?? true); @endphp
                                    <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium border {{ $badge['color'] }}">
                                        <span class="w-1 h-1 rounded-full {{ ($entry['success'] ?? true) ? 'bg-[#30d158]' : 'bg-[#ff453a]' }}"></span>
                                        {{ $badge['label'] }}
                                    </span>
                                </td>
                                <td class="px-4 py-3 text-right text-white/40 font-mono text-[11px]">
                                    {{ isset($entry['elapsed_ms']) ? $entry['elapsed_ms'] . 'ms' : '—' }}
                                </td>
                                <td class="px-4 py-3 text-center">
                                    <button class="text-white/20 hover:text-white/60 transition-colors">
                                        @svg('heroicon-o-eye', 'w-4 h-4')
                                    </button>
                                </td>
                            </tr>
                        @empty
                            <tr>
                                <td colspan="8" class="px-4 py-12 text-center text-white/30">
                                    <div class="flex flex-col items-center gap-2">
                                        @svg('heroicon-o-clipboard-document-list', 'w-8 h-8 text-white/15')
                                        <p>No audit log entries found</p>
                                        <p class="text-[10px] text-white/20">Try adjusting your filters</p>
                                    </div>
                                </td>
                            </tr>
                        @endforelse
                    </tbody>
                </table>
            </div>

            {{-- ── Pagination ──────────────────────────────────────────────── --}}
            @if ($this->getTotalPages() > 1)
                <div class="flex items-center justify-between px-4 py-3 border-t border-white/[0.06]">
                    <div class="text-[11px] text-white/30">
                        Showing {{ (($currentPage - 1) * $perPage) + 1 }}–{{ min($currentPage * $perPage, $this->getTotal()) }}
                        of {{ number_format($this->getTotal()) }}
                    </div>
                    <div class="flex items-center gap-1.5">
                        <button wire:click="previousPage" @disabled($currentPage <= 1)
                            class="px-2.5 py-1.5 rounded-lg bg-white/[0.05] border border-white/[0.08] text-white/50 text-[11px] hover:bg-white/[0.08] disabled:opacity-30 disabled:cursor-not-allowed transition-colors">
                            @svg('heroicon-o-chevron-left', 'w-3.5 h-3.5')
                        </button>

                        @for ($i = max(1, $currentPage - 2); $i <= min($this->getTotalPages(), $currentPage + 2); $i++)
                            <button wire:click="goToPage({{ $i }})"
                                class="px-2.5 py-1.5 rounded-lg text-[11px] transition-colors
                                    {{ $i === $currentPage
                                        ? 'bg-[#6366f1]/20 border border-[#6366f1]/30 text-[#6366f1]'
                                        : 'bg-white/[0.05] border border-white/[0.08] text-white/50 hover:bg-white/[0.08]' }}">
                                {{ $i }}
                            </button>
                        @endfor

                        <button wire:click="nextPage" @disabled($currentPage >= $this->getTotalPages())
                            class="px-2.5 py-1.5 rounded-lg bg-white/[0.05] border border-white/[0.08] text-white/50 text-[11px] hover:bg-white/[0.08] disabled:opacity-30 disabled:cursor-not-allowed transition-colors">
                            @svg('heroicon-o-chevron-right', 'w-3.5 h-3.5')
                        </button>
                    </div>
                </div>
            @endif
        </div>

        {{-- ── Detail Modal ────────────────────────────────────────────────── --}}
        @if ($selectedEntry)
            <div class="fixed inset-0 z-50 flex items-center justify-center p-4" x-data>
                {{-- Backdrop --}}
                <div class="absolute inset-0 bg-black/60 backdrop-blur-sm" wire:click="closeDetail"></div>

                {{-- Modal --}}
                <div class="relative w-full max-w-2xl rounded-2xl bg-[#0a0a0f]/95 border border-white/[0.08] backdrop-blur-xl shadow-2xl overflow-hidden">
                    {{-- Header --}}
                    <div class="flex items-center justify-between px-6 py-4 border-b border-white/[0.06]">
                        <div class="flex items-center gap-3">
                            @svg('heroicon-o-clipboard-document-list', 'w-5 h-5 text-[#6366f1]')
                            <h3 class="text-sm font-semibold text-white/90">Audit Entry #{{ $selectedEntry['id'] ?? '—' }}</h3>
                        </div>
                        <button wire:click="closeDetail" class="text-white/30 hover:text-white/60 transition-colors">
                            @svg('heroicon-o-x-mark', 'w-5 h-5')
                        </button>
                    </div>

                    {{-- Content --}}
                    <div class="px-6 py-5 space-y-4 max-h-[70vh] overflow-y-auto">
                        <div class="grid grid-cols-2 gap-4">
                            <div>
                                <p class="text-[10px] font-semibold tracking-[0.12em] text-white/25 uppercase mb-1">Timestamp</p>
                                <p class="text-xs text-white/70">{{ $this->formatTimestamp($selectedEntry['timestamp'] ?? null) }}</p>
                            </div>
                            <div>
                                <p class="text-[10px] font-semibold tracking-[0.12em] text-white/25 uppercase mb-1">Actor</p>
                                <p class="text-xs text-white/70">{{ $selectedEntry['actor'] ?? '—' }}</p>
                            </div>
                            <div>
                                <p class="text-[10px] font-semibold tracking-[0.12em] text-white/25 uppercase mb-1">Action</p>
                                <p class="text-xs text-white/70 font-mono">{{ $selectedEntry['action'] ?? '—' }}</p>
                            </div>
                            <div>
                                <p class="text-[10px] font-semibold tracking-[0.12em] text-white/25 uppercase mb-1">Status</p>
                                @php $badge = $this->getSuccessBadge($selectedEntry['success'] ?? true); @endphp
                                <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium border {{ $badge['color'] }}">
                                    {{ $badge['label'] }}
                                </span>
                            </div>
                            <div>
                                <p class="text-[10px] font-semibold tracking-[0.12em] text-white/25 uppercase mb-1">IP Address</p>
                                <p class="text-xs text-white/70 font-mono">{{ $selectedEntry['ip_address'] ?? '—' }}</p>
                            </div>
                            <div>
                                <p class="text-[10px] font-semibold tracking-[0.12em] text-white/25 uppercase mb-1">Response Time</p>
                                <p class="text-xs text-white/70 font-mono">{{ isset($selectedEntry['elapsed_ms']) ? $selectedEntry['elapsed_ms'] . 'ms' : '—' }}</p>
                            </div>
                        </div>

                        @if (!empty($selectedEntry['resource']))
                            <div>
                                <p class="text-[10px] font-semibold tracking-[0.12em] text-white/25 uppercase mb-1">Resource</p>
                                <p class="text-xs text-white/70 font-mono break-all">{{ $selectedEntry['resource'] }}</p>
                            </div>
                        @endif

                        @if (!empty($selectedEntry['user_agent']))
                            <div>
                                <p class="text-[10px] font-semibold tracking-[0.12em] text-white/25 uppercase mb-1">User Agent</p>
                                <p class="text-xs text-white/50 break-all">{{ $selectedEntry['user_agent'] }}</p>
                            </div>
                        @endif

                        @if (!empty($selectedEntry['error']))
                            <div>
                                <p class="text-[10px] font-semibold tracking-[0.12em] text-[#ff453a]/60 uppercase mb-1">Error</p>
                                <p class="text-xs text-[#ff453a]/80 font-mono">{{ $selectedEntry['error'] }}</p>
                            </div>
                        @endif

                        @if (!empty($selectedEntry['details']))
                            <div>
                                <p class="text-[10px] font-semibold tracking-[0.12em] text-white/25 uppercase mb-1">Raw Details</p>
                                <pre class="text-[11px] text-white/40 bg-white/[0.03] rounded-lg p-3 overflow-x-auto border border-white/[0.06]">{{ json_encode($selectedEntry['details'], JSON_PRETTY_PRINT) }}</pre>
                            </div>
                        @endif
                    </div>

                    {{-- Footer --}}
                    <div class="px-6 py-3 border-t border-white/[0.06] flex justify-end">
                        <x-filament::button size="sm" wire:click="closeDetail" color="gray">
                            Close
                        </x-filament::button>
                    </div>
                </div>
            </div>
        @endif

    </div>
</x-filament-panels::page>

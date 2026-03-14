<x-filament-panels::page class="relative">
    {{-- Ambient Background --}}
    <div class="fixed inset-0 z-0 pointer-events-none w-full h-full overflow-hidden">
        <div class="absolute inset-0 bg-[#000000]"></div>
        <div class="absolute top-[-20%] left-[10%] w-[60vw] h-[60vw] bg-[#f43f5e]/15 blur-[140px] rounded-[100%] mix-blend-screen opacity-50"></div>
        <div class="absolute bottom-[-10%] right-[-10%] w-[50vw] h-[50vw] bg-[#ff9f0a]/10 blur-[120px] rounded-[100%] mix-blend-screen opacity-40"></div>
    </div>

    <div class="relative z-10 space-y-6 max-w-[1400px] mx-auto">

        {{-- ── Header ──────────────────────────────────────────────────────── --}}
        <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div class="flex items-center gap-4">
                <div class="w-11 h-11 rounded-2xl bg-gradient-to-br from-[#f43f5e] to-[#ff9f0a] flex items-center justify-center shadow-lg shadow-[#f43f5e]/20">
                    @svg('heroicon-o-bell-alert', 'w-6 h-6 text-white')
                </div>
                <div>
                    <h1 class="text-lg font-semibold tracking-tight text-white/95">Alert Configuration</h1>
                    <p class="text-[11px] text-white/35 tracking-wide font-medium">{{ $this->getRuleCount() }} Rules · {{ $this->getEnabledCount() }} Enabled</p>
                </div>
            </div>
            <div class="flex items-center gap-2.5 flex-wrap">
                <x-filament::button size="sm" wire:click="showCreateForm" icon="heroicon-o-plus" color="primary">
                    New Rule
                </x-filament::button>
                <x-filament::button size="sm" wire:click="refreshData" icon="heroicon-o-arrow-path" color="gray">
                    Refresh
                </x-filament::button>
            </div>
        </div>

        {{-- ── Create / Edit Form ──────────────────────────────────────────── --}}
        @if ($showForm)
            <div class="rounded-2xl bg-white/[0.03] border border-white/[0.06] backdrop-blur-md p-6">
                <div class="flex items-center justify-between mb-5">
                    <div class="flex items-center gap-3">
                        @svg($editingRuleId ? 'heroicon-o-pencil-square' : 'heroicon-o-plus-circle', 'w-5 h-5 text-[#f43f5e]')
                        <h2 class="text-sm font-semibold text-white/90">
                            {{ $editingRuleId ? 'Edit Alert Rule' : 'Create Alert Rule' }}
                        </h2>
                    </div>
                    <button wire:click="cancelForm" class="text-white/30 hover:text-white/60 transition-colors">
                        @svg('heroicon-o-x-mark', 'w-5 h-5')
                    </button>
                </div>

                <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    {{-- Name --}}
                    <div>
                        <label class="block text-[10px] font-medium text-white/40 uppercase tracking-wider mb-1">Rule Name</label>
                        <input type="text" wire:model.defer="formName" placeholder="e.g. High CPU Alert"
                            class="w-full px-3 py-2 rounded-lg bg-white/[0.05] border border-white/[0.08] text-white/80 text-xs placeholder-white/20 focus:border-[#f43f5e]/50 focus:outline-none focus:ring-1 focus:ring-[#f43f5e]/30" />
                    </div>
                    {{-- Condition --}}
                    <div>
                        <label class="block text-[10px] font-medium text-white/40 uppercase tracking-wider mb-1">Condition</label>
                        <input type="text" wire:model.defer="formCondition" placeholder="e.g. cpu_usage > threshold"
                            class="w-full px-3 py-2 rounded-lg bg-white/[0.05] border border-white/[0.08] text-white/80 text-xs placeholder-white/20 focus:border-[#f43f5e]/50 focus:outline-none focus:ring-1 focus:ring-[#f43f5e]/30" />
                    </div>
                    {{-- Threshold --}}
                    <div>
                        <label class="block text-[10px] font-medium text-white/40 uppercase tracking-wider mb-1">Threshold</label>
                        <input type="number" step="0.1" wire:model.defer="formThreshold" placeholder="e.g. 90"
                            class="w-full px-3 py-2 rounded-lg bg-white/[0.05] border border-white/[0.08] text-white/80 text-xs placeholder-white/20 focus:border-[#f43f5e]/50 focus:outline-none focus:ring-1 focus:ring-[#f43f5e]/30" />
                    </div>
                    {{-- Severity --}}
                    <div>
                        <label class="block text-[10px] font-medium text-white/40 uppercase tracking-wider mb-1">Severity</label>
                        <select wire:model.defer="formSeverity"
                            class="w-full px-3 py-2 rounded-lg bg-white/[0.05] border border-white/[0.08] text-white/80 text-xs focus:border-[#f43f5e]/50 focus:outline-none focus:ring-1 focus:ring-[#f43f5e]/30">
                            <option value="low">Low</option>
                            <option value="medium">Medium</option>
                            <option value="high">High</option>
                            <option value="critical">Critical</option>
                        </select>
                    </div>
                    {{-- Recipients --}}
                    <div>
                        <label class="block text-[10px] font-medium text-white/40 uppercase tracking-wider mb-1">Recipients (comma-separated)</label>
                        <input type="text" wire:model.defer="formRecipients" placeholder="e.g. admin@sanaa.co, ops@sanaa.co"
                            class="w-full px-3 py-2 rounded-lg bg-white/[0.05] border border-white/[0.08] text-white/80 text-xs placeholder-white/20 focus:border-[#f43f5e]/50 focus:outline-none focus:ring-1 focus:ring-[#f43f5e]/30" />
                    </div>
                    {{-- Enabled --}}
                    <div class="flex items-end">
                        <label class="flex items-center gap-2 cursor-pointer">
                            <input type="checkbox" wire:model.defer="formEnabled"
                                class="rounded border-white/20 bg-white/[0.05] text-[#f43f5e] focus:ring-[#f43f5e]/30 focus:ring-offset-0" />
                            <span class="text-xs text-white/60">Enabled</span>
                        </label>
                    </div>
                </div>

                {{-- Escalation & Quiet Hours --}}
                <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-4">
                    {{-- Escalation Policy (JSON) --}}
                    <div>
                        <label class="block text-[10px] font-medium text-white/40 uppercase tracking-wider mb-1">Escalation Policy (JSON)</label>
                        <textarea wire:model.defer="formEscalationPolicy" rows="4"
                            placeholder='{"tiers": [{"channel": "email", "delay_minutes": 0}, {"channel": "whatsapp", "delay_minutes": 15}]}'
                            class="w-full px-3 py-2 rounded-lg bg-white/[0.05] border border-white/[0.08] text-white/80 text-xs font-mono placeholder-white/20 focus:border-[#f43f5e]/50 focus:outline-none focus:ring-1 focus:ring-[#f43f5e]/30 resize-none"></textarea>
                    </div>
                    {{-- Quiet Hours --}}
                    <div>
                        <label class="block text-[10px] font-medium text-white/40 uppercase tracking-wider mb-1">Quiet Hours</label>
                        <div class="grid grid-cols-3 gap-2">
                            <div>
                                <label class="block text-[9px] text-white/25 mb-0.5">Start</label>
                                <input type="time" wire:model.defer="formQuietHoursStart"
                                    class="w-full px-2 py-2 rounded-lg bg-white/[0.05] border border-white/[0.08] text-white/80 text-xs focus:border-[#f43f5e]/50 focus:outline-none focus:ring-1 focus:ring-[#f43f5e]/30" />
                            </div>
                            <div>
                                <label class="block text-[9px] text-white/25 mb-0.5">End</label>
                                <input type="time" wire:model.defer="formQuietHoursEnd"
                                    class="w-full px-2 py-2 rounded-lg bg-white/[0.05] border border-white/[0.08] text-white/80 text-xs focus:border-[#f43f5e]/50 focus:outline-none focus:ring-1 focus:ring-[#f43f5e]/30" />
                            </div>
                            <div>
                                <label class="block text-[9px] text-white/25 mb-0.5">Timezone</label>
                                <input type="text" wire:model.defer="formQuietHoursTimezone" placeholder="Africa/Nairobi"
                                    class="w-full px-2 py-2 rounded-lg bg-white/[0.05] border border-white/[0.08] text-white/80 text-xs placeholder-white/20 focus:border-[#f43f5e]/50 focus:outline-none focus:ring-1 focus:ring-[#f43f5e]/30" />
                            </div>
                        </div>
                    </div>
                </div>

                {{-- Save / Cancel buttons --}}
                <div class="flex items-center justify-end gap-2.5 mt-5">
                    <x-filament::button size="sm" wire:click="cancelForm" color="gray">
                        Cancel
                    </x-filament::button>
                    <x-filament::button size="sm" wire:click="saveRule" icon="heroicon-o-check" color="primary">
                        {{ $editingRuleId ? 'Update Rule' : 'Create Rule' }}
                    </x-filament::button>
                </div>
            </div>
        @endif

        {{-- ── Alert Rules Table ───────────────────────────────────────────── --}}
        <div class="rounded-2xl bg-white/[0.03] border border-white/[0.06] backdrop-blur-md overflow-hidden">
            <div class="overflow-x-auto">
                <table class="w-full text-xs">
                    <thead>
                        <tr class="border-b border-white/[0.06]">
                            <th class="px-4 py-3 text-left text-[10px] font-semibold tracking-[0.12em] text-white/30 uppercase">Name</th>
                            <th class="px-4 py-3 text-left text-[10px] font-semibold tracking-[0.12em] text-white/30 uppercase">Condition</th>
                            <th class="px-4 py-3 text-center text-[10px] font-semibold tracking-[0.12em] text-white/30 uppercase">Threshold</th>
                            <th class="px-4 py-3 text-center text-[10px] font-semibold tracking-[0.12em] text-white/30 uppercase">Severity</th>
                            <th class="px-4 py-3 text-left text-[10px] font-semibold tracking-[0.12em] text-white/30 uppercase">Recipients</th>
                            <th class="px-4 py-3 text-center text-[10px] font-semibold tracking-[0.12em] text-white/30 uppercase">Status</th>
                            <th class="px-4 py-3 text-left text-[10px] font-semibold tracking-[0.12em] text-white/30 uppercase">Created</th>
                            <th class="px-4 py-3 text-center text-[10px] font-semibold tracking-[0.12em] text-white/30 uppercase">Actions</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-white/[0.04]">
                        @forelse ($rules as $rule)
                            <tr class="hover:bg-white/[0.02] transition-colors duration-150">
                                <td class="px-4 py-3 text-white/80 font-medium">
                                    {{ $rule['name'] ?? '—' }}
                                </td>
                                <td class="px-4 py-3 text-white/60 font-mono text-[11px] max-w-[200px] truncate">
                                    {{ $rule['condition'] ?? '—' }}
                                </td>
                                <td class="px-4 py-3 text-center text-white/70 font-mono">
                                    {{ $rule['threshold'] ?? '—' }}
                                </td>
                                <td class="px-4 py-3 text-center">
                                    <span class="inline-flex px-2 py-0.5 rounded text-[10px] font-bold tracking-wider border {{ $this->getSeverityBadge($rule['severity'] ?? '') }}">
                                        {{ $rule['severity'] ?? '—' }}
                                    </span>
                                </td>
                                <td class="px-4 py-3 text-white/50 max-w-[200px]">
                                    <div class="flex flex-wrap gap-1">
                                        @foreach (($rule['recipients'] ?? []) as $recipient)
                                            <span class="inline-flex px-1.5 py-0.5 rounded bg-white/[0.05] border border-white/[0.08] text-[10px] text-white/50">
                                                {{ $recipient }}
                                            </span>
                                        @endforeach
                                    </div>
                                </td>
                                <td class="px-4 py-3 text-center">
                                    @if ($rule['enabled'] ?? false)
                                        <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium border text-[#30d158] bg-[#30d158]/10 border-[#30d158]/20">
                                            <span class="w-1 h-1 rounded-full bg-[#30d158]"></span>
                                            Enabled
                                        </span>
                                    @else
                                        <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium border text-white/30 bg-white/5 border-white/10">
                                            <span class="w-1 h-1 rounded-full bg-white/30"></span>
                                            Disabled
                                        </span>
                                    @endif
                                </td>
                                <td class="px-4 py-3 text-white/40 whitespace-nowrap text-[11px]">
                                    {{ $this->formatTimestamp($rule['created_at'] ?? null) }}
                                </td>
                                <td class="px-4 py-3 text-center">
                                    <div class="flex items-center justify-center gap-1.5">
                                        <button wire:click="editRule({{ $rule['id'] ?? 0 }})" class="text-white/20 hover:text-[#0a84ff] transition-colors" title="Edit">
                                            @svg('heroicon-o-pencil-square', 'w-4 h-4')
                                        </button>
                                        <button wire:click="deleteRule({{ $rule['id'] ?? 0 }})" wire:confirm="Are you sure you want to delete this rule?"
                                            class="text-white/20 hover:text-[#ff453a] transition-colors" title="Delete">
                                            @svg('heroicon-o-trash', 'w-4 h-4')
                                        </button>
                                    </div>
                                </td>
                            </tr>
                        @empty
                            <tr>
                                <td colspan="8" class="px-4 py-12 text-center text-white/30">
                                    <div class="flex flex-col items-center gap-2">
                                        @svg('heroicon-o-bell-alert', 'w-8 h-8 text-white/15')
                                        <p>No alert rules configured</p>
                                        <p class="text-[10px] text-white/20">Click "New Rule" to create your first alert rule</p>
                                    </div>
                                </td>
                            </tr>
                        @endforelse
                    </tbody>
                </table>
            </div>
        </div>

    </div>
</x-filament-panels::page>

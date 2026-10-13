<x-filament-panels::page>
    {{-- Header --}}
    <x-filament::card>
        <div class="flex items-center justify-between">
            <div>
                <h2 class="text-lg font-semibold">Sanaa Finance — Central Command</h2>
                <div class="text-sm text-gray-500">
                    Cross-tenant monitoring for {{ $tenantCount }} finance instances.
                    @if ($this->hasAlerts())
                        <span class="text-amber-500 font-medium">{{ count($alerts) }} alert(s)</span>
                    @else
                        <span class="text-green-500">All systems healthy</span>
                    @endif
                </div>
            </div>
            <x-filament::button wire:click="refreshAll" size="sm" color="gray">Refresh</x-filament::button>
        </div>
    </x-filament::card>

    {{-- KPI Cards --}}
    <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mt-6">
        <x-filament::card>
            <div class="text-xs text-gray-500 uppercase tracking-wide">Total Clients</div>
            <div class="text-2xl font-bold mt-1">{{ number_format($this->getTotalClients()) }}</div>
        </x-filament::card>
        <x-filament::card>
            <div class="text-xs text-gray-500 uppercase tracking-wide">Active Loans</div>
            <div class="text-2xl font-bold mt-1">{{ number_format($this->getTotalActiveLoans()) }}</div>
        </x-filament::card>
        <x-filament::card>
            <div class="text-xs text-gray-500 uppercase tracking-wide">Open Arrears</div>
            <div class="text-2xl font-bold mt-1 {{ $this->getTotalArrears() > 0 ? 'text-amber-500' : '' }}">
                {{ number_format($this->getTotalArrears()) }}
            </div>
        </x-filament::card>
        <x-filament::card>
            <div class="text-xs text-gray-500 uppercase tracking-wide">Failed Jobs</div>
            <div class="text-2xl font-bold mt-1 {{ $this->getTotalFailedJobs() > 0 ? 'text-red-500' : '' }}">
                {{ $this->getTotalFailedJobs() }}
            </div>
            @if ($this->getTotalFailedJobs() > 0)
                <button wire:click="fixFailedJobs" class="text-xs text-red-500 hover:underline mt-1">Retry all</button>
            @endif
        </x-filament::card>
    </div>

    {{-- Alerts Banner --}}
    @if ($this->hasAlerts())
        <div class="mt-4 p-3 rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800">
            <div class="text-sm font-medium text-amber-800 dark:text-amber-200 mb-1">Alerts</div>
            @foreach ($alerts as $alert)
                <div class="text-xs text-amber-700 dark:text-amber-300">{{ $alert }}</div>
            @endforeach
        </div>
    @endif

    <div class="grid gap-6 lg:grid-cols-3 mt-6">
        {{-- ========== Left: Per-Tenant Overview ========== --}}
        <div class="lg:col-span-2 space-y-4">
            {{-- Per-Tenant Cards --}}
            @foreach ($overview as $domain => $data)
                <x-filament::card>
                    <div class="flex items-center justify-between mb-2">
                        <div class="flex items-center gap-2">
                            <span class="inline-flex h-2.5 w-2.5 rounded-full {{ ($data['worker'] ?? '') === 'RUNNING' ? 'bg-green-500' : 'bg-red-500' }}"
                                  title="Worker: {{ $data['worker'] ?? 'unknown' }}"></span>
                            <a href="https://{{ $domain }}" target="_blank"
                               class="text-sm font-semibold text-primary-600 hover:underline">
                                {{ $domain }}
                            </a>
                        </div>
                        <div class="flex gap-1">
                            <button wire:click="runCheck('metrics', '{{ $domain }}')"
                                class="text-xs px-2 py-1 rounded bg-blue-50 text-blue-700 hover:bg-blue-100 dark:bg-blue-900/30 dark:text-blue-300 transition">
                                Metrics
                            </button>
                            <button wire:click="runCheck('arrears', '{{ $domain }}')"
                                class="text-xs px-2 py-1 rounded bg-amber-50 text-amber-700 hover:bg-amber-100 dark:bg-amber-900/30 dark:text-amber-300 transition">
                                Arrears
                            </button>
                        </div>
                    </div>

                    <div class="grid grid-cols-3 gap-4 text-center">
                        <div>
                            <div class="text-xs text-gray-400">Clients</div>
                            <div class="text-lg font-semibold">{{ number_format($data['clients'] ?? 0) }}</div>
                        </div>
                        <div>
                            <div class="text-xs text-gray-400">Active Loans</div>
                            <div class="text-lg font-semibold">{{ number_format($data['active_loans'] ?? 0) }}</div>
                        </div>
                        <div>
                            <div class="text-xs text-gray-400">Arrears</div>
                            <div class="text-lg font-semibold {{ ($data['open_arrears'] ?? 0) > 0 ? 'text-amber-500' : '' }}">
                                {{ number_format($data['open_arrears'] ?? 0) }}
                            </div>
                        </div>
                    </div>

                    <div class="grid grid-cols-2 gap-4 mt-3 pt-3 border-t border-gray-100 dark:border-gray-700">
                        <div>
                            <span class="text-xs text-gray-400">Month disbursed:</span>
                            <span class="text-xs font-medium ml-1">{{ number_format($data['monthly_disbursed'] ?? 0) }}</span>
                        </div>
                        <div>
                            <span class="text-xs text-gray-400">Month collected:</span>
                            <span class="text-xs font-medium ml-1">{{ number_format($data['monthly_collections'] ?? 0) }}</span>
                        </div>
                    </div>

                    @if (($data['failed_jobs'] ?? 0) > 0)
                        <div class="mt-2 text-xs text-red-500">
                            {{ $data['failed_jobs'] }} failed job(s)
                        </div>
                    @endif
                </x-filament::card>
            @endforeach

            @if (empty($overview))
                <x-filament::card>
                    <div class="text-center py-8 text-gray-500">
                        <div class="text-sm">No tenant data loaded.</div>
                        <x-filament::button wire:click="refreshAll" size="sm" class="mt-2">Load Data</x-filament::button>
                    </div>
                </x-filament::card>
            @endif
        </div>

        {{-- ========== Right: Operations Panel ========== --}}
        <div class="space-y-4">
            {{-- Quick Actions --}}
            <x-filament::card>
                <h3 class="text-base font-semibold mb-3">Operations</h3>
                <div class="space-y-2">
                    <button wire:click="runCheck('metrics')"
                        class="w-full text-left text-sm px-3 py-2 rounded-lg {{ $activeTab === 'metrics' ? 'bg-primary-50 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300' : 'bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700' }} transition">
                        Financial Metrics (all tenants)
                    </button>
                    <button wire:click="runCheck('arrears')"
                        class="w-full text-left text-sm px-3 py-2 rounded-lg {{ $activeTab === 'arrears' ? 'bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300' : 'bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700' }} transition">
                        Arrears Overview
                    </button>
                    <button wire:click="runCheck('queue_health')"
                        class="w-full text-left text-sm px-3 py-2 rounded-lg {{ $activeTab === 'queue_health' ? 'bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300' : 'bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700' }} transition">
                        Queue Worker Health
                    </button>
                    <button wire:click="runCheck('scheduler_check')"
                        class="w-full text-left text-sm px-3 py-2 rounded-lg {{ $activeTab === 'scheduler_check' ? 'bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-300' : 'bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700' }} transition">
                        Scheduler Status
                    </button>
                    <button wire:click="runCheck('failed_jobs')"
                        class="w-full text-left text-sm px-3 py-2 rounded-lg {{ $activeTab === 'failed_jobs' ? 'bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300' : 'bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700' }} transition">
                        Failed Jobs
                    </button>
                    <button wire:click="runCheck('sms_credits')"
                        class="w-full text-left text-sm px-3 py-2 rounded-lg {{ $activeTab === 'sms_credits' ? 'bg-purple-50 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300' : 'bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700' }} transition">
                        SMS Credits
                    </button>
                    <button wire:click="runCheck('risk_score')"
                        class="w-full text-left text-sm px-3 py-2 rounded-lg {{ $activeTab === 'risk_score' ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300' : 'bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700' }} transition">
                        Portfolio Risk Scoring
                    </button>
                    <button wire:click="runCheck('escalate_arrears')"
                        class="w-full text-left text-sm px-3 py-2 rounded-lg {{ $activeTab === 'escalate_arrears' ? 'bg-orange-50 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300' : 'bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700' }} transition">
                        Escalate Arrears
                    </button>
                    <button wire:click="runCheck('daily_summary')"
                        class="w-full text-left text-sm px-3 py-2 rounded-lg {{ $activeTab === 'daily_summary' ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300' : 'bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700' }} transition">
                        Generate Daily Summary
                    </button>
                </div>
            </x-filament::card>

            {{-- Detail Output --}}
            @if ($detailOutput)
                <x-filament::card>
                    <h3 class="text-sm font-semibold mb-2 capitalize">{{ str_replace('_', ' ', $activeTab) }}</h3>
                    <pre class="text-xs overflow-auto max-h-[30rem] bg-gray-950 text-green-200 p-4 rounded whitespace-pre-wrap font-mono leading-relaxed">{{ $detailOutput }}</pre>
                </x-filament::card>
            @endif
        </div>
    </div>
</x-filament-panels::page>

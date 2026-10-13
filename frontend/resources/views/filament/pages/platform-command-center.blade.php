<x-filament-panels::page>
    {{-- Header --}}
    <x-filament::card>
        <div class="flex items-center justify-between">
            <div>
                <h2 class="text-lg font-semibold">Sanaa Platform — Command Center</h2>
                <div class="text-sm text-gray-500">
                    Full-stack monitoring for {{ $this->getTotalSites() }} web applications.
                    @if ($this->hasAlerts())
                        <span class="text-red-500 font-medium">{{ $this->getAlertCount() }} alert(s)</span>
                    @else
                        <span class="text-green-500">All systems healthy</span>
                    @endif
                </div>
            </div>
            <div class="flex gap-2">
                <x-filament::button wire:click="refreshAll" size="sm" color="gray">Refresh</x-filament::button>
            </div>
        </div>
    </x-filament::card>

    {{-- KPI Cards --}}
    <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mt-6">
        <x-filament::card>
            <div class="text-xs text-gray-500 uppercase tracking-wide">Active Sites</div>
            <div class="text-2xl font-bold mt-1">{{ $this->getTotalSites() }}</div>
        </x-filament::card>
        <x-filament::card>
            <div class="text-xs text-gray-500 uppercase tracking-wide">Docker Containers</div>
            <div class="text-2xl font-bold mt-1">{{ $this->getDockerCount() }}</div>
        </x-filament::card>
        <x-filament::card>
            <div class="text-xs text-gray-500 uppercase tracking-wide">Databases</div>
            <div class="text-2xl font-bold mt-1">
                @php
                    $dbs = $this->getDatabases();
                    $upCount = collect($dbs)->filter(fn($v) => $v === 'UP')->count();
                @endphp
                {{ $upCount }} / {{ count($dbs) }}
            </div>
        </x-filament::card>
        <x-filament::card>
            <div class="text-xs text-gray-500 uppercase tracking-wide">Alerts</div>
            <div class="text-2xl font-bold mt-1 {{ $this->getAlertCount() > 0 ? 'text-red-500' : 'text-green-500' }}">
                {{ $this->getAlertCount() }}
            </div>
        </x-filament::card>
    </div>

    {{-- Alerts Banner --}}
    @if ($this->hasAlerts())
        <div class="mt-4 p-3 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800">
            <div class="text-sm font-medium text-red-800 dark:text-red-200 mb-1">Platform Alerts</div>
            @foreach ($alerts as $alert)
                <div class="text-xs text-red-700 dark:text-red-300 flex items-center gap-2">
                    <span>{{ $alert }}</span>
                    @if (str_contains($alert, 'SSL'))
                        <button wire:click="renewSSL('{{ trim(explode(':', $alert)[1] ?? 'all') }}')"
                            class="text-xs px-2 py-0.5 rounded bg-red-100 text-red-800 hover:bg-red-200 dark:bg-red-800 dark:text-red-200 transition">
                            Renew
                        </button>
                    @endif
                </div>
            @endforeach
        </div>
    @endif

    {{-- Database Status Bar --}}
    <div class="mt-4 flex gap-3 flex-wrap">
        @foreach ($this->getDatabases() as $dbName => $status)
            <div class="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium
                {{ $status === 'UP' ? 'bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-300' : 'bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300' }}">
                <span class="inline-flex h-2 w-2 rounded-full {{ $status === 'UP' ? 'bg-green-500' : 'bg-red-500' }}"></span>
                {{ $dbName }}
            </div>
        @endforeach
    </div>

    <div class="grid gap-6 lg:grid-cols-3 mt-6">
        {{-- ========== Left: Monitoring Panels ========== --}}
        <div class="lg:col-span-2 space-y-4">
            {{-- App Type Breakdown --}}
            @if (!empty($this->getAppTypes()))
                <x-filament::card>
                    <h3 class="text-sm font-semibold mb-3">Application Types</h3>
                    <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
                        @foreach ($this->getAppTypes() as $type => $count)
                            <div class="text-center p-3 rounded-lg bg-gray-50 dark:bg-gray-800">
                                <div class="text-lg font-bold">{{ $count }}</div>
                                <div class="text-xs text-gray-500 capitalize">{{ str_replace('-', ' ', $type) }}</div>
                            </div>
                        @endforeach
                    </div>
                </x-filament::card>
            @endif

            {{-- Detail Output --}}
            @if ($detailOutput)
                <x-filament::card>
                    <div class="flex items-center justify-between mb-2">
                        <h3 class="text-sm font-semibold capitalize">{{ str_replace('_', ' ', $activePanel) }}</h3>
                        <button wire:click="$set('detailOutput', '')"
                            class="text-xs text-gray-400 hover:text-gray-600">Clear</button>
                    </div>
                    <pre class="text-xs overflow-auto max-h-[40rem] bg-gray-950 text-green-200 p-4 rounded whitespace-pre-wrap font-mono leading-relaxed">{{ $detailOutput }}</pre>
                </x-filament::card>
            @endif
        </div>

        {{-- ========== Right: Operations Panel ========== --}}
        <div class="space-y-4">
            {{-- Monitoring Actions --}}
            <x-filament::card>
                <h3 class="text-base font-semibold mb-3">Monitoring</h3>
                <div class="space-y-2">
                    @php
                        $monitors = [
                            ['action' => 'overview', 'label' => 'Server Overview', 'color' => 'primary'],
                            ['action' => 'apps', 'label' => 'All Applications', 'color' => 'blue'],
                            ['action' => 'databases', 'label' => 'Database Details', 'color' => 'purple'],
                            ['action' => 'docker', 'label' => 'Docker Containers', 'color' => 'cyan'],
                            ['action' => 'services', 'label' => 'All Services', 'color' => 'green'],
                            ['action' => 'ssl', 'label' => 'SSL Certificates', 'color' => 'amber'],
                            ['action' => 'resources', 'label' => 'System Resources', 'color' => 'red'],
                            ['action' => 'nginx', 'label' => 'Nginx Status', 'color' => 'gray'],
                        ];
                    @endphp

                    @foreach ($monitors as $m)
                        <button wire:click="runMonitor('{{ $m['action'] }}')"
                            class="w-full text-left text-sm px-3 py-2 rounded-lg transition
                            {{ $activePanel === $m['action']
                                ? 'bg-' . $m['color'] . '-50 text-' . $m['color'] . '-700 dark:bg-' . $m['color'] . '-900/30 dark:text-' . $m['color'] . '-300'
                                : 'bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700' }}">
                            {{ $m['label'] }}
                        </button>
                    @endforeach
                </div>
            </x-filament::card>

            {{-- Quick Service Actions --}}
            <x-filament::card>
                <h3 class="text-base font-semibold mb-3">Quick Actions</h3>
                <div class="space-y-2">
                    <button wire:click="manageService('restart', 'nginx', 'systemd')"
                        class="w-full text-left text-sm px-3 py-2 rounded-lg bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700 transition">
                        Restart Nginx
                    </button>
                    <button wire:click="manageService('restart', 'php8.4-fpm', 'systemd')"
                        class="w-full text-left text-sm px-3 py-2 rounded-lg bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700 transition">
                        Restart PHP-FPM
                    </button>
                    <button wire:click="manageService('restart', 'mysql', 'systemd')"
                        class="w-full text-left text-sm px-3 py-2 rounded-lg bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700 transition">
                        Restart MySQL
                    </button>
                    <button wire:click="manageService('restart', 'redis-server', 'systemd')"
                        class="w-full text-left text-sm px-3 py-2 rounded-lg bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700 transition">
                        Restart Redis
                    </button>
                    <button wire:click="renewSSL('all')"
                        class="w-full text-left text-sm px-3 py-2 rounded-lg bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300 hover:bg-amber-100 transition">
                        Renew All SSL Certs
                    </button>
                    <button wire:click="manageService('reload_nginx', 'nginx', 'systemd')"
                        class="w-full text-left text-sm px-3 py-2 rounded-lg bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700 transition">
                        Reload Nginx Config
                    </button>
                </div>
            </x-filament::card>

            {{-- Log Viewer --}}
            <x-filament::card>
                <h3 class="text-base font-semibold mb-3">Logs</h3>
                <div class="space-y-2">
                    @foreach (['nginx', 'mysql', 'antigravity', 'syslog'] as $logSource)
                        <button wire:click="runMonitor('logs', '{{ $logSource }}')"
                            class="w-full text-left text-sm px-3 py-2 rounded-lg bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700 transition">
                            {{ ucfirst($logSource) }} Logs
                        </button>
                    @endforeach
                </div>
            </x-filament::card>
        </div>
    </div>

    {{-- Loading Overlay --}}
    <div wire:loading class="fixed inset-0 bg-black/20 z-50 flex items-center justify-center">
        <div class="bg-white dark:bg-gray-800 rounded-lg px-6 py-4 shadow-xl flex items-center gap-3">
            <svg class="animate-spin h-5 w-5 text-primary-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            <span class="text-sm">Processing...</span>
        </div>
    </div>
</x-filament-panels::page>

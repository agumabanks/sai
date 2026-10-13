<x-filament-panels::page>
    <x-filament::card>
        <div class="flex items-center justify-between">
            <div>
                <h2 class="text-lg font-semibold">Mailcow Email Infrastructure</h2>
                <div class="text-sm text-gray-500">
                    Monitoring postal stack containers, queue depths, and vmail storage limits.
                </div>
            </div>
            <x-filament::button wire:click="refreshAll" size="sm" color="gray">Refresh Check</x-filament::button>
        </div>
    </x-filament::card>

    <div class="grid gap-6 lg:grid-cols-3 mt-6">
        <div class="space-y-4">
            <x-filament::card>
                <h3 class="text-base font-semibold mb-3">Agent Actions</h3>
                <div class="space-y-2">
                    <button wire:click="runCheck('container_health')"
                        class="w-full text-left text-sm px-3 py-2 rounded-lg {{ $activeTab === 'container_health' ? 'bg-primary-50 text-primary-700' : 'bg-gray-50 hover:bg-gray-100 dark:bg-gray-800 dark:hover:bg-gray-700' }} transition">
                        Check Container Health
                    </button>
                    <button wire:click="runCheck('queue_depth')"
                        class="w-full text-left text-sm px-3 py-2 rounded-lg {{ $activeTab === 'queue_depth' ? 'bg-amber-50 text-amber-700' : 'bg-gray-50 hover:bg-gray-100 dark:bg-gray-800 dark:hover:bg-gray-700' }} transition">
                        View Mail Queue Depth
                    </button>
                    <button wire:click="runCheck('check_storage')"
                        class="w-full text-left text-sm px-3 py-2 rounded-lg {{ $activeTab === 'check_storage' ? 'bg-green-50 text-green-700' : 'bg-gray-50 hover:bg-gray-100 dark:bg-gray-800 dark:hover:bg-gray-700' }} transition">
                        Check vmail Storage
                    </button>
                </div>
            </x-filament::card>
        </div>

        <div class="lg:col-span-2 space-y-4">
            @if ($detailOutput)
                <x-filament::card>
                    <h3 class="text-sm font-semibold mb-2 capitalize">{{ str_replace('_', ' ', $activeTab) }} Output</h3>
                    <pre class="text-xs overflow-auto max-h-[40rem] bg-gray-950 text-green-200 p-4 rounded whitespace-pre-wrap font-mono leading-relaxed">{{ $detailOutput }}</pre>
                </x-filament::card>
            @else
                <x-filament::loading-section />
            @endif
        </div>
    </div>
</x-filament-panels::page>

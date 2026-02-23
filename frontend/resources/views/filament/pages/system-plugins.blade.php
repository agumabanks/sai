<x-filament-panels::page>
    <div class="space-y-6">
        <div class="flex items-center justify-between">
            <p class="text-sm text-gray-500 dark:text-gray-400">
                Check for outdated Composer (PHP) and NPM (Node.js) packages.
            </p>
            <x-filament::button wire:click="scanNow" color="primary" icon="heroicon-m-arrow-path">
                <span wire:loading.remove wire:target="scanNow">Scan for Updates</span>
                <span wire:loading wire:target="scanNow">Scanning...</span>
            </x-filament::button>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <!-- Composer -->
            <x-filament::card>
                <div class="flex items-center gap-2 mb-4">
                    <x-filament::icon icon="heroicon-o-server" class="w-5 h-5 text-indigo-500" />
                    <h3 class="text-lg font-medium">Composer Packages</h3>
                </div>
                <div class="bg-gray-900 rounded-lg p-4 overflow-x-auto">
                    <pre class="text-xs text-green-400 whitespace-pre-wrap font-mono">{{ $composerOutput }}</pre>
                </div>
            </x-filament::card>

            <!-- NPM -->
            <x-filament::card>
                <div class="flex items-center gap-2 mb-4">
                    <x-filament::icon icon="heroicon-o-window" class="w-5 h-5 text-yellow-500" />
                    <h3 class="text-lg font-medium">NPM Packages</h3>
                </div>
                <div class="bg-gray-900 rounded-lg p-4 overflow-x-auto">
                    <pre class="text-xs text-green-400 whitespace-pre-wrap font-mono">{{ $npmOutput }}</pre>
                </div>
            </x-filament::card>
        </div>
    </div>
</x-filament-panels::page>

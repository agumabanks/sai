<x-filament-panels::page>
    <div class="space-y-6">
        <x-filament::card>
            <form wire:submit="submit">
                {{ $this->form }}

                <div class="mt-6 flex gap-4">
                    <x-filament::button type="submit">
                        Save Preferences
                    </x-filament::button>
                </div>
            </form>
        </x-filament::card>
        
        <x-filament::card>
            <h3 class="text-lg font-medium leading-6 dark:text-gray-200">Manual Generation</h3>
            <p class="mt-2 text-sm text-gray-500 dark:text-gray-400">
                Trigger intelligence agents to immediately aggregate RSS feeds, synthesize reports, and dispatch the newsletter directly to your alert email.
            </p>
            <div class="mt-4">
                <x-filament::button wire:click="generateNow" color="warning" icon="heroicon-m-bolt">
                    Generate Briefing Now
                </x-filament::button>
            </div>
        </x-filament::card>
    </div>
</x-filament-panels::page>

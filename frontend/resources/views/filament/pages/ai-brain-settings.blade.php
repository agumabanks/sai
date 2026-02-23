<x-filament-panels::page>
    <x-filament::card>
        <form wire:submit="submit">
            {{ $this->form }}

            <div class="mt-6">
                <x-filament::button type="submit">
                    Save Brain Settings
                </x-filament::button>
            </div>
        </form>
    </x-filament::card>
</x-filament-panels::page>

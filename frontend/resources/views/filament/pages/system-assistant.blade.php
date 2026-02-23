<x-filament-panels::page>
    <x-filament::card>
        <form wire:submit="submit">
            {{ $this->form }}

            <div class="mt-6">
                <x-filament::button type="submit" color="primary">
                    Save Assistant Configuration
                </x-filament::button>
            </div>
        </form>
    </x-filament::card>
</x-filament-panels::page>

<x-filament-panels::page>
    <x-filament::card>
        <form wire:submit="submit">
            {{ $this->form }}
            <div class="mt-6">
                <x-filament::button type="submit">
                    Save Tool Policy
                </x-filament::button>
            </div>
        </form>
    </x-filament::card>

    <x-filament::card class="mt-6">
        <div class="flex items-center justify-between">
            <h2 class="text-lg font-semibold">Skills & Exposure</h2>
            <x-filament::button size="sm" color="gray" wire:click="refreshData">Refresh</x-filament::button>
        </div>

        <div class="mt-4 overflow-x-auto">
            <table class="w-full text-sm">
                <thead>
                    <tr class="border-b">
                        <th class="text-left py-2">Skill</th>
                        <th class="text-left py-2">Safety</th>
                        <th class="text-left py-2">Groups</th>
                        <th class="text-left py-2">Enabled</th>
                        <th class="text-left py-2">Exposure</th>
                        <th class="text-left py-2">Brain</th>
                        <th class="text-left py-2">Actions</th>
                    </tr>
                </thead>
                <tbody>
                    @forelse ($skills as $skill)
                        <tr class="border-b align-top">
                            <td class="py-2">
                                <div class="font-medium">{{ $skill['name'] ?? '-' }}</div>
                                <div class="text-xs text-gray-500">{{ $skill['description'] ?? '' }}</div>
                            </td>
                            <td class="py-2">{{ $skill['safety_tier'] ?? '-' }}</td>
                            <td class="py-2">{{ implode(', ', $skill['groups'] ?? []) }}</td>
                            <td class="py-2">{{ !empty($skill['enabled']) ? 'Yes' : 'No' }}</td>
                            <td class="py-2">{{ $skill['exposure'] ?? 'auto' }}</td>
                            <td class="py-2">
                                @if (!empty($skill['exposed_to_brain']))
                                    <span class="text-green-600">Allowed</span>
                                @else
                                    <span class="text-red-600">Blocked</span>
                                    @if (!empty($skill['brain_denied_reason']))
                                        <div class="text-xs text-gray-500">{{ $skill['brain_denied_reason'] }}</div>
                                    @endif
                                @endif
                            </td>
                            <td class="py-2">
                                <div class="flex flex-wrap gap-2">
                                    <x-filament::button size="xs" color="gray" wire:click="toggleSkill('{{ $skill['name'] }}', true)">Enable</x-filament::button>
                                    <x-filament::button size="xs" color="danger" wire:click="toggleSkill('{{ $skill['name'] }}', false)">Disable</x-filament::button>
                                    <x-filament::button size="xs" color="gray" wire:click="changeExposure('{{ $skill['name'] }}', 'auto')">Auto</x-filament::button>
                                    <x-filament::button size="xs" color="warning" wire:click="changeExposure('{{ $skill['name'] }}', 'manual_only')">Manual</x-filament::button>
                                    <x-filament::button size="xs" color="danger" wire:click="changeExposure('{{ $skill['name'] }}', 'hidden')">Hide</x-filament::button>
                                </div>
                            </td>
                        </tr>
                    @empty
                        <tr><td colspan="7" class="py-4 text-gray-500">No skills found.</td></tr>
                    @endforelse
                </tbody>
            </table>
        </div>
    </x-filament::card>
</x-filament-panels::page>

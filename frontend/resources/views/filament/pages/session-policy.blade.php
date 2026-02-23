<x-filament-panels::page>
    <x-filament::card>
        <form wire:submit="submit">
            {{ $this->form }}
            <div class="mt-6 flex gap-2">
                <x-filament::button type="submit">Save Session Policy</x-filament::button>
                <x-filament::button type="button" color="gray" wire:click="refreshData">Refresh</x-filament::button>
            </div>
        </form>
    </x-filament::card>

    <x-filament::card class="mt-6">
        <div class="flex items-center justify-between">
            <h2 class="text-lg font-semibold">Recent Sessions</h2>
            <x-filament::button size="sm" color="gray" wire:click="refreshData">Reload</x-filament::button>
        </div>
        <div class="mt-4 overflow-x-auto">
            <table class="w-full text-sm">
                <thead>
                    <tr class="border-b">
                        <th class="text-left py-2">Session</th>
                        <th class="text-left py-2">Channel</th>
                        <th class="text-left py-2">Sender</th>
                        <th class="text-left py-2">Last Seen</th>
                        <th class="text-left py-2">Send Override</th>
                        <th class="text-left py-2">Actions</th>
                    </tr>
                </thead>
                <tbody>
                    @forelse ($sessions as $session)
                        <tr class="border-b align-top">
                            <td class="py-2 text-xs">{{ $session['session_id'] ?? '-' }}</td>
                            <td class="py-2">{{ $session['channel'] ?? '-' }}</td>
                            <td class="py-2">{{ $session['sender_name'] ?? ($session['sender_id'] ?? '-') }}</td>
                            <td class="py-2">{{ $session['last_seen'] ?? '-' }}</td>
                            <td class="py-2">{{ $session['send_override'] ?? 'inherit' }}</td>
                            <td class="py-2">
                                <div class="flex flex-wrap gap-2">
                                    <x-filament::button size="xs" color="gray" wire:click="inspectSession('{{ $session['session_id'] }}')">Inspect</x-filament::button>
                                    <x-filament::button size="xs" color="warning" wire:click="resetSessionAction('{{ $session['session_id'] }}')">Reset</x-filament::button>
                                    <x-filament::button size="xs" color="success" wire:click="setSendOverride('{{ $session['session_id'] }}', 'on')">Send On</x-filament::button>
                                    <x-filament::button size="xs" color="danger" wire:click="setSendOverride('{{ $session['session_id'] }}', 'off')">Send Off</x-filament::button>
                                    <x-filament::button size="xs" color="gray" wire:click="setSendOverride('{{ $session['session_id'] }}', 'inherit')">Inherit</x-filament::button>
                                </div>
                            </td>
                        </tr>
                    @empty
                        <tr><td colspan="6" class="py-4 text-gray-500">No sessions found.</td></tr>
                    @endforelse
                </tbody>
            </table>
        </div>
    </x-filament::card>

    <x-filament::card class="mt-6">
        <h2 class="text-lg font-semibold">Session Detail</h2>
        @if ($selectedSession)
            <pre class="mt-4 text-xs overflow-auto max-h-[28rem] bg-gray-950 text-green-200 p-4 rounded">{{ json_encode($selectedSession, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) }}</pre>
        @else
            <div class="mt-3 text-sm text-gray-500">Select a session to inspect recent messages.</div>
        @endif
    </x-filament::card>
</x-filament-panels::page>


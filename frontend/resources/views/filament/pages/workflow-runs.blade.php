<x-filament-panels::page>
    <div class="grid gap-6 lg:grid-cols-2">
        <x-filament::card>
            <div class="flex items-center justify-between">
                <h2 class="text-lg font-semibold">Workflow Definitions</h2>
                <x-filament::button size="sm" color="gray" wire:click="refreshData">Refresh</x-filament::button>
            </div>
            <div class="mt-4 space-y-3">
                @forelse ($workflows as $wf)
                    <div class="border rounded-lg p-3">
                        <div class="flex items-center justify-between">
                            <div>
                                <div class="font-medium">{{ $wf['name'] ?? '-' }}</div>
                                <div class="text-xs text-gray-500">{{ $wf['description'] ?? '' }}</div>
                            </div>
                            <x-filament::button size="xs" wire:click="startWorkflow('{{ $wf['name'] }}')">Run</x-filament::button>
                        </div>
                        <div class="mt-2 text-xs text-gray-500">
                            Steps: {{ $wf['step_count'] ?? 0 }}
                        </div>
                    </div>
                @empty
                    <div class="text-sm text-gray-500">No workflows discovered.</div>
                @endforelse
            </div>
        </x-filament::card>

        <x-filament::card>
            <div class="flex items-center justify-between">
                <h2 class="text-lg font-semibold">Recent Workflow Runs</h2>
                <x-filament::button size="sm" color="gray" wire:click="refreshData">Refresh</x-filament::button>
            </div>
            <div class="mt-4 overflow-x-auto">
                <table class="w-full text-sm">
                    <thead>
                        <tr class="border-b">
                            <th class="text-left py-2">Run</th>
                            <th class="text-left py-2">Workflow</th>
                            <th class="text-left py-2">Status</th>
                            <th class="text-left py-2">Started</th>
                            <th class="text-left py-2">Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        @forelse ($runs as $run)
                            <tr class="border-b align-top">
                                <td class="py-2">#{{ $run['id'] ?? '-' }}</td>
                                <td class="py-2">{{ $run['workflow_name'] ?? '-' }}</td>
                                <td class="py-2">{{ $run['status'] ?? '-' }}</td>
                                <td class="py-2">{{ $run['started_at'] ?? '-' }}</td>
                                <td class="py-2">
                                    <div class="flex flex-wrap gap-2">
                                        <x-filament::button size="xs" color="gray" wire:click="viewRun({{ (int) ($run['id'] ?? 0) }})">View</x-filament::button>
                                        @if (($run['status'] ?? '') === 'paused')
                                            <x-filament::button size="xs" color="success" wire:click="approveRun({{ (int) ($run['id'] ?? 0) }})">Approve</x-filament::button>
                                            <x-filament::button size="xs" color="warning" wire:click="denyRun({{ (int) ($run['id'] ?? 0) }})">Deny</x-filament::button>
                                        @endif
                                        @if (in_array(($run['status'] ?? ''), ['running', 'paused']))
                                            <x-filament::button size="xs" color="danger" wire:click="cancelRun({{ (int) ($run['id'] ?? 0) }})">Cancel</x-filament::button>
                                        @endif
                                    </div>
                                </td>
                            </tr>
                        @empty
                            <tr><td colspan="5" class="py-4 text-gray-500">No workflow runs yet.</td></tr>
                        @endforelse
                    </tbody>
                </table>
            </div>
        </x-filament::card>
    </div>

    <x-filament::card class="mt-6">
        <h2 class="text-lg font-semibold">Selected Run Details</h2>
        @if ($selectedRun)
            @if (!empty($selectedApproval['approval']))
                <div class="mt-4 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm">
                    <div class="font-medium text-amber-800">Approval Required</div>
                    <div class="mt-1 text-amber-700">{{ $selectedApproval['approval']['prompt'] ?? 'No prompt' }}</div>
                </div>
            @endif
            <pre class="mt-4 text-xs overflow-auto max-h-[28rem] bg-gray-950 text-green-200 p-4 rounded">{{ json_encode($selectedRun, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) }}</pre>
        @else
            <div class="mt-3 text-sm text-gray-500">Select a run to inspect step outputs and approval state.</div>
        @endif
    </x-filament::card>
</x-filament-panels::page>


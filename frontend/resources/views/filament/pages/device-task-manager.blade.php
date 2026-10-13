<x-filament-panels::page>
    <div class="space-y-6">
        {{-- New Task Form --}}
        @if($showForm)
            <div class="rounded-2xl bg-white/5 dark:bg-[#1c1c1e]/60 backdrop-blur-3xl border border-black/5 dark:border-white/5 p-6">
                <h3 class="text-lg font-semibold text-white mb-4">Create New Task</h3>

                <div class="space-y-4">
                    {{-- Device Selection --}}
                    <div>
                        <label class="block text-sm text-zinc-400 mb-1">Target Device</label>
                        <select wire:model="selectedDeviceId"
                                class="w-full rounded-lg bg-[#1c1c1e] border border-white/10 text-white p-2.5 text-sm">
                            <option value="">Select a device...</option>
                            @foreach($devices as $device)
                                <option value="{{ $device['device_id'] }}">
                                    {{ $device['display_name'] ?? 'Unnamed' }}
                                    ({{ $device['status'] ?? '?' }})
                                    — {{ $device['worker_role'] ?? 'worker' }}
                                </option>
                            @endforeach
                        </select>
                    </div>

                    {{-- Task Type --}}
                    <div>
                        <label class="block text-sm text-zinc-400 mb-1">Task Type</label>
                        <select wire:model="taskType"
                                class="w-full rounded-lg bg-[#1c1c1e] border border-white/10 text-white p-2.5 text-sm">
                            <option value="">Select task type...</option>
                            <option value="api_call">API Call</option>
                            <option value="screenshot">Screenshot</option>
                            <option value="scrape">Web Scrape</option>
                            <option value="upload">File Upload</option>
                            <option value="test">Connectivity Test</option>
                            <option value="ping">Ping</option>
                            <option value="sleep">Sleep/Delay</option>
                        </select>
                    </div>

                    {{-- Priority --}}
                    <div>
                        <label class="block text-sm text-zinc-400 mb-1">Priority</label>
                        <select wire:model="taskPriority"
                                class="w-full rounded-lg bg-[#1c1c1e] border border-white/10 text-white p-2.5 text-sm">
                            <option value="0">Normal (0)</option>
                            <option value="1">High (1)</option>
                            <option value="2">Critical (2)</option>
                        </select>
                    </div>

                    {{-- Payload --}}
                    <div>
                        <label class="block text-sm text-zinc-400 mb-1">Payload (JSON)</label>
                        <textarea wire:model="taskPayload" rows="5"
                                  placeholder='{"url": "https://example.com", "method": "GET"}'
                                  class="w-full rounded-lg bg-[#1c1c1e] border border-white/10 text-white p-2.5 text-sm font-mono"></textarea>
                    </div>

                    {{-- Actions --}}
                    <div class="flex gap-3">
                        <x-filament::button wire:click="createTask" color="success">
                            Create Task
                        </x-filament::button>
                        <x-filament::button wire:click="$set('showForm', false)" color="gray">
                            Cancel
                        </x-filament::button>
                    </div>

                    @if($lastResult)
                        <div class="p-3 rounded-lg bg-green-900/30 border border-green-700 text-sm text-green-300">
                            {{ $lastResult }}
                        </div>
                    @endif
                </div>
            </div>
        @endif

        {{-- Device Task Queues --}}
        @foreach($devices as $device)
            <div class="rounded-2xl bg-white/5 dark:bg-[#1c1c1e]/60 backdrop-blur-3xl border border-black/5 dark:border-white/5 overflow-hidden">
                <div class="p-4 border-b border-black/5 dark:border-white/5 flex items-center gap-3">
                    <x-filament::icon
                        :icon="match($device['status'] ?? '') {
                            'online' => 'heroicon-m-check-circle',
                            'idle' => 'heroicon-m-clock',
                            'busy' => 'heroicon-m-play-circle',
                            default => 'heroicon-m-x-circle'
                        }"
                        :class="'h-4 w-4 text-' . match($device['status'] ?? '') {
                            'online' => 'green',
                            'idle' => 'yellow',
                            'busy' => 'blue',
                            default => 'gray'
                        } . '-400'"
                    />
                    <span class="text-white font-medium">{{ $device['display_name'] ?? 'Unnamed' }}</span>
                    <span class="text-xs text-zinc-500">{{ $device['device_id'] }}</span>
                    <span class="text-xs text-zinc-500 capitalize">{{ $device['worker_role'] ?? 'worker' }}</span>
                    <span class="text-xs text-zinc-500">{{ $device['total_tasks_completed'] ?? 0 }} completed</span>
                </div>
                <div class="p-4 text-sm text-zinc-500">
                    <div class="flex gap-3">
                        <span>Status: <span class="text-white capitalize">{{ $device['status'] ?? 'offline' }}</span></span>
                        @if($device['last_heartbeat'])
                            <span>• Last: {{ \Carbon\Carbon::parse($device['last_heartbeat'])->diffForHumans() }}</span>
                        @endif
                        <span class="ml-auto">
                            <x-filament::button
                                wire:click="$set('selectedDeviceId', '{{ $device['device_id'] }}'); $set('showForm', true)"
                                color="primary"
                                size="xs">
                                Assign Task
                            </x-filament::button>
                        </span>
                    </div>
                </div>
            </div>
        @endforeach
    </div>
</x-filament-panels::page>

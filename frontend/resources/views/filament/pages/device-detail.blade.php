<x-filament-panels::page>
    <div class="space-y-6">
        @if($loading)
            <div class="p-8 text-center">
                <x-filament::loading-indicator class="h-8 w-8 mx-auto text-primary-500" />
                <p class="mt-3 text-sm text-zinc-400">Loading device data...</p>
            </div>
        @else
            {{-- Device Header --}}
            <div class="rounded-2xl bg-white/5 dark:bg-[#1c1c1e]/60 backdrop-blur-3xl border border-black/5 dark:border-white/5 p-6">
                <div class="flex items-center gap-4 mb-4">
                    <div class="flex-shrink-0">
                        <x-filament::icon
                            :icon="match($deviceData['status'] ?? '') {
                                'online' => 'heroicon-o-check-circle',
                                'idle' => 'heroicon-o-clock',
                                'busy' => 'heroicon-o-play-circle',
                                'error' => 'heroicon-o-exclamation-triangle',
                                default => 'heroicon-o-x-circle'
                            }"
                            :class="'h-10 w-10 text-' . $this->getStatusColor($deviceData['status'] ?? 'offline') . '-400'"
                        />
                    </div>
                    <div>
                        <h2 class="text-2xl font-bold text-white">{{ $deviceData['display_name'] ?? 'Unknown Device' }}</h2>
                        <div class="flex items-center gap-3 mt-1 text-sm text-zinc-400">
                            <span>{{ $deviceData['device_id'] }}</span>
                            <span>•</span>
                            <span class="capitalize">{{ $deviceData['worker_role'] ?? 'worker' }}</span>
                            @if($deviceData['codename'])
                                <span>•</span>
                                <span>{{ $deviceData['codename'] }}</span>
                            @endif
                        </div>
                    </div>
                    <div class="ml-auto">
                        <x-filament::badge :color="$this->getStatusColor($deviceData['status'] ?? 'offline')" size="lg">
                            {{ strtoupper($deviceData['status'] ?? 'OFFLINE') }}
                        </x-filament::badge>
                    </div>
                </div>

                {{-- Specs Grid --}}
                <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6">
                    <div class="p-3 rounded-xl bg-black/20">
                        <p class="text-xs text-zinc-500">Model</p>
                        <p class="text-sm text-white font-medium">{{ $deviceData['device_model'] ?? 'N/A' }}</p>
                    </div>
                    <div class="p-3 rounded-xl bg-black/20">
                        <p class="text-xs text-zinc-500">Android</p>
                        <p class="text-sm text-white font-medium">{{ $deviceData['android_version'] ?? 'N/A' }}</p>
                    </div>
                    <div class="p-3 rounded-xl bg-black/20">
                        <p class="text-xs text-zinc-500">RAM</p>
                        <p class="text-sm text-white font-medium">{{ $deviceData['ram_mb'] ? number_format($deviceData['ram_mb']) . ' MB' : 'N/A' }}</p>
                    </div>
                    <div class="p-3 rounded-xl bg-black/20">
                        <p class="text-xs text-zinc-500">Storage</p>
                        <p class="text-sm text-white font-medium">{{ $deviceData['storage_mb'] ? number_format($deviceData['storage_mb'] / 1024, 1) . ' GB' : 'N/A' }}</p>
                    </div>
                    <div class="p-3 rounded-xl bg-black/20">
                        <p class="text-xs text-zinc-500">Battery</p>
                        <p class="text-sm text-white font-medium">{{ $deviceData['battery_health'] ?? 'N/A' }}</p>
                    </div>
                    <div class="p-3 rounded-xl bg-black/20">
                        <p class="text-xs text-zinc-500">Tasks Completed</p>
                        <p class="text-sm text-white font-medium">{{ number_format($deviceData['total_tasks_completed'] ?? 0) }}</p>
                    </div>
                    <div class="p-3 rounded-xl bg-black/20">
                        <p class="text-xs text-zinc-500">Uptime</p>
                        <p class="text-sm text-white font-medium">{{ $deviceData['total_uptime_seconds'] ? gmdate('H:i:s', $deviceData['total_uptime_seconds']) : 'N/A' }}</p>
                    </div>
                    <div class="p-3 rounded-xl bg-black/20">
                        <p class="text-xs text-zinc-500">App Version</p>
                        <p class="text-sm text-white font-medium">{{ $deviceData['app_version'] ?? 'N/A' }}</p>
                    </div>
                </div>

                @if($deviceData['last_heartbeat'])
                    <p class="mt-4 text-xs text-zinc-500">
                        Last heartbeat: {{ \Carbon\Carbon::parse($deviceData['last_heartbeat'])->diffForHumans() }}
                        @if($deviceData['ip_address'])
                            • IP: {{ $deviceData['ip_address'] }}
                        @endif
                    </p>
                @endif
            </div>

            {{-- Command Center --}}
            <div class="rounded-2xl bg-white/5 dark:bg-[#1c1c1e]/60 backdrop-blur-3xl border border-black/5 dark:border-white/5 p-5">
                <h3 class="text-sm font-semibold text-white mb-4">Remote Command</h3>
                <div class="flex gap-3 items-end">
                    <div class="flex-1">
                        <select wire:model="commandType"
                                class="w-full rounded-lg bg-[#1c1c1e] border border-white/10 text-white text-sm p-2">
                            <option value="">Select command...</option>
                            <option value="restart">Restart Device</option>
                            <option value="update">Update App</option>
                            <option value="screenshot">Take Screenshot</option>
                            <option value="sync">Force Sync</option>
                            <option value="debug">Debug Mode</option>
                            <option value="shutdown">Shutdown</option>
                        </select>
                    </div>
                    <div class="flex-1">
                        <input type="text" wire:model="commandPayload"
                               placeholder="JSON payload (optional)"
                               class="w-full rounded-lg bg-[#1c1c1e] border border-white/10 text-white text-sm p-2" />
                    </div>
                    <x-filament::button wire:click="sendCommand" color="primary">
                        Send Command
                    </x-filament::button>
                </div>
            </div>

            {{-- Recent Tasks --}}
            <div class="rounded-2xl bg-white/5 dark:bg-[#1c1c1e]/60 backdrop-blur-3xl border border-black/5 dark:border-white/5 overflow-hidden">
                <div class="p-5 border-b border-black/5 dark:border-white/5">
                    <h3 class="text-sm font-semibold text-white">Recent Tasks</h3>
                </div>
                @if(empty($recentTasks))
                    <div class="p-5 text-sm text-zinc-500">No tasks yet</div>
                @else
                    <div class="divide-y divide-black/5 dark:divide-white/5">
                        @foreach($recentTasks as $task)
                            <div class="p-4 flex items-center gap-3 text-sm">
                                <x-filament::badge :color="$this->getTaskStatusColor($task['status'] ?? '')" size="sm">
                                    {{ $task['status'] ?? 'unknown' }}
                                </x-filament::badge>
                                <span class="text-white flex-1">{{ $task['task_type'] ?? 'unknown' }}</span>
                                <span class="text-zinc-500">{{ $task['task_id'] }}</span>
                                <span class="text-zinc-500 text-xs">{{ $task['created_at'] ? \Carbon\Carbon::parse($task['created_at'])->diffForHumans() : '' }}</span>
                            </div>
                        @endforeach
                    </div>
                @endif
            </div>

            {{-- Recent Logs --}}
            <div class="rounded-2xl bg-white/5 dark:bg-[#1c1c1e]/60 backdrop-blur-3xl border border-black/5 dark:border-white/5 overflow-hidden">
                <div class="p-5 border-b border-black/5 dark:border-white/5">
                    <h3 class="text-sm font-semibold text-white">Recent Logs</h3>
                </div>
                @if(empty($recentLogs))
                    <div class="p-5 text-sm text-zinc-500">No logs yet</div>
                @else
                    <div class="divide-y divide-black/5 dark:divide-white/5">
                        @foreach($recentLogs as $log)
                            <div class="p-3 flex items-center gap-3 text-xs font-mono">
                                <x-filament::badge :color="$this->getLogSeverityColor($log['severity'] ?? 'info')" size="sm">
                                    {{ $log['severity'] ?? 'info' }}
                                </x-filament::badge>
                                <span class="text-zinc-400">{{ $log['log_type'] ?? '' }}</span>
                                <span class="text-zinc-300 flex-1 truncate">{{ $log['message'] ?? '' }}</span>
                                <span class="text-zinc-500">{{ $log['created_at'] ? \Carbon\Carbon::parse($log['created_at'])->diffForHumans() : '' }}</span>
                            </div>
                        @endforeach
                    </div>
                @endif
            </div>
        @endif
    </div>
</x-filament-panels::page>

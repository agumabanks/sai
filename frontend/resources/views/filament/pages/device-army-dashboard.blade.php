<x-filament-panels::page>
    <div class="space-y-6">
        {{-- Stats Overview --}}
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div class="rounded-2xl bg-white/5 dark:bg-[#1c1c1e]/60 backdrop-blur-3xl border border-black/5 dark:border-white/5 p-5">
                <div class="flex items-center justify-between">
                    <div>
                        <p class="text-sm text-zinc-400">Total Devices</p>
                        <p class="text-3xl font-bold text-white mt-1">{{ $stats['total'] ?? 0 }}</p>
                    </div>
                    <x-filament::icon icon="heroicon-o-cpu-chip" class="h-8 w-8 text-blue-400" />
                </div>
            </div>

            <div class="rounded-2xl bg-white/5 dark:bg-[#1c1c1e]/60 backdrop-blur-3xl border border-black/5 dark:border-white/5 p-5">
                <div class="flex items-center justify-between">
                    <div>
                        <p class="text-sm text-zinc-400">Online</p>
                        <p class="text-3xl font-bold text-green-400 mt-1">{{ $stats['online'] ?? 0 }}</p>
                    </div>
                    <x-filament::icon icon="heroicon-o-wifi" class="h-8 w-8 text-green-400" />
                </div>
            </div>

            <div class="rounded-2xl bg-white/5 dark:bg-[#1c1c1e]/60 backdrop-blur-3xl border border-black/5 dark:border-white/5 p-5">
                <div class="flex items-center justify-between">
                    <div>
                        <p class="text-sm text-zinc-400">Offline</p>
                        <p class="text-3xl font-bold text-gray-400 mt-1">{{ $stats['offline'] ?? 0 }}</p>
                    </div>
                    <x-filament::icon icon="heroicon-o-wifi-off" class="h-8 w-8 text-gray-400" />
                </div>
            </div>

            <div class="rounded-2xl bg-white/5 dark:bg-[#1c1c1e]/60 backdrop-blur-3xl border border-black/5 dark:border-white/5 p-5">
                <div class="flex items-center justify-between">
                    <div>
                        <p class="text-sm text-zinc-400">Roles Active</p>
                        <p class="text-3xl font-bold text-purple-400 mt-1">{{ count($stats['by_role'] ?? []) }}</p>
                    </div>
                    <x-filament::icon icon="heroicon-o-users" class="h-8 w-8 text-purple-400" />
                </div>
            </div>
        </div>

        {{-- Device List --}}
        <div class="rounded-2xl bg-white/5 dark:bg-[#1c1c1e]/60 backdrop-blur-3xl border border-black/5 dark:border-white/5 overflow-hidden">
            <div class="p-5 border-b border-black/5 dark:border-white/5">
                <h2 class="text-lg font-semibold text-white">Device Fleet</h2>
            </div>

            @if($loading)
                <div class="p-8 text-center">
                    <x-filament::loading-indicator class="h-8 w-8 mx-auto text-primary-500" />
                    <p class="mt-3 text-sm text-zinc-400">Scanning the fleet...</p>
                </div>
            @elseif(empty($devices))
                <div class="p-8 text-center">
                    <x-filament::icon icon="heroicon-o-cpu-chip" class="h-12 w-12 mx-auto text-zinc-600" />
                    <p class="mt-3 text-lg font-medium text-zinc-400">No Devices Registered</p>
                    <p class="text-sm text-zinc-500">Install the Sanaa Worker app on an Android device to get started.</p>
                </div>
            @else
                <div class="divide-y divide-black/5 dark:divide-white/5">
                    @foreach($devices as $device)
                        <div class="p-4 hover:bg-white/5 transition-colors flex items-center gap-4">
                            {{-- Status Indicator --}}
                            <div class="flex-shrink-0">
                                <x-filament::icon
                                    :icon="$this->getDeviceStatusIcon($device['status'] ?? 'offline')"
                                    :class="'h-5 w-5 text-' . $this->getDeviceStatusColor($device['status'] ?? 'offline') . '-400'"
                                />
                            </div>

                            {{-- Device Info --}}
                            <div class="flex-1 min-w-0">
                                <div class="flex items-center gap-2">
                                    <span class="font-medium text-white truncate">{{ $device['display_name'] ?? 'Unnamed' }}</span>
                                    <x-filament::badge :color="$this->getDeviceStatusColor($device['status'] ?? 'offline')" size="sm">
                                        {{ $device['status'] ?? 'offline' }}
                                    </x-filament::badge>
                                </div>
                                <div class="flex items-center gap-3 mt-1 text-xs text-zinc-400">
                                    <span class="flex items-center gap-1">
                                        <x-filament::icon :icon="$this->getRoleIcon($device['worker_role'] ?? 'worker')" class="h-3 w-3" />
                                        {{ $device['worker_role'] ?? 'worker' }}
                                    </span>
                                    @if($device['codename'])
                                        <span>{{ $device['codename'] }}</span>
                                    @endif
                                    <span>{{ $device['device_model'] ?? 'Unknown' }}</span>
                                    @if($device['last_heartbeat'])
                                        <span>{{ \Carbon\Carbon::parse($device['last_heartbeat'])->diffForHumans() }}</span>
                                    @endif
                                </div>
                            </div>

                            {{-- Stats --}}
                            <div class="flex items-center gap-4 text-xs text-zinc-400">
                                @if($device['battery_health'])
                                    <span>{{ $device['battery_health'] }}</span>
                                @endif
                                <span>{{ $device['total_tasks_completed'] ?? 0 }} tasks</span>
                            </div>

                            {{-- Action --}}
                            <a href="{{ url("/admin/device-army/devices/{$device['device_id']}") }}"
                               class="flex-shrink-0 px-3 py-1.5 text-xs font-medium text-primary-400 hover:text-primary-300 transition-colors">
                                View →
                            </a>
                        </div>
                    @endforeach
                </div>
            @endif
        </div>

        {{-- Task Distribution --}}
        @if(!empty($stats['by_role']))
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div class="rounded-2xl bg-white/5 dark:bg-[#1c1c1e]/60 backdrop-blur-3xl border border-black/5 dark:border-white/5 p-5">
                    <h3 class="text-sm font-semibold text-white mb-4">Workers by Role</h3>
                    <div class="space-y-3">
                        @foreach($stats['by_role'] as $role => $count)
                            <div class="flex items-center justify-between">
                                <span class="text-sm text-zinc-300 capitalize">{{ $role }}</span>
                                <span class="text-sm font-medium text-white">{{ $count }}</span>
                            </div>
                            <div class="w-full bg-zinc-700 rounded-full h-1.5">
                                <div class="bg-primary-500 h-1.5 rounded-full"
                                     style="width: {{ $stats['total'] > 0 ? ($count / $stats['total']) * 100 : 0 }}%">
                                </div>
                            </div>
                        @endforeach
                    </div>
                </div>

                <div class="rounded-2xl bg-white/5 dark:bg-[#1c1c1e]/60 backdrop-blur-3xl border border-black/5 dark:border-white/5 p-5">
                    <h3 class="text-sm font-semibold text-white mb-4">Task Status</h3>
                    @if(!empty($stats['task_counts']))
                        <div class="space-y-3">
                            @foreach($stats['task_counts'] as $status => $count)
                                <div class="flex items-center justify-between">
                                    <span class="text-sm text-zinc-300 capitalize">{{ $status }}</span>
                                    <span class="text-sm font-medium text-white">{{ $count }}</span>
                                </div>
                                @php
                                    $totalTasks = array_sum($stats['task_counts']);
                                @endphp
                                <div class="w-full bg-zinc-700 rounded-full h-1.5">
                                    <div class="bg-{{ match($status) {
                                        'completed' => 'green',
                                        'failed' => 'red',
                                        'in_progress' => 'blue',
                                        default => 'gray'
                                    } }}-500 h-1.5 rounded-full"
                                         style="width: {{ $totalTasks > 0 ? ($count / $totalTasks) * 100 : 0 }}%">
                                    </div>
                                </div>
                            @endforeach
                        </div>
                    @else
                        <p class="text-sm text-zinc-500">No tasks yet</p>
                    @endif
                </div>
            </div>
        @endif
    </div>
</x-filament-panels::page>

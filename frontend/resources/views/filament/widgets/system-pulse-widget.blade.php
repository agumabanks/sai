<x-filament-widgets::widget>
    <div class="relative overflow-hidden rounded-[24px] bg-white/5 dark:bg-[#1c1c1e]/60 backdrop-blur-3xl backdrop-saturate-150 border border-black/5 dark:border-white/5 shadow-sm p-6 lg:p-8">
        
        <div class="relative z-10">
            {{-- Header Area --}}
            <div class="flex items-center justify-between mb-8">
                <div class="flex items-center gap-4">
                    <div class="h-10 w-10 rounded-full flex items-center justify-center bg-white/10 dark:bg-white/5 ring-1 ring-black/5 dark:ring-white/5">
                        <x-filament::icon
                            :icon="$this->getProviderIcon()"
                            class="h-5 w-5 text-zinc-800 dark:text-zinc-200"
                        />
                    </div>
                    <div>
                        <h2 class="text-[11px] font-semibold tracking-wide text-zinc-500 dark:text-zinc-400 uppercase">AI Core Processor</h2>
                        <p class="text-xl font-medium tracking-tight text-zinc-900 dark:text-white">
                            {{ $data['brain_provider'] ?? 'System Offline' }}
                        </p>
                    </div>
                </div>

                <div class="flex items-center gap-2">
                    @if($data['healer_active'] ?? false)
                        <div class="flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#ff453a]/10 border border-[#ff453a]/20 text-[#ff453a] text-[11px] font-medium tracking-wide">
                            <span class="relative flex h-2 w-2">
                              <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#ff453a] opacity-75"></span>
                              <span class="relative inline-flex rounded-full h-2 w-2 bg-[#ff453a]"></span>
                            </span>
                            Active Recovery
                        </div>
                    @else
                        <div class="flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#30d158]/10 border border-[#30d158]/20 text-[#30d158] text-[11px] font-medium tracking-wide">
                            <span class="h-1.5 w-1.5 rounded-full bg-[#30d158]"></span>
                            All Systems Nominal
                        </div>
                    @endif
                </div>
            </div>

            {{-- Hardware Resource Metrics --}}
            <div class="grid grid-cols-3 gap-8">
                {{-- CPU --}}
                <div class="space-y-2">
                    <div class="flex justify-between items-baseline">
                        <span class="text-[11px] font-medium text-zinc-500 dark:text-zinc-400">CPU Load</span>
                        <span class="text-sm font-medium @if(($data['cpu'] ?? 0) > 80) text-[#ff453a] @else text-zinc-900 dark:text-white @endif">{{ $data['cpu'] ?? 0 }}%</span>
                    </div>
                    <div class="h-1.5 w-full bg-zinc-200 dark:bg-zinc-800 rounded-full overflow-hidden">
                        <div class="h-full bg-zinc-800 dark:bg-white transition-all duration-700 ease-out" style="width: {{ $data['cpu'] ?? 0 }}%"></div>
                    </div>
                </div>

                {{-- RAM --}}
                <div class="space-y-2">
                    <div class="flex justify-between items-baseline">
                        <span class="text-[11px] font-medium text-zinc-500 dark:text-zinc-400">Memory</span>
                        <span class="text-sm font-medium @if(($data['ram'] ?? 0) > 80) text-[#ff453a] @else text-zinc-900 dark:text-white @endif">{{ $data['ram'] ?? 0 }}%</span>
                    </div>
                    <div class="h-1.5 w-full bg-zinc-200 dark:bg-zinc-800 rounded-full overflow-hidden">
                        <div class="h-full bg-zinc-800 dark:bg-white transition-all duration-700 ease-out" style="width: {{ $data['ram'] ?? 0 }}%"></div>
                    </div>
                </div>

                {{-- DISK --}}
                <div class="space-y-2">
                    <div class="flex justify-between items-baseline">
                        <span class="text-[11px] font-medium text-zinc-500 dark:text-zinc-400">Storage</span>
                        <span class="text-sm font-medium @if(($data['disk'] ?? 0) > 90) text-[#ff453a] @else text-zinc-900 dark:text-white @endif">{{ $data['disk'] ?? 0 }}%</span>
                    </div>
                    <div class="h-1.5 w-full bg-zinc-200 dark:bg-zinc-800 rounded-full overflow-hidden">
                        <div class="h-full bg-zinc-800 dark:bg-white transition-all duration-700 ease-out" style="width: {{ $data['disk'] ?? 0 }}%"></div>
                    </div>
                </div>
            </div>

            {{-- Chronic Failures --}}
            @if(!empty($data['failures']))
                <div class="mt-8 pt-6 border-t border-black/5 dark:border-white/10">
                    <h3 class="text-[11px] font-medium text-[#ff453a] flex items-center gap-2 mb-4">
                        Critical Anomalies
                    </h3>
                    <div class="space-y-3">
                        @foreach($data['failures'] as $fail)
                            <div class="flex items-center justify-between">
                                <span class="text-sm text-zinc-700 dark:text-zinc-300">
                                    {{ str_replace('_', ' ', str_replace('fail_count.', '', $fail['metric'])) }}
                                </span>
                                <div class="flex items-center gap-3">
                                    <span class="text-xs font-medium text-zinc-500">
                                        {{ $fail['count'] }} incidents
                                    </span>
                                    @if($fail['count'] >= ($data['thresholds']['t4'] ?? 6))
                                        <span class="text-[10px] bg-[#ff453a] text-white px-2 py-0.5 rounded-full font-medium">SOS Triggered</span>
                                    @elseif($fail['count'] >= ($data['thresholds']['t3'] ?? 4))
                                        <span class="text-[10px] bg-[#ff9f0a] text-white px-2 py-0.5 rounded-full font-medium">Load Shedding</span>
                                    @endif
                                </div>
                            </div>
                        @endforeach
                    </div>
                </div>
            @endif
        </div>
    </div>
</x-filament-widgets::widget>

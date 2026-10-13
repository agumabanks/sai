<x-filament-widgets::widget>
    <div class="relative overflow-hidden rounded-2xl glass-dark p-6 lg:p-7">

        {{-- Ambient glow orb --}}
        <div class="pointer-events-none absolute -top-10 -right-10 h-40 w-40 rounded-full opacity-20"
             style="background: radial-gradient(circle, hsla(234,89%,64%,0.6) 0%, transparent 70%);"></div>

        <div class="relative z-10">

            {{-- Header --}}
            <div class="flex items-center justify-between mb-6">
                <div class="flex items-center gap-3">
                    <div class="h-9 w-9 rounded-xl flex items-center justify-center"
                         style="background: rgba(94,92,230,0.15); border: 1px solid rgba(94,92,230,0.25);">
                        <x-filament::icon
                            :icon="$this->getProviderIcon()"
                            class="h-4 w-4 text-indigo-400"
                        />
                    </div>
                    <div>
                        <p class="text-[10px] font-bold tracking-[0.12em] uppercase text-white/40">AI Core Processor</p>
                        <p class="text-base font-semibold text-white/90 leading-tight">
                            {{ $data['brain_provider'] ?? 'System Offline' }}
                        </p>
                    </div>
                </div>

                @if($data['healer_active'] ?? false)
                    <div class="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-semibold tracking-wide"
                         style="background: rgba(255,69,58,0.12); border: 1px solid rgba(255,69,58,0.25); color: #ff6b6b;">
                        <span class="relative flex h-1.5 w-1.5">
                            <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#ff453a] opacity-75"></span>
                            <span class="relative inline-flex rounded-full h-1.5 w-1.5 bg-[#ff453a]"></span>
                        </span>
                        Active Recovery
                    </div>
                @else
                    <div class="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-semibold tracking-wide"
                         style="background: rgba(48,209,88,0.10); border: 1px solid rgba(48,209,88,0.2); color: #34d399;">
                        <span class="h-1.5 w-1.5 rounded-full bg-[#30d158]"></span>
                        All Systems Nominal
                    </div>
                @endif
            </div>

            {{-- Resource Bars --}}
            <div class="grid grid-cols-3 gap-5">

                {{-- CPU — indigo --}}
                @php $cpu = $data['cpu'] ?? 0; $cpuCrit = $cpu > 80; @endphp
                <div class="space-y-2">
                    <div class="flex justify-between items-baseline">
                        <span class="text-[11px] font-medium text-white/40 uppercase tracking-wide">CPU</span>
                        <span class="text-sm font-semibold {{ $cpuCrit ? 'text-rose-400' : 'text-white/80' }}">{{ $cpu }}%</span>
                    </div>
                    <div class="h-1 w-full rounded-full overflow-hidden" style="background: rgba(255,255,255,0.06);">
                        <div class="h-full rounded-full transition-all duration-700 ease-out"
                             style="width: {{ $cpu }}%; background: {{ $cpuCrit ? 'linear-gradient(90deg, #f43f5e, #fb7185)' : 'linear-gradient(90deg, hsl(234,89%,58%), hsl(245,80%,68%))' }}; box-shadow: {{ $cpuCrit ? '0 0 8px -1px rgba(244,63,94,0.6)' : '0 0 8px -1px hsla(234,89%,64%,0.55)' }};"></div>
                    </div>
                </div>

                {{-- RAM — purple --}}
                @php $ram = $data['ram'] ?? 0; $ramCrit = $ram > 80; @endphp
                <div class="space-y-2">
                    <div class="flex justify-between items-baseline">
                        <span class="text-[11px] font-medium text-white/40 uppercase tracking-wide">Memory</span>
                        <span class="text-sm font-semibold {{ $ramCrit ? 'text-rose-400' : 'text-white/80' }}">{{ $ram }}%</span>
                    </div>
                    <div class="h-1 w-full rounded-full overflow-hidden" style="background: rgba(255,255,255,0.06);">
                        <div class="h-full rounded-full transition-all duration-700 ease-out"
                             style="width: {{ $ram }}%; background: {{ $ramCrit ? 'linear-gradient(90deg, #f43f5e, #fb7185)' : 'linear-gradient(90deg, hsl(262,83%,60%), hsl(270,75%,68%))' }}; box-shadow: {{ $ramCrit ? '0 0 8px -1px rgba(244,63,94,0.6)' : '0 0 8px -1px hsla(262,83%,65%,0.55)' }};"></div>
                    </div>
                </div>

                {{-- Disk — amber --}}
                @php $disk = $data['disk'] ?? 0; $diskCrit = $disk > 90; @endphp
                <div class="space-y-2">
                    <div class="flex justify-between items-baseline">
                        <span class="text-[11px] font-medium text-white/40 uppercase tracking-wide">Storage</span>
                        <span class="text-sm font-semibold {{ $diskCrit ? 'text-rose-400' : 'text-white/80' }}">{{ $disk }}%</span>
                    </div>
                    <div class="h-1 w-full rounded-full overflow-hidden" style="background: rgba(255,255,255,0.06);">
                        <div class="h-full rounded-full transition-all duration-700 ease-out"
                             style="width: {{ $disk }}%; background: {{ $diskCrit ? 'linear-gradient(90deg, #f43f5e, #fb7185)' : 'linear-gradient(90deg, hsl(38,92%,48%), hsl(45,88%,58%))' }}; box-shadow: {{ $diskCrit ? '0 0 8px -1px rgba(244,63,94,0.6)' : '0 0 8px -1px hsla(38,92%,50%,0.45)' }};"></div>
                    </div>
                </div>
            </div>

            {{-- Critical Anomalies --}}
            @if(!empty($data['failures']))
                <div class="mt-6 pt-5 border-t border-white/[0.05]">
                    <p class="text-[10px] font-bold tracking-[0.12em] uppercase text-rose-400/80 mb-3">Critical Anomalies</p>
                    <div class="space-y-2">
                        @foreach($data['failures'] as $fail)
                            <div class="flex items-center justify-between">
                                <span class="text-[12px] text-white/60">
                                    {{ str_replace('_', ' ', str_replace('fail_count.', '', $fail['metric'])) }}
                                </span>
                                <div class="flex items-center gap-2">
                                    <span class="text-[11px] text-white/40">{{ $fail['count'] }}×</span>
                                    @if($fail['count'] >= ($data['thresholds']['t4'] ?? 6))
                                        <span class="text-[9px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full"
                                              style="background: rgba(255,69,58,0.2); color: #ff6b6b; border: 1px solid rgba(255,69,58,0.3);">SOS</span>
                                    @elseif($fail['count'] >= ($data['thresholds']['t3'] ?? 4))
                                        <span class="text-[9px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full"
                                              style="background: rgba(255,159,10,0.15); color: #fbbf24; border: 1px solid rgba(255,159,10,0.25);">Shedding</span>
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

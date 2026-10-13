<x-filament-widgets::widget class="h-full">
    <div class="relative overflow-hidden rounded-2xl bg-white/[0.04] backdrop-blur-[40px] p-6 shadow-[0_4px_24px_rgba(0,0,0,0.25)] border border-white/[0.08] h-full">
        <div class="relative z-10 space-y-5">

            {{-- Header --}}
            <div class="flex items-center justify-between">
                <div class="flex items-center gap-3">
                    <div class="w-9 h-9 rounded-xl bg-[#30d158]/15 border border-[#30d158]/25 flex items-center justify-center">
                        <x-heroicon-m-server-stack class="w-4 h-4 text-[#30d158]" />
                    </div>
                    <div>
                        <h3 class="text-sm font-semibold text-white/90 tracking-tight">Services</h3>
                        <p class="text-[10px] font-medium text-white/40 uppercase tracking-wider">{{ $activeCount }}/{{ $totalCount }} Active</p>
                    </div>
                </div>
                <button wire:click="refreshServices" class="p-2 rounded-xl hover:bg-white/[0.06] transition-colors group">
                    <x-heroicon-m-arrow-path class="w-4 h-4 text-white/30 group-hover:text-white/60 transition-colors" />
                </button>
            </div>

            {{-- Services List --}}
            <div class="space-y-1.5">
                @forelse($services as $service)
                    <div class="flex items-center justify-between py-2.5 px-3 rounded-xl {{ $service['active'] ? 'bg-white/[0.02]' : 'bg-[#ff453a]/5' }} border border-white/[0.04]">
                        <div class="flex items-center gap-3">
                            <x-dynamic-component
                                :component="$this->getServiceIcon($service['name'])"
                                class="w-4 h-4 {{ $service['active'] ? 'text-white/60' : 'text-[#ff453a]/70' }}"
                            />
                            <span class="text-[12px] font-medium {{ $service['active'] ? 'text-white/80' : 'text-[#ff453a]' }}">
                                {{ $service['label'] }}
                            </span>
                        </div>
                        <div class="flex items-center gap-2">
                            <span class="text-[10px] font-medium {{ $service['active'] ? 'text-[#30d158]' : 'text-[#ff453a]' }}">
                                {{ $service['active'] ? 'Active' : ucfirst($service['state']) }}
                            </span>
                            <div class="w-1.5 h-1.5 rounded-full {{ $service['active'] ? 'bg-[#30d158]' : 'bg-[#ff453a]' }}"></div>
                        </div>
                    </div>
                @empty
                    <div class="text-center py-6">
                        <p class="text-[12px] text-white/40">No services detected</p>
                    </div>
                @endforelse
            </div>

        </div>
    </div>
</x-filament-widgets::widget>

@php
    // Apple-inspired accent colors for the metric cards
    $macColor = match($color) {
        'danger' => 'text-[#ff453a] bg-[#ff453a]/10 border-[#ff453a]/20',
        'warning' => 'text-[#ff9f0a] bg-[#ff9f0a]/10 border-[#ff9f0a]/20',
        'success' => 'text-[#30d158] bg-[#30d158]/10 border-[#30d158]/20',
        'info' => 'text-[#0a84ff] bg-[#0a84ff]/10 border-[#0a84ff]/20',
        'primary' => 'text-[#bf5af2] bg-[#bf5af2]/10 border-[#bf5af2]/20',
        default => 'text-white/80 bg-white/5 border-white/10'
    };
    
    $macIconColor = match($color) {
        'danger' => 'text-[#ff453a]',
        'warning' => 'text-[#ff9f0a]',
        'success' => 'text-[#30d158]',
        'info' => 'text-[#0a84ff]',
        'primary' => 'text-[#bf5af2]',
        default => 'text-white/80'
    };
@endphp

<div class="relative overflow-hidden rounded-3xl bg-white/[0.03] dark:bg-[#1c1c1e]/40 backdrop-blur-[30px] backdrop-saturate-[180%] border border-white/[0.08] shadow-[0_4px_24px_rgba(0,0,0,0.2)] transition-transform duration-300 hover:scale-[1.02] flex flex-col p-5">
    
    <div class="relative z-10 space-y-3 flex-1 flex flex-col justify-between">
        {{-- Header --}}
        <div class="flex items-start justify-between">
            <div class="flex flex-col">
                <span class="text-[12px] font-medium text-white/60 tracking-wide">{{ $label }}</span>
                @if($description)
                    <p class="text-[10px] text-white/40 font-medium leading-tight mt-0.5">{{ $description }}</p>
                @endif
            </div>
            
            @if($icon)
                <div class="w-8 h-8 rounded-full bg-white/[0.05] border border-white/[0.08] flex items-center justify-center shadow-inner">
                    <x-dynamic-component :component="$icon" class="w-4 h-4 {{ $macIconColor }}" />
                </div>
            @endif
        </div>

        {{-- Value --}}
        <div class="mt-4 mb-2">
            <div class="text-[28px] leading-none font-semibold text-white/95 tracking-tight shadow-sm drop-shadow-md">
                {{ $value }}
            </div>
        </div>

        {{-- Trend Indicator --}}
        @if($trend)
            <div class="pt-3 border-t border-white/[0.05] mt-auto">
                @if(str_starts_with($trend, '+') || str_contains(strtolower($trend), 'normal') || str_contains(strtolower($trend), 'healthy') || str_contains(strtolower($trend), 'stable') || str_contains(strtolower($trend), 'clear'))
                    <div class="inline-flex items-center gap-1.5">
                        <x-heroicon-s-chevron-up class="w-3 h-3 text-[#30d158]" />
                        <span class="text-[11px] font-medium text-[#30d158]">{{ $trend }}</span>
                    </div>
                @elseif(str_starts_with($trend, '-') || str_contains(strtolower($trend), 'high') || str_contains(strtolower($trend), 'critical') || str_contains(strtolower($trend), 'low'))
                    <div class="inline-flex items-center gap-1.5">
                        <x-heroicon-s-chevron-down class="w-3 h-3 text-[#ff453a]" />
                        <span class="text-[11px] font-medium text-[#ff453a]">{{ $trend }}</span>
                    </div>
                @else
                    <div class="inline-flex items-center gap-1.5">
                        <span class="text-[11px] font-medium text-white/50">{{ $trend }}</span>
                    </div>
                @endif
            </div>
        @endif
    </div>
</div>
